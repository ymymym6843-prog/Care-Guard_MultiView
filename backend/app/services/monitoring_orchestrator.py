"""
모니터링 오케스트레이터

camera -> pose -> person_tracker -> fall_detect -> alert -> broadcast 파이프라인을 캡슐화합니다.
ws.py에서 분리하여 단일 책임 원칙을 준수합니다.

YOLO 가용 시: Camera -> YOLO11 (N명 bbox+track_id) -> 각 ROI -> MediaPipe (33점) -> FallDetector -> Alert
YOLO 미설치:  Camera -> MediaPipe (5명 제한) -> PersonTracker -> FallDetector -> Alert (기존 파이프라인)
"""

import asyncio
import time
from concurrent.futures import ThreadPoolExecutor

from app.config import settings
from app.core.connection_manager import connection_manager
from app.core.logging_config import get_logger
from app.services.camera_service import camera_service
from app.services.pose_service import pose_service, PoseResult, PoseLandmarks
from app.services.fall_detector import fall_detector
from app.services.alert_manager import alert_manager
from app.services.person_tracker import person_tracker
from app.services.multi_person_detector import multi_person_detector
from app.services.walking_aid_detector import (
    walking_aid_detector,
    walking_aid_heuristic,
    walking_aid_tracker,
)
from app.services.skeleton_blackbox import skeleton_blackbox, PersonSnapshot
from app.services.privacy_pipeline import privacy_pipeline
from app.services.privacy_audit import privacy_audit
from app.services.zone_checker import zone_checker

logger = get_logger("app.services.orchestrator")

# ML 작업 전용 스레드 풀 (기본 executor를 점유하지 않도록 분리)
# max_workers=8: 다중 카메라 처리 시 낙상 감지 병렬화를 위해 확대
_ml_executor = ThreadPoolExecutor(max_workers=8, thread_name_prefix="ml-worker")

# 버퍼 정리 주기 (초) - 사라진 인물의 FallClassifier 버퍼 메모리 누수 방지
_BUFFER_CLEANUP_INTERVAL = 30.0


class _CameraProcessingState:
    """카메라별 처리 상태 (다중 카메라에서 카메라 간 상태 격리)"""
    __slots__ = ("frame_num", "active_person_ids", "last_person_centers", "cached_aid_detections")

    def __init__(self):
        self.frame_num: int = 0
        self.active_person_ids: set[str] = set()
        self.last_person_centers: dict[str, tuple[float, float]] = {}
        self.cached_aid_detections: list = []


