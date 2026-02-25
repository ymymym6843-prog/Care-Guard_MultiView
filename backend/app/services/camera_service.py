"""
카메라 캡처 서비스 (Producer)

OpenCV를 사용한 카메라 캡처를 전용 스레드에서 실행합니다.
프레임을 큐에 넣어 pose_service가 소비합니다.

데모 모드: 영상 파일 반복 재생 + 실시간 소스 전환 지원
다중 카메라: CameraInstance(개별 카메라) + CameraManager(관리자) 구조
"""

import os
import threading
import time
from pathlib import Path
from queue import Queue, Full

import cv2
import numpy as np

from app.config import settings
from app.core.logging_config import get_logger

logger = get_logger("app.services.camera")


class CameraInstance:
    """개별 카메라 인스턴스 (캡처 스레드 + 프레임 큐 + JPEG 버퍼)"""

    def __init__(self, camera_id: str, name: str = ""):
        self.camera_id = camera_id
        self.name = name or camera_id
        self._capture: cv2.VideoCapture | None = None
        self._thread: threading.Thread | None = None
        self._running = False
        self._lock = threading.Lock()

        # Producer → Consumer 큐 (메모리 방지)
        self.frame_queue: Queue[np.ndarray] = Queue(maxsize=settings.FRAME_QUEUE_SIZE)

        # MJPEG 스트리밍용 최신 JPEG 바이트
        self._latest_jpeg: bytes | None = None
        self._jpeg_lock = threading.Lock()

        # 상태
        self.fps: float = 0.0
        self.is_active: bool = False
        self.frame_width: int = 640
        self.frame_height: int = 480

        # 현재 소스
        self._current_source: str | int = ""

        # 데모 모드 상태
        self._demo_mode: bool = False
        self._demo_source: str = ""
        self._switch_requested: bool = False
        self._switch_source: str = ""

        # 재생 속도 배율 (1.0 = 원속, 0.5 = 절반 속도, 2.0 = 2배속)
        self._speed: float = 1.0

        # 플레이리스트 모드 (여러 영상을 순차 재생)
        self._playlist: list[str] = []
        self._playlist_index: int = 0

    @property
    def demo_mode(self) -> bool:
        return self._demo_mode

    @property
    def current_source(self) -> str:
        return self._demo_source if self._demo_mode else str(self._current_source)

    def start(self, source: str | int | None = None):
        """카메라 캡처 시작"""
        if self._running:
            return

        # 이전 스레드가 완전히 종료되었는지 확인 (좀비 스레드 방지)
        if self._thread and self._thread.is_alive():
            logger.warning("[%s] 이전 캡처 스레드가 아직 실행 중, 종료 대기...", self.camera_id)
            self._thread.join(timeout=5.0)
            if self._thread.is_alive():
                logger.error("[%s] 이전 스레드 종료 실패, 재시작 중단", self.camera_id)
                return
        self._thread = None

        if source is not None:
            self._current_source = source
            if isinstance(source, str) and source.isdigit():
                self._capture = cv2.VideoCapture(int(source))
            else:
                self._capture = cv2.VideoCapture(source)
        elif self._current_source != "":
            # 이전에 사용하던 소스로 재시작 (카메라 재시작 시 source 유실 방지)
            prev = self._current_source
            if isinstance(prev, str) and prev.isdigit():
                self._capture = cv2.VideoCapture(int(prev))
            elif isinstance(prev, int):
                self._capture = cv2.VideoCapture(prev)
            else:
                self._capture = cv2.VideoCapture(prev)
        else:
            # 최초 시작: 기본 소스 사용
            cam_source = settings.CAMERA_SOURCE
            if cam_source:
                self._capture = cv2.VideoCapture(cam_source)
                self._current_source = cam_source
            else:
                idx = settings.CAMERA_INDEX
                self._capture = cv2.VideoCapture(idx)
                self._current_source = idx

        if not self._capture.isOpened():
            logger.warning("[%s] 카메라 열기 실패 (source=%s)", self.camera_id, self._current_source)
            self._capture = None
            return

        self._capture.set(cv2.CAP_PROP_FRAME_WIDTH, settings.CAMERA_WIDTH)
        self._capture.set(cv2.CAP_PROP_FRAME_HEIGHT, settings.CAMERA_HEIGHT)
        self._capture.set(cv2.CAP_PROP_FPS, 30)

        self.frame_width = int(self._capture.get(cv2.CAP_PROP_FRAME_WIDTH))
        self.frame_height = int(self._capture.get(cv2.CAP_PROP_FRAME_HEIGHT))

        # 데모 영상 파일인 경우 (source가 None이면 _current_source로 판별)
        self._demo_mode = False
        effective_source = source if source is not None else self._current_source
        if isinstance(effective_source, str) and not effective_source.isdigit() and self._capture:
            total_frames = int(self._capture.get(cv2.CAP_PROP_FRAME_COUNT))
            if total_frames > 30:  # 파일 기반 소스 (프레임 수가 있으면 파일)
                self._demo_mode = True
                self._demo_source = effective_source
                # 플레이리스트 모드에서는 오프셋 불필요 (영상이 이미 다름)
                if not self._playlist:
                    # 단일 영상 반복 시 카메라별 시작 위치 오프셋 (동시 낙상 방지)
                    try:
                        cam_idx = int(self.camera_id.replace("cam", ""))
                    except ValueError:
                        cam_idx = 0
                    offset_ratio = (cam_idx * 0.25) % 1.0
                    offset_frame = int(total_frames * offset_ratio)
                    if offset_frame > 0:
                        self._capture.set(cv2.CAP_PROP_POS_FRAMES, offset_frame)
                        logger.info("[%s] 데모 영상 시작 오프셋: %d/%d (%.0f%%)",
                                    self.camera_id, offset_frame, total_frames, offset_ratio * 100)

        self._running = True
        self.is_active = True
        self._thread = threading.Thread(
            target=self._capture_loop, daemon=True, name=f"cam-{self.camera_id}"
        )
        self._thread.start()
        logger.info("[%s] 카메라 시작 (source=%s, %dx%d)", self.camera_id, self._current_source, self.frame_width, self.frame_height)

    def start_demo(self, video_path: str) -> bool:
        """데모 영상 재생 시작"""
        self.stop()

        if not os.path.isfile(video_path):
            logger.error("[%s] 데모 영상 파일 없음: %s", self.camera_id, video_path)
            return False

        self._capture = cv2.VideoCapture(video_path)
        if not self._capture.isOpened():
            logger.error("[%s] 데모 영상 열기 실패: %s", self.camera_id, video_path)
            self._capture = None
            return False

        self.frame_width = int(self._capture.get(cv2.CAP_PROP_FRAME_WIDTH))
        self.frame_height = int(self._capture.get(cv2.CAP_PROP_FRAME_HEIGHT))

        self._running = True
        self.is_active = True
        self._demo_mode = True
        self._demo_source = video_path
        self._switch_requested = False
        self._thread = threading.Thread(
            target=self._capture_loop, daemon=True, name=f"cam-{self.camera_id}"
        )
        self._thread.start()
        logger.info("[%s] 데모 모드 시작: %s (%dx%d)", self.camera_id, video_path, self.frame_width, self.frame_height)
        return True

    def switch_demo(self, video_path: str) -> bool:
        """데모 영상 실시간 전환"""
        if not os.path.isfile(video_path):
            logger.error("[%s] 전환 대상 영상 파일 없음: %s", self.camera_id, video_path)
            return False
        with self._lock:
            self._switch_source = video_path
            self._switch_requested = True
        logger.info("[%s] 데모 영상 전환 요청: %s", self.camera_id, video_path)
        return True

    def stop(self):
        """카메라 캡처 중지"""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5.0)
            if self._thread.is_alive():
                logger.warning("[%s] 캡처 스레드 종료 타임아웃 (5초)", self.camera_id)
            self._thread = None
        if self._capture:
            self._capture.release()
            self._capture = None
        self.is_active = False
        self._demo_mode = False
        self._demo_source = ""

        # 오래된 프레임 데이터 초기화 (재시작 시 정지 화면 방지)
        with self._jpeg_lock:
            self._latest_jpeg = None
        # 큐에 남은 오래된 프레임 비우기
        while not self.frame_queue.empty():
            try:
                self.frame_queue.get_nowait()
            except Exception:
                break

    def _capture_loop(self):
        """카메라 프레임 캡처 루프 (별도 스레드)"""
        frame_count = 0
        start_time = time.time()
        video_fps = 30.0

        if self._capture:
            video_fps = self._capture.get(cv2.CAP_PROP_FPS) or 30.0

        while self._running and self._capture and self._capture.isOpened():
            # 데모 영상 전환 요청 처리
            with self._lock:
                if self._switch_requested:
                    self._switch_requested = False
                    new_source = self._switch_source
                    self._capture.release()
                    self._capture = cv2.VideoCapture(new_source)
                    if self._capture.isOpened():
                        self._demo_source = new_source
                        self.frame_width = int(self._capture.get(cv2.CAP_PROP_FRAME_WIDTH))
                        self.frame_height = int(self._capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
                        video_fps = self._capture.get(cv2.CAP_PROP_FPS) or 30.0
                        from app.services.fall_detector import fall_detector
                        from app.services.fall_classifier import fall_classifier
                        from app.services.alert_manager import alert_manager
                        fall_detector.reset_camera(self.camera_id)
                        fall_classifier.reset_camera(self.camera_id)
                        alert_manager.reset_camera(self.camera_id)
                        logger.info("[%s] 데모 영상 전환 완료: %s (%dx%d)", self.camera_id, new_source, self.frame_width, self.frame_height)
                    else:
                        logger.error("[%s] 전환 영상 열기 실패: %s", self.camera_id, new_source)
                        break

            ret, frame = self._capture.read()
            if not ret:
                if self._demo_mode:
                    # 플레이리스트 전환: 해당 카메라의 person만 리셋 (다른 카메라 보존)
                    # 이전: reset_all()로 모든 카메라 GRU 버퍼 초기화 → 감지율 하락
                    # 이후: reset_camera()로 해당 카메라만 → 다른 카메라 GRU 버퍼 보존
                    from app.services.fall_detector import fall_detector
                    from app.services.fall_classifier import fall_classifier
                    # 플레이리스트 전환 시 감지 상태만 리셋, 알림 상태는 보존
                    # alert_manager를 리셋하면 MONITORING/WARNING 중 끊겨서 낙상 미감지
                    fall_detector.reset_camera(self.camera_id)
                    fall_classifier.reset_camera(self.camera_id)

                    if self._playlist and len(self._playlist) > 1:
                        self._playlist_index = (self._playlist_index + 1) % len(self._playlist)
                        next_source = self._playlist[self._playlist_index]
                        self._capture.release()
                        self._capture = cv2.VideoCapture(next_source)
                        if self._capture.isOpened():
                            self._demo_source = next_source
                            self.frame_width = int(self._capture.get(cv2.CAP_PROP_FRAME_WIDTH))
                            self.frame_height = int(self._capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
                            video_fps = self._capture.get(cv2.CAP_PROP_FPS) or 30.0
                            logger.info("[%s] 플레이리스트 전환 [%d/%d]: %s",
                                        self.camera_id, self._playlist_index + 1,
                                        len(self._playlist), Path(next_source).name)
                        else:
                            logger.error("[%s] 플레이리스트 영상 열기 실패: %s", self.camera_id, next_source)
                            # 다음 영상으로 스킵
                            continue
                    else:
                        # 단일 영상 반복 재생
                        self._capture.set(cv2.CAP_PROP_POS_FRAMES, 0)
                        logger.info("[%s] 데모 영상 반복 재생: %s", self.camera_id, self._demo_source)
                    continue
                else:
                    time.sleep(0.01)
                    continue

            # 고해상도 프레임 리사이즈
            h, w = frame.shape[:2]
            _TARGET_WIDTH = 640
            if w > _TARGET_WIDTH:
                scale = _TARGET_WIDTH / w
                frame = cv2.resize(frame, (int(w * scale), int(h * scale)),
                                   interpolation=cv2.INTER_AREA)

            # 큐에 프레임 추가
            try:
                self.frame_queue.put_nowait(frame)
            except Full:
                try:
                    self.frame_queue.get_nowait()
                except Exception:
                    pass
                try:
                    self.frame_queue.put_nowait(frame)
                except Exception:
                    pass

            # MJPEG용 JPEG 인코딩
            _, jpeg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 50])
            with self._jpeg_lock:
                self._latest_jpeg = jpeg.tobytes()

            # FPS 계산
            frame_count += 1
            elapsed = time.time() - start_time
            if elapsed >= 1.0:
                self.fps = frame_count / elapsed
                frame_count = 0
                start_time = time.time()

            # 프레임 레이트 제한 (speed 배율 적용)
            if self._demo_mode and video_fps > 0:
                base_delay = 1.0 / video_fps
                speed = max(self._speed, 0.1)  # 최소 0.1배속
                adjusted_delay = base_delay / speed
                time.sleep(max(adjusted_delay - 0.005, 0.005))
            else:
                time.sleep(0.015)

        self.is_active = False

    def get_latest_jpeg(self) -> bytes | None:
        """MJPEG 스트리밍용 최신 JPEG 프레임"""
        with self._jpeg_lock:
            return self._latest_jpeg

    def update_jpeg_from_processed(self, frame: np.ndarray):
        """포즈 검출 결과가 오버레이된 프레임으로 JPEG 업데이트"""
        _, jpeg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 50])
        with self._jpeg_lock:
            self._latest_jpeg = jpeg.tobytes()