class MonitoringOrchestrator:
    """카메라 -> 포즈 -> 추적 -> 낙상감지 -> 알림 파이프라인 오케스트레이터"""

    # 보행도구 감지 주기 (N 프레임마다 1회 = 성능 최적화)
    # 보행도구 ONNX가 ~200ms + CPU 경합으로 ~500ms 스파이크 발생
    # 보행도구는 보조 기능이며 상태 변화가 매우 느리므로 긴 간격 허용
    # 150프레임 ≈ 카메라당 ~60초 (4카메라 2fps 기준)
    _WALKING_AID_DETECT_INTERVAL = 150

    def __init__(self):
        self._use_yolo: bool | None = None
        self._paused = False  # 개발/데모용 일시정지 플래그
        self._last_cleanup_time = time.monotonic()
        # 카메라별 처리 상태 (다중 카메라 지원)
        self._camera_states: dict[str, _CameraProcessingState] = {}

    def _get_cam_state(self, camera_id: str) -> _CameraProcessingState:
        """카메라별 처리 상태 조회/생성"""
        if camera_id not in self._camera_states:
            self._camera_states[camera_id] = _CameraProcessingState()
        return self._camera_states[camera_id]

    # 하위 호환 프로퍼티 (기본 카메라 cam0에 위임)
    @property
    def _active_person_ids(self) -> set[str]:
        return self._get_cam_state("cam0").active_person_ids

    @_active_person_ids.setter
    def _active_person_ids(self, value: set[str]):
        self._get_cam_state("cam0").active_person_ids = value

    @property
    def _frame_num(self) -> int:
        return self._get_cam_state("cam0").frame_num

    @_frame_num.setter
    def _frame_num(self, value: int):
        self._get_cam_state("cam0").frame_num = value

    @property
    def _last_person_centers(self) -> dict[str, tuple[float, float]]:
        return self._get_cam_state("cam0").last_person_centers

    @_last_person_centers.setter
    def _last_person_centers(self, value: dict):
        self._get_cam_state("cam0").last_person_centers = value

    @property
    def _cached_aid_detections(self) -> list:
        return self._get_cam_state("cam0").cached_aid_detections

    @_cached_aid_detections.setter
    def _cached_aid_detections(self, value: list):
        self._get_cam_state("cam0").cached_aid_detections = value

    @property
    def is_paused(self) -> bool:
        """파이프라인 일시정지 상태"""
        return self._paused

    def pause(self) -> None:
        """파이프라인 일시정지 (개발/데모용)"""
        if not self._paused:
            self._paused = True
            logger.info("파이프라인 일시정지됨")

    def resume(self) -> None:
        """파이프라인 재개"""
        if self._paused:
            self._paused = False
            logger.info("파이프라인 재개됨")

    @property
    def use_yolo(self) -> bool:
        """YOLO 사용 여부 (lazy check)"""
        if self._use_yolo is None:
            self._use_yolo = multi_person_detector.enabled
            if self._use_yolo:
                logger.info("하이브리드 파이프라인 활성화: YOLO11 + MediaPipe")
            else:
                logger.info("기존 파이프라인 유지: MediaPipe-only")
        return self._use_yolo

    async def process_frame_pipeline(self, camera_id: str = "cam0", camera_instance=None) -> None:
        """단일 프레임 처리 파이프라인

        Args:
            camera_id: 카메라 ID (person_id 프리픽스 및 브로드캐스트용)
            camera_instance: CameraInstance (None이면 기본 카메라)
        """
        # 1. 프레임 가져오기 (큐에서 최신 프레임만 사용, 나머지 버림)
        frame = None
        queue = camera_instance.frame_queue if camera_instance else camera_service.frame_queue
        try:
            frame = queue.get_nowait()
            # 큐에 쌓인 오래된 프레임 버리기
            while not queue.empty():
                try:
                    frame = queue.get_nowait()
                except Exception:
                    break
        except Exception:
            return

        if frame is None:
            return

        if self.use_yolo:
            await self._process_yolo_pipeline(frame, camera_id, camera_instance)
        else:
            await self._process_mediapipe_pipeline(frame, camera_id)

    async def _process_yolo_pipeline(self, frame, camera_id: str = "cam0", camera_instance=None) -> None:
        """YOLO + MediaPipe 하이브리드 파이프라인

        성능 최적화:
        - MediaPipe ROI 처리를 asyncio.gather()로 병렬화
        - 사라진 인물 버퍼 주기적 정리
        - 프레임 처리 시간 모니터링
        """
        t_start = time.monotonic()
        cam_state = self._get_cam_state(camera_id)
        cam_state.frame_num += 1

        # 2. YOLO 감지: 인원 감지 (매 프레임) + 보행도구 감지 (N프레임마다)
        loop = asyncio.get_running_loop()

        # 인원 감지는 항상 실행 (camera_id 전달 → 카메라별 트래커 격리)
        yolo_result = await loop.run_in_executor(
            _ml_executor, multi_person_detector.detect, frame, camera_id
        )

        # 보행도구 감지는 N 프레임마다만 실행 (모델 비활성 시 완전 건너뜀)
        # YOLO와 순차 실행 (병렬 시 CPU 경합으로 YOLO 100ms→700ms 급증 방지)
        run_aid_detection = (
            walking_aid_detector.enabled
            and cam_state.frame_num % self._WALKING_AID_DETECT_INTERVAL == 0
        )
        if run_aid_detection:
            aid_detections = await loop.run_in_executor(
                _ml_executor, walking_aid_detector.detect, frame
            )
            cam_state.cached_aid_detections = aid_detections
        else:
            aid_detections = cam_state.cached_aid_detections

        t_yolo = time.monotonic()

        if not yolo_result.persons:
            # 감지된 인원 없음 - 빈 메트릭 브로드캐스트
            cam_state.active_person_ids.clear()
            await self._cleanup_stale_buffers(camera_id)
            await self._broadcast_empty_metrics(camera_id, camera_instance)
            return

        # 3. 키포인트 추출 (YOLO-only vs YOLO+MediaPipe)
        pose_result = PoseResult(frame=frame, timestamp=time.time())
        h, w = frame.shape[:2]

        if settings.YOLO_KEYPOINTS_ONLY:
            # YOLO 17점 키포인트 직접 사용 (MediaPipe 생략 = 빠름)
            roi_results = []
            for idx, person in enumerate(yolo_result.persons):
                person_id = f"{camera_id}_person_{person.track_id}"
                landmarks = None
                if person.keypoints is not None and len(person.keypoints) >= 17:
                    # YOLO keypoints: (17, 3) [x, y, conf] in pixel coords
                    kpts = person.keypoints
                    lm_list = []
                    for kp_idx in range(17):
                        x_px, y_px, vis = kpts[kp_idx]
                        lm_list.append({
                            "x": float(x_px / w),
                            "y": float(y_px / h),
                            "z": 0.0,
                            "visibility": float(vis),
                        })
                    landmarks = PoseLandmarks(
                        landmarks=lm_list,
                        person_id=person_id,
                        keypoint_format="coco_17",
                        bbox=person.bbox,  # YOLO bbox → 프론트엔드 Canvas 오버레이용
                    )
                roi_results.append((idx, person, person_id, landmarks))
            t_mediapipe = time.monotonic()
        else:
            # MediaPipe ROI 추출을 병렬로 실행 (정밀도 ↑, 속도 ↓)
            async def _extract_roi(person, idx):
                person_id = f"{camera_id}_person_{person.track_id}"
                landmarks = await loop.run_in_executor(
                    _ml_executor,
                    pose_service.process_roi_sync,
                    frame,
                    person.bbox,
                    person_id,
                )
                return idx, person, person_id, landmarks

            roi_tasks = [
                _extract_roi(person, idx)
                for idx, person in enumerate(yolo_result.persons)
            ]
            roi_results = await asyncio.gather(*roi_tasks, return_exceptions=True)
            t_mediapipe = time.monotonic()

        # 현재 프레임에서 감지된 인물 ID 추적
        current_person_ids = set()
        # 인원별 보행도구 상태 (브로드캐스트용)
        walking_aid_info: dict[str, dict] = {}
        # 현재 프레임의 인원 중심 좌표 (track_id 변경 대응용)
        current_person_centers: dict[str, tuple[float, float]] = {}

        for result in roi_results:
            if isinstance(result, BaseException):
                logger.warning("MediaPipe ROI 처리 오류: %s", result)
                continue

            idx, person, person_id, landmarks = result
            current_person_ids.add(person_id)

            # track_id 변경 감지: 새 ID가 이전 ID 위치 근처에 나타나면 ML 버퍼 이전
            if person_id not in cam_state.active_person_ids and cam_state.last_person_centers:
                pcx_new = (person.bbox[0] + person.bbox[2]) / 2
                pcy_new = (person.bbox[1] + person.bbox[3]) / 2
                self._migrate_ml_buffer(person_id, pcx_new, pcy_new, cam_state)

            if landmarks is not None:
                pose_result.poses.append(landmarks)

                # 스켈레톤 + bbox 드로잉은 프론트엔드 Canvas 오버레이로 이전
                # (MJPEG는 raw 영상 30fps 유지, AI 결과는 WebSocket으로 전송)

                # 보행도구 휴리스틱 (MediaPipe 33점 필요, YOLO-only 모드에서는 건너뜀)
                if settings.YOLO_KEYPOINTS_ONLY:
                    mp_heuristic = None  # COCO 17점에서는 휴리스틱 비활성화
                else:
                    mp_heuristic = walking_aid_heuristic.estimate(landmarks.landmarks, person_id)

                # 인원 중심 좌표
                pcx = (person.bbox[0] + person.bbox[2]) / 2
                pcy = (person.bbox[1] + person.bbox[3]) / 2
                current_person_centers[person_id] = (pcx, pcy)

                # 보행도구 상태 업데이트
                aid_state = walking_aid_tracker.update(
                    person_id=person_id,
                    person_center=(pcx, pcy),
                    yolo_detections=aid_detections,
                    mp_heuristic=mp_heuristic,
                    frame_num=cam_state.frame_num,
                )

                walking_aid_info[person_id] = {
                    "type": aid_state.aid_type,
                    "established": aid_state.established,
                    "missing": aid_state.is_missing,
                }

                # 보행도구 분실 알림
                if aid_state.established and aid_state.is_missing:
                    alert_manager.update_walking_aid_alert(person_id, aid_state)

        cam_state.active_person_ids = current_person_ids
        cam_state.last_person_centers = current_person_centers

        cam_fps = camera_instance.fps if camera_instance else camera_service.fps
        pose_result.fps = cam_fps
        # MJPEG는 raw 영상 유지 (camera_service._latest_jpeg는 카메라 스레드가 30fps로 갱신)
        # AI 결과(bbox, skeleton, 낙상)는 WebSocket으로 프론트엔드에 전송

        # 보행도구 상태 정리
        walking_aid_tracker.cleanup(current_person_ids)
        walking_aid_heuristic.cleanup(current_person_ids)

        # 4~6. 낙상 감지, 알림, 브로드캐스트 (공통 로직)
        await self._process_fall_and_broadcast(pose_result, walking_aid_info, camera_id, camera_instance)

        # 사라진 인물 버퍼 주기적 정리
        await self._cleanup_stale_buffers(camera_id)

        # 처리 시간 모니터링
        t_end = time.monotonic()
        total_ms = (t_end - t_start) * 1000
        yolo_ms = (t_yolo - t_start) * 1000
        mp_ms = (t_mediapipe - t_yolo) * 1000

        logger.debug(
            "[파이프라인:%s] 총 %.0fms (YOLO=%.0fms, MP=%.0fms) | "
            "감지=%d명, 보행도구=%s, 활성ID=%s",
            camera_id, total_ms, yolo_ms, mp_ms,
            len(yolo_result.persons),
            "검사" if run_aid_detection else "캐시",
            ",".join(sorted(current_person_ids)) if current_person_ids else "없음",
        )

        if total_ms > 100:  # 100ms 초과 시 경고 (10fps 미만)
            logger.warning(
                "[%s] 파이프라인 처리 지연: %.0fms (YOLO=%.0fms, MP=%.0fms, 인원=%d, 보행도구=%s)",
                camera_id, total_ms, yolo_ms, mp_ms, len(yolo_result.persons),
                "검사" if run_aid_detection else "캐시",
            )

    def _migrate_ml_buffer(self, new_person_id: str, cx: float, cy: float, cam_state: _CameraProcessingState | None = None) -> None:
        """새 track_id가 이전 ID 위치 근처에 나타나면 ML 버퍼/상태를 이전.

        YOLO 트래킹 ID가 변경되면 FallClassifier 버퍼(30프레임)가 초기화되어
        ML 분류기가 ~2초간 비활성화됩니다. 위치가 가까운 이전 ID의 버퍼를 복사하여
        ML 판정 연속성을 유지합니다.
        """
        from app.services.fall_classifier import fall_classifier
        from app.services.posture_classifier import posture_classifier

        if cam_state is None:
            cam_state = self._get_cam_state("cam0")

        _MAX_DIST = 0.15  # 정규화 좌표 기준 최대 거리

        # 현재 프레임에 없고, 이전 프레임에 있던 인물 중 가장 가까운 ID 찾기
        best_id = None
        best_dist = _MAX_DIST
        for old_id, (ox, oy) in cam_state.last_person_centers.items():
            if old_id in cam_state.active_person_ids:
                continue  # 아직 활성인 ID는 건너뜀
            dist = ((cx - ox) ** 2 + (cy - oy) ** 2) ** 0.5
            if dist < best_dist:
                best_dist = dist
                best_id = old_id

        if best_id is None:
            return

        # ML 버퍼 이전
        old_buf = fall_classifier._buffers.get(best_id)
        if old_buf and len(old_buf) > 0:
            from collections import deque
            fall_classifier._buffers[new_person_id] = deque(old_buf, maxlen=fall_classifier.SEQUENCE_LENGTH)
            logger.info(
                "[ID이전] %s → %s (거리=%.3f, ML버퍼=%d프레임 이전)",
                best_id, new_person_id, best_dist, len(old_buf),
            )

        # FallDetector 상태 이전 (히스토리, 프레임 카운터 + 낙상 상태)
        old_state = fall_detector._person_states.get(best_id)
        if old_state:
            new_state = fall_detector.get_or_create_state(new_person_id)
            new_state.head_y_history = old_state.head_y_history
            new_state.hip_y_history = old_state.hip_y_history
            new_state.frames_since_first_seen = old_state.frames_since_first_seen
            new_state.ml_score_ema = old_state.ml_score_ema
            # N2/N3/N4 확장 규칙 상태 이전
            new_state.arm_spread_history = old_state.arm_spread_history
            new_state.prev_com_bos_deviation = old_state.prev_com_bos_deviation
            new_state.com_bos_growing_frames = old_state.com_bos_growing_frames
            new_state.prev_min_knee_angle = old_state.prev_min_knee_angle
            # 낙상 상태 이전 (track_id 변경 시 낙상 유실 방지)
            new_state.is_fallen = old_state.is_fallen
            new_state.fall_start_time = old_state.fall_start_time
            new_state.consecutive_fall_frames = old_state.consecutive_fall_frames
            new_state.cooldown_active = old_state.cooldown_active
            new_state.last_normal_time = old_state.last_normal_time
            new_state.fall_score = old_state.fall_score
            new_state.fall_lying_duration = old_state.fall_lying_duration
            new_state.quick_recovery_standing_frames = old_state.quick_recovery_standing_frames
            new_state.post_fall_frames = old_state.post_fall_frames
            new_state.post_fall_velocity_history = old_state.post_fall_velocity_history
            if old_state.is_fallen:
                logger.info(
                    "[ID이전] %s → %s 낙상 상태 이전 (is_fallen=%s, duration=%.1fs)",
                    best_id, new_person_id, old_state.is_fallen,
                    (time.time() - old_state.fall_start_time) if old_state.fall_start_time else 0,
                )

        # AlertManager 상태 이전 (WARNING/DANGER 상태 유지)
        old_alert = alert_manager._person_alerts.get(best_id)
        if old_alert and old_alert.state.value not in ("normal",):
            new_alert = alert_manager._get_or_create(new_person_id)
            new_alert.state = old_alert.state
            new_alert.fall_start_time = old_alert.fall_start_time
            new_alert.warning_time = old_alert.warning_time
            new_alert.danger_time = old_alert.danger_time
            new_alert.pre_impact_warned = old_alert.pre_impact_warned
            new_alert.recovery_start_time = old_alert.recovery_start_time
            logger.info(
                "[ID이전] %s → %s 알림 상태 이전 (state=%s)",
                best_id, new_person_id, old_alert.state.value,
            )

        # PostureClassifier 상태 이전
        old_posture = posture_classifier._person_states.get(best_id)
        if old_posture:
            posture_classifier._person_states[new_person_id] = old_posture

    async def _process_mediapipe_pipeline(self, frame, camera_id: str = "cam0") -> None:
        """기존 MediaPipe-only 파이프라인"""
        # 2. 포즈 감지 (스레드 풀에서)
        result = await pose_service.process_frame(frame)

        # 3. 인물 추적 (안정적 person_id 할당)
        if result.poses:
            person_tracker.update(result.poses)

        # 4~6. 낙상 감지, 알림, 브로드캐스트
        await self._process_fall_and_broadcast(result, camera_id=camera_id)

    async def _process_fall_and_broadcast(self, result: PoseResult, walking_aid_info: dict | None = None, camera_id: str = "cam0", camera_instance=None) -> None:
        """낙상 감지 + 알림 상태 업데이트 + 블랙박스 기록 + 브로드캐스트 (공통)"""
        fall_results = []
        persons_data = []
        bbox_data = []
        blackbox_persons: list[PersonSnapshot] = []

        loop = asyncio.get_running_loop()

        # Phase 1: 모든 인물의 낙상 감지를 병렬 실행 (GRU ONNX 추론 병렬화)
        fall_tasks = []
        for pose in result.poses:
            task = loop.run_in_executor(
                _ml_executor,
                fall_detector.detect,
                pose.landmarks,
                pose.person_id,
                getattr(pose, "keypoint_format", "mediapipe_33"),
            )
            fall_tasks.append(task)

        fall_raw_results = await asyncio.gather(*fall_tasks, return_exceptions=True) if fall_tasks else []

        # Phase 2: 결과 처리 (zone 체크, 알림 업데이트)
        for pose, fall_result in zip(result.poses, fall_raw_results):
            if isinstance(fall_result, BaseException):
                logger.warning("낙상 감지 오류: %s", fall_result)
                continue

            # Zone 체크: bbox 기준으로 zone 판별
            zone_type = None
            if pose.bbox:
                try:
                    zone_type = await zone_checker.check_person_zone(camera_id, pose.bbox)
                except Exception as e:
                    logger.debug("zone 체크 실패 (무시): %s", e)

            if zone_type == "exclusion":
                # exclusion zone 내 인물은 완전 스킵 (감지 무시)
                continue

            if zone_type == "safe":
                # safe zone: 실제 낙상 징후(급격한 하강)는 억제하지 않음
                # fall_type이 front/back/side_fall이면 진짜 낙상 → 알림 유지
                actual_fall = fall_result.get("fall_type", "normal") in (
                    "front_fall", "back_fall", "side_fall",
                )
                if not actual_fall:
                    fall_result["is_fallen"] = False
                    fall_result["confidence"] = 0.0

            fall_results.append(fall_result)

            # per-person 상세 데이터
            person_data = {
                "person_id": pose.person_id,
                "fall_confidence": round(fall_result["confidence"], 3),
                "is_fallen": fall_result["is_fallen"],
                "head_y": round(fall_result["head_y"], 4),
                "hip_y": round(fall_result["hip_y"], 4),
                "angle": round(fall_result["angle"], 1),
                "fall_duration": round(fall_result["fall_duration"], 1),
                "fall_type": fall_result["fall_type"],
                "is_pre_impact": fall_result.get("is_pre_impact", False),
                "posture": fall_result.get("posture", "unknown"),
                "rule_score": round(fall_result["rule_score"], 3),
                "ml_score": round(fall_result["ml_score"], 3),
            }

            # 보행도구 정보 추가
            if walking_aid_info and pose.person_id in walking_aid_info:
                person_data["walking_aid"] = walking_aid_info[pose.person_id]

            persons_data.append(person_data)

            # 바운딩 박스 데이터 (프론트엔드 오버레이용)
            if pose.bbox:
                bbox_data.append({
                    "person_id": pose.person_id,
                    "bbox": [float(v) for v in pose.bbox],  # numpy float32 → Python float
                    "is_fallen": fall_result["is_fallen"],
                    "confidence": round(fall_result["confidence"], 3),
                    "camera_id": camera_id,
                    "zone_type": zone_type,
                })

            # Skeleton Blackbox: 좌표 스냅샷 기록
            blackbox_persons.append(PersonSnapshot(
                track_id=pose.person_id,
                landmarks=pose.landmarks,  # type: ignore[arg-type]
                posture=fall_result.get("posture", "unknown"),
                confidence=fall_result["confidence"],
            ))

            # 5. 알림 매니저 업데이트
            alert_result = alert_manager.update(
                person_id=pose.person_id,
                is_fallen=fall_result["is_fallen"],
                confidence=fall_result["confidence"],
                fall_duration=fall_result["fall_duration"],
                fall_type=fall_result["fall_type"],
                is_pre_impact=fall_result.get("is_pre_impact", False),
            )

            # 상태 변경 시 알림 브로드캐스트
            if alert_result["changed"]:
                await connection_manager.broadcast_alert_update({
                    "alert_level": alert_manager.get_state_for_frontend(),
                    "state": alert_result["state"],
                    "duration": alert_result["duration"],
                    "person_id": alert_result["person_id"],
                    "confidence": alert_result["confidence"],
                    "fall_type": fall_result["fall_type"],
                })

        # 5.5. Skeleton Blackbox 기록 + DANGER 시 덤프
        if blackbox_persons:
            skeleton_blackbox.record(time.time(), blackbox_persons)

        for fr, pose in zip(fall_results, result.poses):
            if fr.get("is_fallen") and alert_manager.global_state.value == "danger":
                dump_path = skeleton_blackbox.dump_incident(
                    event_id=f"danger_{pose.person_id}",
                    trigger_person=pose.person_id,
                    trigger_type="DANGER",
                )
                if dump_path:
                    import asyncio as _aio
                    _aio.ensure_future(privacy_audit.log_incident_dump(
                        incident_id=dump_path.stem,
                        data_hash=dump_path.stem,
                    ))
                break  # 한 번만 덤프

        # 6. 포즈 데이터 & 메트릭 브로드캐스트
        pose_data = [
            {"person_id": pose.person_id, "landmarks": pose.landmarks, "camera_id": camera_id}
            for pose in result.poses
        ]

        cam_active = camera_instance.is_active if camera_instance else camera_service.is_active
        metrics = {
            "person_count": len(result.poses),
            "fps": round(result.fps, 1),
            "alert_level": alert_manager.get_state_for_frontend(),
            "alert_duration": round(alert_manager.alert_duration, 1),
            "yolo_enabled": self.use_yolo,
            "walking_aid_users": walking_aid_tracker.count_established(),
            "is_camera_active": cam_active,
            "camera_id": camera_id,
        }

        # 하위 호환: 기존 top-level 필드는 첫 번째 인물 데이터 유지
        if fall_results:
            fr = fall_results[0]
            metrics.update({
                "fall_confidence": round(fr["confidence"], 3),
                "head_y": round(fr["head_y"], 4),
                "hip_y": round(fr["hip_y"], 4),
                "angle": round(fr["angle"], 1),
            })

        # 다중 인원 상세 데이터
        if persons_data:
            metrics["persons"] = persons_data

        # 바운딩 박스 데이터 (프론트엔드 오버레이용)
        if bbox_data:
            metrics["bboxes"] = bbox_data

        # 메트릭은 항상 캐시 (broadcast_metrics 내부에서 _last_metrics 저장)
        # 새 WebSocket 연결 시 캐시된 메트릭을 즉시 제공
        await connection_manager.broadcast_metrics(metrics)

        if connection_manager.active_count > 0 and pose_data:
            await connection_manager.broadcast_pose_data(pose_data, result.fps, camera_id)

    async def _cleanup_stale_buffers(self, camera_id: str = "cam0") -> None:
        """사라진 인물의 FallClassifier 버퍼를 주기적으로 정리 (메모리 누수 방지)"""
        now = time.monotonic()
        if now - self._last_cleanup_time < _BUFFER_CLEANUP_INTERVAL:
            return

        self._last_cleanup_time = now

        # 모든 카메라의 활성 인물 ID 합집합
        all_active = set()
        for cs in self._camera_states.values():
            all_active |= cs.active_person_ids

        # FallClassifier 및 PostureClassifier 버퍼에서 현재 감지되지 않는 인물 제거
        from app.services.fall_classifier import fall_classifier
        from app.services.posture_classifier import posture_classifier
        stale_ids = set(fall_classifier._buffers.keys()) - all_active
        if stale_ids:
            for pid in stale_ids:
                fall_classifier.reset_person(pid)
            logger.debug("사라진 인물 버퍼 정리: %d명 (%s)", len(stale_ids), stale_ids)

        # fall_detector 및 posture_classifier 내부 상태도 정리
        stale_detector_ids = set(fall_detector._person_states.keys()) - all_active
        if stale_detector_ids:
            for pid in stale_detector_ids:
                fall_detector._person_states.pop(pid, None)
                posture_classifier.reset_person(pid)
            logger.debug("사라진 인물 낙상/자세 상태 정리: %d명", len(stale_detector_ids))

    async def _broadcast_empty_metrics(self, camera_id: str = "cam0", camera_instance=None) -> None:
        """감지된 인원 없을 때 빈 메트릭 브로드캐스트 (캐시 저장 포함)"""
        cam_fps = camera_instance.fps if camera_instance else camera_service.fps
        cam_active = camera_instance.is_active if camera_instance else camera_service.is_active
        metrics = {
            "person_count": 0,
            "fps": round(cam_fps, 1),
            "alert_level": alert_manager.get_state_for_frontend(),
            "alert_duration": round(alert_manager.alert_duration, 1),
            "yolo_enabled": self.use_yolo,
            "walking_aid_users": walking_aid_tracker.count_established(),
            "is_camera_active": cam_active,
            "camera_id": camera_id,
            "fall_confidence": 0.0,
            "head_y": 0.0,
            "hip_y": 0.0,
            "angle": 90.0,
            "persons": [],
            "bboxes": [],
        }
        await connection_manager.broadcast_metrics(metrics)

    async def _broadcast_idle_metrics(self) -> None:
        """카메라 비활성 시 idle 메트릭 브로드캐스트"""
        metrics = {
            "person_count": 0,
            "fps": 0,
            "alert_level": "safe",
            "alert_duration": 0,
            "yolo_enabled": self.use_yolo,
            "walking_aid_users": 0,
            "is_camera_active": False,
            "fall_confidence": 0.0,
            "head_y": 0.0,
            "hip_y": 0.0,
            "angle": 90.0,
            "persons": [],
            "bboxes": [],
        }
        await connection_manager.broadcast_metrics(metrics)

    async def run_loop(self) -> None:
        """프레임 처리 무한 루프 (~15fps 제한으로 이벤트 루프 부하 방지)

        다중 카메라: 활성 카메라 프레임을 순차 처리 (YOLO 모델 공유)
        """
        logger.info("모니터링 파이프라인 루프 시작")
        _loop_count = 0
        while True:
            try:
                _loop_count += 1
                # 일시정지 상태 시 idle 메트릭만 전송하고 대기 (개발/데모용)
                if self._paused:
                    await self._broadcast_idle_metrics()
                    await asyncio.sleep(0.5)
                    continue

                # 활성 카메라 목록 조회
                active_cameras = camera_service.active_cameras()
                if not active_cameras:
                    if _loop_count % 100 == 1:
                        logger.warning("활성 카메라 없음 (loop=%d)", _loop_count)
                    await self._broadcast_idle_metrics()
                    await asyncio.sleep(0.5)
                    continue

                if _loop_count <= 5 or _loop_count % 300 == 0:
                    logger.info("파이프라인 루프 #%d: 카메라=%d, ws=%d, paused=%s",
                                _loop_count, len(active_cameras),
                                connection_manager.active_count, self._paused)

                cycle_start = time.monotonic()
                processed = False
                for camera_id, camera_instance in active_cameras:
                    try:
                        # 10초 타임아웃: GPU 행(hang) 시 전체 루프 멈춤 방지
                        await asyncio.wait_for(
                            self.process_frame_pipeline(camera_id, camera_instance),
                            timeout=10.0,
                        )
                        processed = True
                    except asyncio.TimeoutError:
                        logger.error("[%s] 프레임 처리 타임아웃 (10초 초과) - 건너뜀", camera_id)
                        processed = True  # 타임아웃이어도 루프는 계속
                    except Exception as e:
                        logger.error("[%s] 파이프라인 처리 오류: %s", camera_id, e, exc_info=True)
                        try:
                            await connection_manager.broadcast_metrics({
                                "person_count": 0,
                                "fps": round(camera_instance.fps, 1),
                                "alert_level": alert_manager.get_state_for_frontend(),
                                "alert_duration": round(alert_manager.alert_duration, 1),
                                "yolo_enabled": self.use_yolo,
                                "walking_aid_users": 0,
                                "is_camera_active": camera_instance.is_active,
                                "camera_id": camera_id,
                                "fall_confidence": 0.0,
                                "head_y": 0.0,
                                "hip_y": 0.0,
                                "angle": 90.0,
                                "persons": [],
                                "bboxes": [],
                            })
                        except Exception:
                            pass  # broadcast 실패도 루프를 죽이지 않음

                if not processed:
                    await asyncio.sleep(0.5)
                    continue

                # 적응형 슬립: 사이클 처리 시간을 감안하여 잔여 시간만 대기
                # 처리가 이미 목표 간격을 초과했으면 즉시 다음 사이클 시작
                cycle_elapsed = time.monotonic() - cycle_start
                remaining_sleep = max(0.001, settings.AI_PROCESS_INTERVAL - cycle_elapsed)
                await asyncio.sleep(remaining_sleep)

            except asyncio.CancelledError:
                logger.info("파이프라인 루프 취소됨 (정상 종료)")
                break
            except Exception as e:
                logger.error("파이프라인 루프 치명적 오류 (복구 시도): %s", e, exc_info=True)
                await asyncio.sleep(1.0)  # 1초 대기 후 복구


# 싱글턴
monitoring_orchestrator = MonitoringOrchestrator()