class CameraManager:
    """다중 카메라 관리자 (기존 CameraService 대체, 하위 호환 유지)

    MULTI_CAMERA_ENABLED=False일 때: 기존 단일 카메라와 동일하게 동작
    MULTI_CAMERA_ENABLED=True일 때: 다중 카메라 동시 운영
    """

    def __init__(self):
        self._cameras: dict[str, CameraInstance] = {}
        self._default_id = "cam0"
        # 기본 카메라 인스턴스 생성
        self._cameras[self._default_id] = CameraInstance(self._default_id, "기본 카메라")

    # --- 기본(디폴트) 카메라 접근 ---

    @property
    def default(self) -> CameraInstance:
        """기본 카메라 인스턴스"""
        return self._cameras[self._default_id]

    # --- 하위 호환 프로퍼티 (기존 CameraService 인터페이스 유지) ---

    @property
    def frame_queue(self) -> Queue:
        return self.default.frame_queue

    @property
    def is_active(self) -> bool:
        return self.default.is_active

    @property
    def fps(self) -> float:
        return self.default.fps

    @property
    def frame_width(self) -> int:
        return self.default.frame_width

    @property
    def frame_height(self) -> int:
        return self.default.frame_height

    @property
    def demo_mode(self) -> bool:
        return self.default.demo_mode

    @property
    def current_camera_index(self) -> int:
        src = self.default._current_source
        if isinstance(src, int):
            return src
        if isinstance(src, str) and src.isdigit():
            return int(src)
        return 0

    @property
    def current_source(self) -> str:
        return self.default.current_source

    # --- 하위 호환 메서드 (기본 카메라에 위임) ---

    def start(self, camera_index: int | None = None):
        """기본 카메라 시작"""
        if camera_index is not None:
            self.default.start(camera_index)
        else:
            self.default.start()

    def start_demo(self, video_path: str) -> bool:
        return self.default.start_demo(video_path)

    def switch_demo(self, video_path: str) -> bool:
        return self.default.switch_demo(video_path)

    def stop(self):
        self.default.stop()

    def get_latest_jpeg(self) -> bytes | None:
        return self.default.get_latest_jpeg()

    def update_jpeg_from_processed(self, frame: np.ndarray):
        self.default.update_jpeg_from_processed(frame)

    def list_available_cameras(self, max_index: int = 10) -> list[dict]:
        """시스템에서 사용 가능한 카메라 목록 탐색

        Windows에서 동일 디바이스가 여러 인덱스에 나타나는 문제를 방지하기 위해
        첫 프레임 해시를 비교하여 중복을 제거합니다.
        """
        import hashlib

        current_idx = self.current_camera_index
        active = self.is_active
        cameras = []
        seen_hashes: set[str] = set()

        for i in range(max_index):
            if active and i == current_idx:
                # 현재 활성 카메라: 프레임 해시를 기록
                frame_hash = ""
                jpeg = self.get_latest_jpeg()
                if jpeg:
                    frame_hash = hashlib.md5(jpeg).hexdigest()[:16]
                    seen_hashes.add(frame_hash)
                cameras.append({
                    "index": i,
                    "name": f"Camera {i}",
                    "resolution": f"{self.frame_width}x{self.frame_height}",
                    "backend": "ACTIVE",
                    "is_current": True,
                })
                continue
            cap = cv2.VideoCapture(i)
            if cap.isOpened():
                w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                backend = cap.getBackendName()
                # 첫 프레임으로 중복 디바이스 검사
                ret, frame = cap.read()
                cap.release()
                if ret and frame is not None:
                    _, jpeg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 50])
                    frame_hash = hashlib.md5(jpeg.tobytes()).hexdigest()[:16]
                    if frame_hash in seen_hashes:
                        logger.debug("Camera %d 중복 디바이스 (hash=%s), 건너뜀", i, frame_hash)
                        continue
                    seen_hashes.add(frame_hash)
                cameras.append({
                    "index": i,
                    "name": f"Camera {i}",
                    "resolution": f"{w}x{h}",
                    "backend": backend,
                    "is_current": False,
                })
        return cameras

    def switch_camera(self, camera_index: int) -> bool:
        """런타임 카메라 전환"""
        from app.services.monitoring_orchestrator import monitoring_orchestrator
        from app.services.fall_detector import fall_detector
        monitoring_orchestrator.pause()
        self.stop()
        fall_detector.reset_all()
        self.default._current_source = camera_index
        self.start(camera_index=camera_index)
        monitoring_orchestrator.resume()
        return self.is_active

    @staticmethod
    def list_demo_videos() -> list[dict]:
        """데모 영상 목록 반환"""
        demo_dir = settings.DEMO_VIDEO_DIR
        if not demo_dir or not os.path.isdir(demo_dir):
            return []

        videos = []
        extensions = {".mp4", ".avi", ".mov", ".mkv", ".webm"}
        for f in sorted(Path(demo_dir).iterdir()):
            if f.suffix.lower() in extensions and f.is_file():
                name = f.stem
                category = _infer_category(name)
                videos.append({
                    "filename": f.name,
                    "path": str(f),
                    "category": category,
                    "size_mb": round(f.stat().st_size / (1024 * 1024), 1),
                })
        return videos

    # --- 다중 카메라 API ---

    def get(self, camera_id: str) -> CameraInstance | None:
        """카메라 ID로 인스턴스 조회"""
        return self._cameras.get(camera_id)

    def add_camera(self, camera_id: str, name: str = "", source: str | int = "") -> CameraInstance:
        """카메라 추가 (이미 존재하면 이름 업데이트 후 반환)"""
        if camera_id in self._cameras:
            if name:
                self._cameras[camera_id].name = name
            return self._cameras[camera_id]
        cam = CameraInstance(camera_id, name)
        self._cameras[camera_id] = cam
        logger.info("[CameraManager] 카메라 추가: %s (%s)", camera_id, name)
        return cam

    def remove_camera(self, camera_id: str) -> bool:
        """카메라 제거 (기본 카메라는 제거 불가)"""
        if camera_id == self._default_id:
            logger.warning("기본 카메라(cam0)는 제거할 수 없습니다")
            return False
        cam = self._cameras.pop(camera_id, None)
        if cam:
            cam.stop()
            logger.info("[CameraManager] 카메라 제거: %s", camera_id)
            return True
        return False

    def active_cameras(self) -> list[tuple[str, CameraInstance]]:
        """활성 카메라 목록 반환 (camera_id, instance) 튜플"""
        return [(cid, cam) for cid, cam in self._cameras.items() if cam.is_active]

    def all_cameras(self) -> dict[str, CameraInstance]:
        """모든 카메라 인스턴스 반환"""
        return dict(self._cameras)

    def stop_all(self):
        """모든 카메라 중지"""
        for cam in self._cameras.values():
            cam.stop()
        logger.info("[CameraManager] 모든 카메라 중지 (%d대)", len(self._cameras))


def _infer_category(filename: str) -> str:
    """파일명에서 낙상 유형 추론"""
    upper = filename.upper()
    if upper.startswith("N_") or "NORMAL" in upper:
        return "normal"
    elif upper.startswith("FY") or "FRONT_FALL" in upper:
        return "front_fall"
    elif upper.startswith("BY") or "BACK_FALL" in upper:
        return "back_fall"
    elif upper.startswith("SY") or "SIDE_FALL" in upper:
        return "side_fall"
    elif "PRE" in upper or "ABNORMAL" in upper:
        return "pre_impact"
    return "unknown"


# 싱글턴 인스턴스 (변수명 유지 → import 변경 불필요)
camera_service = CameraManager()
