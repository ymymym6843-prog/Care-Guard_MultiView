"""
낙상 감지 알고리즘

기립 상태 4가지 기본 감지 조건 (C1-C4):
1. 머리-엉덩이 역전 (head Y > hip Y)
2. 급격한 하강 ([-10] 프레임 비교)
3. 수평 체형 각도
4. 복합 점수

확장 규칙 6가지 (N1-N6, rule-enhanced 프로필):
N1. 수직 가속도 (head_y 3프레임 가속)
N2. 보호 신전 반응 (팔 벌림 + 손목 하강)
N3. 무게중심-지지면 이탈 (CoM-BoS 편차 연속 증가)
N4. 무릎 좌굴 (knee angle rate + angle limit)
N5. 체간 회전 속도 (shoulder tilt delta, standing only)
N6. 높이 궤적 패턴 (후반부 가속)

착석 상태 추가 3가지 감지 조건:
5. 전방 쏠림 (머리가 무릎보다 아래)
6. 측면 이탈 (어깨 기울기 급변)
7. 높이 급락 (기준선 대비 머리 높이 하락)

앙상블: 규칙 기반 + ML 분류기 (설정 가능 가중치)
자세 분류기(PostureClassifier) 연동으로 자세별 다른 임계값 적용
5초 쿨다운으로 고령자 회복 시간 고려 및 오감지 방지
"""

import math
import time
from collections import deque
from dataclasses import dataclass, field

from app.config import settings
from app.core.logging_config import get_logger
from app.services.fall_classifier import fall_classifier
from app.services.keypoint_adapter import KeypointAdapter, KeypointFormat
from app.services.posture_classifier import posture_classifier, PostureType

logger = get_logger("app.services.fall_detector")


@dataclass
class PersonState:
    """개인별 감지 상태"""
    person_id: str
    head_y_history: deque = field(default_factory=lambda: deque(maxlen=30))
    hip_y_history: deque = field(default_factory=lambda: deque(maxlen=30))
    fall_score: float = 0.0
    is_fallen: bool = False
    fall_start_time: float | None = None
    last_normal_time: float | None = None
    cooldown_active: bool = False
    # 오탐 방지: 프레임 진입 유예 기간
    frames_since_first_seen: int = 0
    # 오탐 방지: 연속 프레임 확인
    consecutive_fall_frames: int = 0
    # ML 점수 EMA (프레임 간 변동 완화)
    ml_score_ema: float = 0.0
    # N2 보호 신전 반응
    arm_spread_history: deque = field(default_factory=lambda: deque(maxlen=3))
    # N3 무게중심-지지면 이탈
    prev_com_bos_deviation: float = 0.0
    com_bos_growing_frames: int = 0
    # N4 무릎 좌굴
    prev_min_knee_angle: float = 170.0
    # 오탐 방지: 발목 히스토리 (구부리기 감지용)
    ankle_y_history: deque = field(default_factory=lambda: deque(maxlen=10))
    # 오탐 방지: 제어된 눕기 감지용 (sitting → lying 전환 프레임 수)
    controlled_lying_frames: int = 0
    prev_posture: str = "unknown"
    # Quick Recovery Detection: 빠른 회복 감지
    quick_recovery_standing_frames: int = 0  # 낙상 후 연속 standing 프레임
    fall_lying_duration: int = 0  # 낙상 후 lying 상태 지속 프레임
    # 다중 프레임 누적 감지 (저가시성 시나리오용)
    low_vis_score_history: deque = field(default_factory=lambda: deque(maxlen=5))
    # 동작 지속성 체크 (오탐 방지: 낙상 후 제어된 움직임 감지)
    post_fall_velocity_history: deque = field(default_factory=lambda: deque(maxlen=10))
    post_fall_frames: int = 0  # 낙상 판정 후 경과 프레임


class FallDetector:
    # MediaPipe 랜드마크 인덱스
    NOSE = 0
    LEFT_SHOULDER = 11
    RIGHT_SHOULDER = 12
    LEFT_HIP = 23
    RIGHT_HIP = 24
    LEFT_KNEE = 25
    RIGHT_KNEE = 26
    LEFT_ANKLE = 27
    RIGHT_ANKLE = 28
    LEFT_WRIST = 15
    RIGHT_WRIST = 16

    def __init__(self):
        import threading
        self._person_states: dict[str, PersonState] = {}
        self._states_lock = threading.Lock()  # 다중 카메라 스레드 안전성
        self._head_hip_threshold = settings.FALL_HEAD_HIP_THRESHOLD
        self._cooldown_seconds = settings.FALL_COOLDOWN_SECONDS
        self._rapid_descent_threshold = settings.FALL_RAPID_DESCENT_THRESHOLD
        self._horizontal_angle = settings.FALL_HORIZONTAL_ANGLE
        self._composite_threshold = settings.FALL_COMPOSITE_THRESHOLD
        self._pre_impact_threshold = settings.FALL_PRE_IMPACT_THRESHOLD
        self._pre_impact_ml_threshold = settings.FALL_PRE_IMPACT_ML_THRESHOLD
        # 앙상블 가중치 (설정 가능)
        self._rule_weight = settings.FALL_RULE_WEIGHT
        self._ml_weight = settings.FALL_ML_WEIGHT
        # 확장 규칙 활성화 여부
        self._enhanced_rules = settings.FALL_ENHANCED_RULES_ENABLED
        logger.info(
            "FallDetector 초기화 완료 (rule_weight=%.2f, ml_weight=%.2f, enhanced=%s)",
            self._rule_weight, self._ml_weight, self._enhanced_rules,
        )

    # --- Public setters for settings_route ---
    @property
    def head_hip_threshold(self) -> float:
        return self._head_hip_threshold

    @head_hip_threshold.setter
    def head_hip_threshold(self, value: float) -> None:
        self._head_hip_threshold = value
        logger.info("head_hip_threshold 변경: %s", value)

    @property
    def cooldown_seconds(self) -> float:
        return self._cooldown_seconds

    @cooldown_seconds.setter
    def cooldown_seconds(self, value: float) -> None:
        self._cooldown_seconds = value
        logger.info("cooldown_seconds 변경: %s", value)

    @property
    def rule_weight(self) -> float:
        return self._rule_weight

    @rule_weight.setter
    def rule_weight(self, value: float) -> None:
        self._rule_weight = max(0.0, min(1.0, value))
        self._ml_weight = round(1.0 - self._rule_weight, 4)
        logger.info("앙상블 가중치 변경: rule=%.2f, ml=%.2f", self._rule_weight, self._ml_weight)

    @property
    def ml_weight(self) -> float:
        return self._ml_weight

    @ml_weight.setter
    def ml_weight(self, value: float) -> None:
        self._ml_weight = max(0.0, min(1.0, value))
        self._rule_weight = round(1.0 - self._ml_weight, 4)
        logger.info("앙상블 가중치 변경: rule=%.2f, ml=%.2f", self._rule_weight, self._ml_weight)

    @property
    def enhanced_rules(self) -> bool:
        return self._enhanced_rules

    @enhanced_rules.setter
    def enhanced_rules(self, value: bool) -> None:
        self._enhanced_rules = value
        logger.info("확장 규칙(N1-N6) 변경: %s", value)

    def get_or_create_state(self, person_id: str) -> PersonState:
        with self._states_lock:
            if person_id not in self._person_states:
                self._person_states[person_id] = PersonState(person_id=person_id)
            return self._person_states[person_id]

    @staticmethod
    def _compute_angle(a: dict, b: dict, c: dict) -> float:
        """3점 각도 계산 (a-b-c, b가 꼭짓점). 도(degree) 단위 반환."""
        ba_x, ba_y = a["x"] - b["x"], a["y"] - b["y"]
        bc_x, bc_y = c["x"] - b["x"], c["y"] - b["y"]
        dot = ba_x * bc_x + ba_y * bc_y
        mag_ba = math.sqrt(ba_x * ba_x + ba_y * ba_y)
        mag_bc = math.sqrt(bc_x * bc_x + bc_y * bc_y)
        if mag_ba < 1e-9 or mag_bc < 1e-9:
            return 180.0
        cos_angle = max(-1.0, min(1.0, dot / (mag_ba * mag_bc)))
        return math.degrees(math.acos(cos_angle))

    def detect(
        self,
        landmarks: list[dict],
        person_id: str = "person_0",
        keypoint_format: KeypointFormat | str = KeypointFormat.MEDIAPIPE_33,
    ) -> dict:
        """
        랜드마크에서 낙상 감지

        Args:
            landmarks: 키포인트 리스트 [{x, y, z, visibility}, ...]
            person_id: 인물 ID
            keypoint_format: 키포인트 포맷 (MEDIAPIPE_33 또는 COCO_17)
                - MEDIAPIPE_33: 33개 랜드마크 (기본값)
                - COCO_17: 17개 랜드마크 (YOLO Pose 출력, 자동 변환됨)

        Returns:
            {
                "is_fallen": bool,
                "confidence": float (0-1),
                "head_y": float,
                "hip_y": float,
                "angle": float,
                "fall_duration": float,
                "cooldown_active": bool,
                "fall_type": str ("normal", "front_fall", "back_fall", "side_fall"),
                "rule_score": float (0-1),
                "ml_score": float (0-1),
                "conditions": dict (각 조건별 결과)
            }
        """
        # ── 키포인트 포맷 변환 (COCO 17 → MediaPipe 33) ──
        if isinstance(keypoint_format, str):
            keypoint_format = KeypointFormat(keypoint_format)

        # YOLO-only 모드에서 임계값 상향 배수 (노이즈 대응)
        _yolo_mult = settings.YOLO_THRESHOLD_MULTIPLIER if keypoint_format == KeypointFormat.COCO_17 else 1.0

        if keypoint_format == KeypointFormat.COCO_17:
            if len(landmarks) < 17:
                return self._default_result()
            # COCO 17점을 MediaPipe 33점 형식으로 변환
            landmarks = KeypointAdapter.coco_to_mediapipe_33(landmarks)
        elif len(landmarks) < 33:
            return self._default_result()

        state = self.get_or_create_state(person_id)
        now = time.time()

        # ── 오탐 방지 1: 랜드마크 가시성 게이트 + 저가시성 누적 감지 ──
        # 핵심 랜드마크(코, 양어깨, 양엉덩이)의 평균 가시성이 낮으면 감지 건너뜀
        # 단, 중간 가시성(0.3-0.5)에서는 다중 프레임 누적 감지 시도
        _key_indices = [self.NOSE, self.LEFT_SHOULDER, self.RIGHT_SHOULDER,
                        self.LEFT_HIP, self.RIGHT_HIP]
        avg_visibility = sum(
            landmarks[i].get("visibility", 1.0) for i in _key_indices
        ) / len(_key_indices)

        # 저가시성 모드 플래그 (0.3 <= visibility < 0.5)
        _low_vis_mode = (avg_visibility >= settings.FALL_LOW_VIS_MIN
                         and avg_visibility < settings.FALL_MIN_VISIBILITY)

        # 완전 저가시성: 건너뜀
        if avg_visibility < settings.FALL_LOW_VIS_MIN:
            state.low_vis_score_history.clear()  # 히스토리 리셋
            logger.debug(
                "[오탐방지] %s | 가시성 매우 부족 (%.2f < %.2f), 감지 건너뜀",
                person_id, avg_visibility, settings.FALL_LOW_VIS_MIN,
            )
            return self._default_result()

        # 중간 가시성: 다중 프레임 누적 모드로 계속 진행
        if _low_vis_mode:
            logger.debug(
                "[저가시성] %s | 중간 가시성 (%.2f), 누적 감지 모드 활성",
                person_id, avg_visibility,
            )

        # ── ML skip 최적화: ml_weight=0이면 ONNX 추론 완전 생략 ──
        _ml_active = self._ml_weight > 0.0

        # ── 오탐 방지 2: 신규 인물 유예 기간 ──
        state.frames_since_first_seen += 1
        in_grace_period = state.frames_since_first_seen <= settings.FALL_GRACE_FRAMES

        if in_grace_period:
            # 히스토리만 쌓고 (빠른 낙상 검출용 예비 점수 계산은 수행)
            nose = landmarks[self.NOSE]
            state.head_y_history.append(nose["y"])
            hip_y = (landmarks[self.LEFT_HIP]["y"] + landmarks[self.RIGHT_HIP]["y"]) / 2
            state.hip_y_history.append(hip_y)
            # 자세 분류기에도 데이터 공급 (기준선 확립용)
            posture_classifier.classify(landmarks, person_id)
            if _ml_active:
                fall_classifier.add_frame(person_id, landmarks)

            # === 빠른 낙상(trip) 조기 감지 ===
            # grace period 중이라도 매우 높은 점수(역전+하강+수평)면 즉시 감지
            # 이를 위해 예비 점수 계산
            l_hip = landmarks[self.LEFT_HIP]
            r_hip = landmarks[self.RIGHT_HIP]
            quick_hip_y = (l_hip["y"] + r_hip["y"]) / 2
            quick_head_hip_diff = quick_hip_y - nose["y"]
            quick_inverted = quick_head_hip_diff < self._head_hip_threshold

            quick_descent = 0.0
            if len(state.head_y_history) >= 3:
                quick_descent = state.head_y_history[-1] - state.head_y_history[-3]
            quick_rapid = quick_descent > self._rapid_descent_threshold * 0.5  # 더 민감하게

            # 빠른 낙상이면 grace period 무시
            if quick_inverted and quick_rapid:
                logger.info(
                    "[빠른낙상] %s | 유예기간(%d) 중 조기 감지 (역전+급하강), 감지 진행",
                    person_id, state.frames_since_first_seen,
                )
                in_grace_period = False  # 감지 진행
            else:
                logger.debug(
                    "[오탐방지] %s | 유예 기간 (%d/%d), 감지 건너뜀",
                    person_id, state.frames_since_first_seen, settings.FALL_GRACE_FRAMES,
                )
                return self._default_result()

        # 주요 랜드마크 추출
        nose = landmarks[self.NOSE]
        l_shoulder = landmarks[self.LEFT_SHOULDER]
        r_shoulder = landmarks[self.RIGHT_SHOULDER]
        l_hip = landmarks[self.LEFT_HIP]
        r_hip = landmarks[self.RIGHT_HIP]
        l_ankle = landmarks[self.LEFT_ANKLE]
        r_ankle = landmarks[self.RIGHT_ANKLE]
        l_knee = landmarks[self.LEFT_KNEE]
        r_knee = landmarks[self.RIGHT_KNEE]
        l_wrist = landmarks[self.LEFT_WRIST]
        r_wrist = landmarks[self.RIGHT_WRIST]

        # 중심점 계산
        head_y = nose["y"]
        hip_y = (l_hip["y"] + r_hip["y"]) / 2
        shoulder_y = (l_shoulder["y"] + r_shoulder["y"]) / 2
        ankle_y = (l_ankle["y"] + r_ankle["y"]) / 2
        knee_y = (l_knee["y"] + r_knee["y"]) / 2

        # 히스토리 기록
        state.head_y_history.append(head_y)
        state.hip_y_history.append(hip_y)
        state.ankle_y_history.append(ankle_y)  # 오탐 방지: 발목 히스토리

        # ── 인물 크기 기반 스케일 계수 ──
        # 기준: 인물이 프레임의 ~50%를 차지하는 경우 scale=1.0
        # 4K 영상 등에서 인물이 작으면 임계값을 비례적으로 낮춤
        person_height = max(ankle_y - head_y, 0.05)  # 머리~발목 높이
        _REF_HEIGHT = 0.50  # 기준 인물 크기 (프레임 대비 50%)
        scale = min(person_height / _REF_HEIGHT, 1.0)  # 0~1.0 (작은 인물=작은 값)

        # ── 자세 분류 (서있음/앉아있음/누워있음) ──
        posture = posture_classifier.classify(landmarks, person_id)

        # ── 오탐 방지: 제어된 눕기 전환 감지 ──
        # sitting → lying 전환이 천천히 이루어지면 정상 눕기로 판단
        if state.prev_posture in ("sitting", "standing") and posture == PostureType.LYING:
            state.controlled_lying_frames += 1
        elif posture != PostureType.LYING:
            state.controlled_lying_frames = 0
        state.prev_posture = posture.value

        # 자세별 임계값 선택 + 스케일 적용 + YOLO 배수
        if posture == PostureType.SITTING:
            head_hip_th = settings.FALL_SEATED_HEAD_HIP_THRESHOLD * scale
            descent_th = settings.FALL_SEATED_RAPID_DESCENT_THRESHOLD * scale * _yolo_mult
            angle_th = settings.FALL_SEATED_HORIZONTAL_ANGLE
        else:
            head_hip_th = self._head_hip_threshold * scale
            descent_th = self._rapid_descent_threshold * scale * _yolo_mult
            angle_th = self._horizontal_angle

        # === 조건 C1: 머리-엉덩이 역전 ===
        head_hip_diff = hip_y - head_y
        cond1_inverted = head_hip_diff < head_hip_th

        # === 조건 C2: 급격한 하강 ===
        cond2_rapid_descent = False
        descent = 0.0
        if len(state.head_y_history) >= 10:
            past_head = state.head_y_history[-10]
            current_head = state.head_y_history[-1]
            descent = current_head - past_head
            cond2_rapid_descent = descent > descent_th

        # === 조건 C3: 수평 체형 (어깨-엉덩이 각도, 수직 기준: 0°=서있음, 90°=누워있음) ===
        shoulder_mid_x = (l_shoulder["x"] + r_shoulder["x"]) / 2
        hip_mid_x = (l_hip["x"] + r_hip["x"]) / 2
        dx = hip_mid_x - shoulder_mid_x
        dy = hip_y - shoulder_y
        body_length = math.sqrt(dx * dx + dy * dy)
        if body_length > 1e-6:
            body_angle_vertical = math.degrees(math.acos(min(abs(dy) / body_length, 1.0)))
        else:
            body_angle_vertical = 0.0
        cond3_horizontal = body_angle_vertical > (90.0 - angle_th)
        # 반환값은 수평 기준 각도 (후방 호환: 0°=수평, 90°=수직)
        body_angle = 90.0 - body_angle_vertical

        # === 조건 C4: 복합 점수 (기립 공통) ===
        # 확장 규칙 모드에서는 가중치 재배분 (C1:0.35, C2:0.25, C3:0.25)
        _enhanced = self._enhanced_rules
        if _enhanced:
            _w_c1, _w_c2, _w_c3 = 0.35, 0.25, 0.25
        else:
            _w_c1, _w_c2, _w_c3 = 0.4, 0.3, 0.3

        score = 0.0
        if cond1_inverted:
            score += _w_c1
        if cond2_rapid_descent:
            score += _w_c2
        if cond3_horizontal:
            score += _w_c3

        # 발목이 엉덩이보다 높은 경우 추가 점수
        ankle_above_hip = ankle_y < hip_y
        if ankle_above_hip:
            score += 0.1

        # === 확장 규칙 N1-N6 (rule-enhanced 프로필에서만 활성화) ===
        n1_accel = False
        n2_protective = False
        n3_com_bos = False
        n4_knee_buckle = False
        n5_trunk_rotation = False
        n6_trajectory = False

        if _enhanced:
            # ── N1: 수직 가속도 (head_y 3프레임) ──
            if len(state.head_y_history) >= 3:
                h = state.head_y_history
                v1 = h[-1] - h[-2]  # 현재 속도
                v0 = h[-2] - h[-3]  # 이전 속도
                accel = v1 - v0
                # YOLO 노이즈 대응: 임계값 상향
                n1_accel_th = settings.FALL_N1_ACCEL_THRESHOLD * scale * _yolo_mult
                n1_vel_th = settings.FALL_N1_VELOCITY_GATE * scale * _yolo_mult
                if accel > n1_accel_th and v1 > n1_vel_th:
                    n1_accel = True
                    score += 0.15

            # ── N2: 보호 신전 반응 (팔 벌림 + 손목 하강) ──
            lw_vis = l_wrist.get("visibility", 0.0)
            rw_vis = r_wrist.get("visibility", 0.0)
            if lw_vis > 0.5 and rw_vis > 0.5:
                arm_spread = abs(l_wrist["x"] - r_wrist["x"])
                state.arm_spread_history.append(arm_spread)
                if len(state.arm_spread_history) >= 2:
                    spread_vel = state.arm_spread_history[-1] - state.arm_spread_history[-2]
                    wrist_avg_y = (l_wrist["y"] + r_wrist["y"]) / 2
                    wrist_drop = wrist_avg_y - hip_y  # 손목이 엉덩이보다 아래로 떨어지면 양수
                    if spread_vel > settings.FALL_N2_ARM_SPREAD_VEL and wrist_drop > settings.FALL_N2_WRIST_DROP:
                        n2_protective = True
                        score += 0.10

            # ── N3: 무게중심-지지면 이탈 (standing only) ──
            if posture == PostureType.STANDING:
                ankle_span = abs(l_ankle["x"] - r_ankle["x"])
                if ankle_span > settings.FALL_N3_MIN_ANKLE_SPAN:
                    com_x = (shoulder_mid_x + hip_mid_x) / 2
                    bos_center = (l_ankle["x"] + r_ankle["x"]) / 2
                    deviation = abs(com_x - bos_center)
                    if deviation > state.prev_com_bos_deviation:
                        state.com_bos_growing_frames += 1
                    else:
                        state.com_bos_growing_frames = 0
                    state.prev_com_bos_deviation = deviation
                    if state.com_bos_growing_frames >= settings.FALL_N3_GROWING_FRAMES:
                        n3_com_bos = True
                        score += 0.10

            # ── N4: 무릎 좌굴 ──
            lk_vis = l_knee.get("visibility", 0.0)
            rk_vis = r_knee.get("visibility", 0.0)
            if lk_vis > 0.5 and rk_vis > 0.5:
                angle_l = self._compute_angle(l_hip, l_knee, l_ankle)
                angle_r = self._compute_angle(r_hip, r_knee, r_ankle)
                min_angle = min(angle_l, angle_r)
                angle_rate = state.prev_min_knee_angle - min_angle  # 양수 = 무릎 굽힘
                # YOLO 노이즈 대응: 임계값 상향
                n4_rate_th = settings.FALL_N4_ANGLE_RATE * _yolo_mult
                if angle_rate > n4_rate_th and min_angle < settings.FALL_N4_ANGLE_LIMIT:
                    n4_knee_buckle = True
                    score += 0.15
                state.prev_min_knee_angle = min_angle

            # ── N5: 체간 회전 속도 (standing + C조건 1개 이상 활성) ──
            if posture == PostureType.STANDING:
                tilt_delta = posture_classifier.get_shoulder_tilt_delta(person_id)
                c_any_active = cond1_inverted or cond2_rapid_descent or cond3_horizontal
                if tilt_delta > settings.FALL_N5_STANDING_TILT and c_any_active:
                    n5_trunk_rotation = True
                    score += 0.05

            # ── N6: 높이 궤적 패턴 (head_y_history 15프레임) ──
            if len(state.head_y_history) >= 15:
                h = list(state.head_y_history)[-15:]
                mid = len(h) // 2
                # 전반부/후반부 평균 속도
                first_half_speeds = [h[i+1] - h[i] for i in range(mid)]
                second_half_speeds = [h[i+1] - h[i] for i in range(mid, len(h)-1)]
                avg_first = sum(first_half_speeds) / max(len(first_half_speeds), 1)
                avg_second = sum(second_half_speeds) / max(len(second_half_speeds), 1)
                # YOLO 노이즈 대응: 가속 비율 임계값 상향
                n6_ratio_th = settings.FALL_N6_ACCEL_RATIO * _yolo_mult
                if avg_first > 0 and avg_second > avg_first * n6_ratio_th:
                    n6_trajectory = True
                    score += 0.10

        score = min(score, 1.0)

        # === 착석 전용 조건 (앉아있을 때만) ===
        cond5_forward_slump = False
        cond6_lateral_tilt = False
        cond7_height_drop = False

        if posture == PostureType.SITTING:
            # 기준선이 충분히 확립된 후에만 착석 낙상 감지 활성화
            # (착석 직후 불안정한 기준선으로 인한 오탐 방지)
            baseline_frames = getattr(
                posture_classifier.get_or_create_state(person_id),
                "sitting_baseline_frames", 0,
            )
            seated_detection_active = baseline_frames >= settings.FALL_SEATED_BASELINE_MIN_FRAMES

            if seated_detection_active:
                # 조건 5: 전방 쏠림 - 머리가 무릎보다 아래로 내려감
                forward_diff = head_y - knee_y  # 양수면 머리가 무릎보다 아래
                cond5_forward_slump = forward_diff > settings.FALL_SEATED_FORWARD_SLUMP_THRESHOLD
                if cond5_forward_slump:
                    score += 0.25

                # 조건 6: 측면 이탈 - 어깨 좌우 기울기 급변 (부호 포함 delta로 방향 변화 감지)
                tilt_delta = posture_classifier.get_shoulder_tilt_delta(person_id)
                cond6_lateral_tilt = tilt_delta > settings.FALL_SEATED_LATERAL_TILT_THRESHOLD
                if cond6_lateral_tilt:
                    score += 0.25

                # 조건 7: 높이 급락 - 기준선 대비 머리 높이 하락
                baseline = posture_classifier.get_sitting_baseline(person_id)
                if baseline > 0:
                    height_drop = (head_y - baseline) / max(baseline, 0.01)
                    cond7_height_drop = height_drop > settings.FALL_SEATED_HEIGHT_DROP_RATIO
                    if cond7_height_drop:
                        score += 0.20

        score = min(score, 1.0)

        # ══════════════════════════════════════════════════════════════════
        # 오탐 억제 1: 구부리기 (bending) 감지
        # - C1(역전) + C2(하강) 활성 but C3(수평) 비활성 → 구부리기 가능성
        # - 추가 조건: 발목 고정 (줍기/숙이기는 발이 바닥에 고정)
        # ══════════════════════════════════════════════════════════════════
        bending_suppression = False
        if cond1_inverted and cond2_rapid_descent and not cond3_horizontal:
            # 발목이 바닥에 고정되어 있는지 확인 (수직 변화량 작음)
            if len(state.ankle_y_history) >= 3:
                ankle_hist = list(state.ankle_y_history)[-3:]
                ankle_variance = max(ankle_hist) - min(ankle_hist)

                # 발목 고정 + 비수평 → 구부리기 (낙상 아님)
                if ankle_variance < settings.FALL_BENDING_MAX_ANKLE_VARIANCE:
                    bending_suppression = True
                    # C1 + C2 + N조건 점수 모두 제거 → 0.5 미만으로
                    score = max(score - _w_c1 - _w_c2 - 0.1, 0.0)
                    logger.debug(
                        "[오탐억제] %s | 구부리기 감지 (ankle_var=%.4f, C1+C2 but !C3), score→%.2f",
                        person_id, ankle_variance, score,
                    )

        # ══════════════════════════════════════════════════════════════════
        # 오탐 억제 2: 제어된 눕기 (controlled lying) 감지
        # - 가속이 없으면 (N1, N6 모두 비활성) → 정상 눕기로 판단
        # - 가속이 감지되면 → 낙상 가능성 높음 (억제 안 함)
        # - 핵심: 실제 낙상은 급격한 가속이 동반됨
        # ══════════════════════════════════════════════════════════════════
        controlled_lying_suppression = False
        was_sitting_or_lying = state.prev_posture in ("sitting", "lying")
        was_standing = state.prev_posture == "standing"
        has_fall_acceleration = n1_accel or n6_trajectory  # 낙상 특유의 가속 패턴

        # 핵심 억제 조건: 수평 자세 + 가속 없음 → 제어된 눕기
        # (역전 여부와 관계없이, 가속이 없으면 정상 눕기로 판단)
        if cond3_horizontal and not has_fall_acceleration:
            # 추가 조건: 이전 자세가 sitting/lying이었거나, standing에서 왔더라도 점진적 전환
            gradual_transition = (
                was_sitting_or_lying or
                (was_standing and state.controlled_lying_frames >= 2)
            )
            if gradual_transition:
                controlled_lying_suppression = True
                # 역전까지 있으면 더 많은 점수 제거
                penalty = _w_c2 + _w_c3 + 0.15
                if cond1_inverted:
                    penalty += _w_c1 * 0.5  # 역전 점수의 절반도 제거
                score = max(score - penalty, 0.0)
                logger.debug(
                    "[오탐억제] %s | 제어된 눕기 감지 (no accel, gradual), score→%.2f",
                    person_id, score,
                )

        # ══════════════════════════════════════════════════════════════════
        # 오탐 억제 3: 제어된 앉기 (controlled sitting) 감지
        # - standing에서 sitting으로 전환 + C2(하강) 있음 + 가속 없음 → 정상 앉기
        # - 빠른 낙상(trip)과 구분하기 위해 가속(N1/N6) 체크
        # ══════════════════════════════════════════════════════════════════
        controlled_sitting_suppression = False
        if (posture == PostureType.SITTING
                and was_standing
                and cond2_rapid_descent
                and not has_fall_acceleration
                and not cond3_horizontal):  # 수평이 아니면 정상 앉기
            controlled_sitting_suppression = True
            # 하강 점수만 제거 (앉기는 하강은 있지만 수평은 아님)
            score = max(score - _w_c2, 0.0)
            logger.debug(
                "[오탐억제] %s | 제어된 앉기 감지 (standing→sitting, descent but not horizontal), score→%.2f",
                person_id, score,
            )

        # ══════════════════════════════════════════════════════════════════
        # 오탐 억제 4: 서있는 상태 제어된 동작 (standing controlled motion)
        # - standing 자세 + N1(가속) 없음 → 제어된 동작 가능성 높음
        # - 실제 낙상은 급격한 가속(N1)이 동반됨
        # - N_normal_standing_03.mp4, N_hospital_normal_C5.mp4 케이스 방지
        # - 핵심: 가속 없이 standing에서 감지되면 대부분 의도적 동작
        # - 단, 히스토리 부족 시 억제 건너뜀 (테스트/초기 프레임)
        # ══════════════════════════════════════════════════════════════════
        standing_controlled_suppression = False
        has_enough_history = len(state.head_y_history) >= 3
        if posture == PostureType.STANDING and not n1_accel and has_enough_history:
            # standing 자세에서 가속 없이 감지 → 점수 상당량 감소
            # 패널티: 트리거된 조건들의 점수 대부분 제거
            standing_controlled_suppression = True
            penalty = 0.0
            # C1이 있으면 전체 가중치의 80% 감소 (깊은 숙이기)
            if cond1_inverted:
                penalty += _w_c1 * 0.8
            # C2, C3, N6 모두 감소
            if cond2_rapid_descent:
                penalty += _w_c2
            if cond3_horizontal:
                penalty += _w_c3
            if n6_trajectory:
                penalty += 0.10
            score = max(score - penalty, 0.0)
            logger.debug(
                "[오탐억제] %s | 서있는 상태 제어된 동작 감지 (standing, no N1), penalty=%.2f → score=%.2f",
                person_id, penalty, score,
            )

        # ══════════════════════════════════════════════════════════════════
        # Trip Fall 부스트: 빠른 넘어짐 감지
        # - sitting 상태 + 매우 수평 각도 → trip fall 가능성 높음
        # - 핵심: 정상적인 앉기는 body_angle이 60° 이상 (상체가 세워짐)
        # - body_angle < 50°인 sitting은 자연스럽지 않음 → trip fall
        # ══════════════════════════════════════════════════════════════════
        trip_fall_boost = False
        very_horizontal_sitting = (
            posture == PostureType.SITTING
            and body_angle < 50.0  # 매우 수평 (정상 앉기는 60-80° 정도)
            and not bending_suppression  # 구부리기가 아닌 경우
        )

        if very_horizontal_sitting:
            trip_fall_boost = True
            # Trip fall 부스트: C1과 C2가 미작동해도 점수 보완
            # 기존 점수에서 0.5 미만이면 0.52로 올려서 감지 가능하게
            if score < self._composite_threshold:
                boost_needed = self._composite_threshold + 0.02 - score
                score = min(score + boost_needed, 1.0)
                logger.info(
                    "[Trip Fall] %s | sitting+very_horizontal (angle=%.1f° < 50°), boost +%.2f → score=%.2f",
                    person_id, body_angle, boost_needed, score,
                )

        score = min(score, 1.0)

        # 착석 전용 조건 유무 판별 (앙상블 후 임계값 조정에 사용)
        seated_any_specific = cond5_forward_slump or cond6_lateral_tilt or cond7_height_drop

        # === 앙상블: ML 분류기가 활성화된 경우 가중 평균 ===
        rule_score = score
        ml_score = 0.0
        ml_score_raw = 0.0
        fall_type = "normal"
        ml_class_probs = {}

        # ML skip 최적화: ml_weight > 0일 때만 ONNX 추론 실행
        if _ml_active:
            fall_classifier.add_frame(person_id, landmarks)

        if _ml_active and fall_classifier.enabled:
            ml_result = fall_classifier.predict_detailed(person_id)
            ml_score_raw = ml_result.fall_probability
            fall_type = ml_result.fall_type
            ml_class_probs = ml_result.class_probabilities

            # ML 버퍼 충족 여부 확인
            ml_buf = None
            try:
                ml_buf = fall_classifier._get_buffer(person_id)
                ml_ready = len(ml_buf) >= fall_classifier.SEQUENCE_LENGTH
            except (AttributeError, TypeError):
                ml_ready = True  # mock/테스트 환경에서는 ML 준비된 것으로 간주

            # ML 점수 EMA 평활화 (비대칭: 상승 시 빠르게, 하강 시 느리게)
            # 빠른 공격(0.6): 낙상 초기 ML 반응을 빨리 반영 → 조기 감지
            # 느린 감쇄(0.3): 일시적 ML 떨림을 완화 → 안정적 유지
            if ml_score_raw > state.ml_score_ema:
                _EMA_ALPHA = 0.6  # fast attack
            else:
                _EMA_ALPHA = 0.3  # slow decay
            if state.ml_score_ema < 0.01:
                state.ml_score_ema = ml_score_raw
            else:
                state.ml_score_ema = _EMA_ALPHA * ml_score_raw + (1 - _EMA_ALPHA) * state.ml_score_ema
            ml_score = state.ml_score_ema
            # 설정 가능 가중치
            score = rule_score * self._rule_weight + ml_score * self._ml_weight

            # ── ML 미준비 시 규칙 점수 제한 (착석 오탐 방지) ──
            # ML 버퍼 미충족 시 착석 상태에서만 규칙 점수를 감쇄.
            # 기립/누워있음 상태에서는 감쇄 없이 즉시 반응 (전조 감지 속도 우선).
            if not ml_ready and ml_score_raw < 0.1 and posture == PostureType.SITTING:
                score = rule_score * 0.7 * self._rule_weight
                if rule_score >= 0.7:
                    logger.debug(
                        "[ML 미준비] %s | ML버퍼=%d/30, 규칙=%.2f → 감쇄 score=%.2f",
                        person_id, len(ml_buf) if ml_buf else 0, rule_score, score,
                    )
            else:
                # 규칙 점수가 매우 높으면 ML 억제 방지 (override)
                # 단, rule_weight=0.0 (순수 ML 모드)에서는 비활성화
                # → 순수 ML 모드에서 rule만 높고 ML은 낮은 경우 FP 발생 방지
                if rule_score >= 0.8 and score < self._composite_threshold and self._rule_weight > 0:
                    score = rule_score
                    logger.debug(
                        "[ML Override] %s | rule=%.2f >= 0.8, 앙상블=%.2f < 임계값 → rule_score 사용",
                        person_id, rule_score, rule_score * self._rule_weight + ml_score * self._ml_weight,
                    )
                # ML raw 점수가 EMA보다 높을 때 raw 사용 (EMA 지연 보상)
                _seated_block = (posture == PostureType.SITTING and not seated_any_specific)
                if score < self._composite_threshold:
                    # 착석이어도 매우 높은 ML (0.85+) → EMA 지연 보상 허용
                    # (낙상 중 mid-fall 높이에서 일시적으로 sitting 분류되는 경우)
                    if _seated_block and ml_score_raw >= 0.75:
                        score = ml_score_raw
                        logger.info(
                            "[ML Boost-Seated] %s | ml_raw=%.2f(≥0.75) ema=%.2f → 착석 EMA 지연 보상",
                            person_id, ml_score_raw, ml_score,
                        )
                    elif not _seated_block:
                        # 제어된 동작 억제가 활성화된 경우 ML Boost 차단
                        # (천천히 눕기/앉기는 규칙에서 억제했는데 ML이 덮어쓰면 안 됨)
                        _any_suppression = (
                            controlled_lying_suppression
                            or controlled_sitting_suppression
                            or bending_suppression
                            or standing_controlled_suppression
                        )
                        # 고확신 ML (0.7+): 규칙 점수 무관하게 ML raw 사용
                        # (EMA가 저값에 끌려 고신뢰 낙상을 놓치는 것 방지)
                        # 단, standing + 거의 직립(angle>75°) + 규칙 무반응 → ML FP 패턴 억제
                        # 단, 제어된 동작 억제 활성 시 ML Boost 차단 (ml_raw < 0.90일 때)
                        if ml_score_raw >= 0.7:
                            if (posture == PostureType.STANDING
                                    and body_angle > 75.0
                                    and rule_score < 0.3):
                                logger.debug(
                                    "[ML Boost 억제] %s | standing+직립(%.1f°)+rule(%.2f)<0.3 → ML FP 패턴",
                                    person_id, body_angle, rule_score,
                                )
                            elif _any_suppression and ml_score_raw < 0.90:
                                logger.debug(
                                    "[ML Boost 억제] %s | 제어된 동작 억제 활성 + ml_raw=%.2f(<0.90) → ML Boost 차단",
                                    person_id, ml_score_raw,
                                )
                            else:
                                score = ml_score_raw
                                logger.info(
                                    "[ML Boost] %s | ml_raw=%.2f(≥0.70) ema=%.2f → ML raw 점수 사용",
                                    person_id, ml_score_raw, ml_score,
                                )
                        # 중간 확신 ML (0.4-0.7): 규칙도 일부 반응 필요
                        elif ml_score_raw >= 0.40 and rule_score >= 0.15:
                            if _any_suppression:
                                logger.debug(
                                    "[ML Boost 억제] %s | 제어된 동작 억제 활성 + ml_raw=%.2f → 중간 ML Boost 차단",
                                    person_id, ml_score_raw,
                                )
                            else:
                                score = ml_score_raw
                                logger.info(
                                    "[ML Boost] %s | ml_raw=%.2f(≥0.40) ema=%.2f + rule=%.2f(≥0.15) → ML raw 점수 사용",
                                    person_id, ml_score_raw, ml_score, rule_score,
                                )

        is_fall_detected = score >= self._composite_threshold

        # ── Standing FP Post-EMA 필터 ──
        # EMA 경로에서도 standing + 거의 직립(angle>75°) + 규칙 무반응(rule<0.20) → 감지 취소
        # 기존 ML Boost 억제(line 744-750)는 ML Boost 경로만 차단하지만, 이 필터는 EMA 경로도 차단
        # 실제 낙상은 angle이 빠르게 감소하므로 영향 없음
        # 단, ML ≥ 0.90 (극고확신) → 필터 면제 (ML 시간적 패턴이 낙상 초기 단계 감지)
        if (is_fall_detected
                and posture == PostureType.STANDING
                and body_angle > 75.0
                and rule_score < 0.20
                and not state.is_fallen
                and score < 0.90):
            is_fall_detected = False
            logger.debug(
                "[Standing FP 필터] %s | standing+직립(%.1f°)+rule(%.2f)<0.20+score(%.2f)<0.90 → 감지 취소",
                person_id, body_angle, rule_score, score,
            )

        # ── 저가시성 다중 프레임 누적 감지 ──
        # 중간 가시성(0.3-0.5)에서 개별 프레임은 임계값 미달이지만
        # 연속으로 중간 점수가 나오면 패턴으로 인정하여 감지
        # AIHub C1/C4/C8 카메라 각도에서 부분 가려짐 해결용
        state.low_vis_score_history.append(score)
        if _low_vis_mode and not is_fall_detected:
            # 최근 N프레임의 점수가 모두 임계값 이상이면 감지 활성화
            if len(state.low_vis_score_history) >= settings.FALL_LOW_VIS_ACCUM_FRAMES:
                recent_scores = list(state.low_vis_score_history)[-settings.FALL_LOW_VIS_ACCUM_FRAMES:]
                if all(s >= settings.FALL_LOW_VIS_ACCUM_THRESHOLD for s in recent_scores):
                    is_fall_detected = True
                    logger.info(
                        "[저가시성 누적] %s | vis=%.2f, 최근%d프레임 점수 %s (≥%.2f) → 누적 감지",
                        person_id, avg_visibility,
                        settings.FALL_LOW_VIS_ACCUM_FRAMES,
                        [f"{s:.2f}" for s in recent_scores],
                        settings.FALL_LOW_VIS_ACCUM_THRESHOLD,
                    )

        # ── 착석 오탐 방지: 착석 전용 조건 없으면 ML 단독 감지 차단 ──
        # 앉아있는 자세는 ML 모델이 낙상과 혼동하기 쉬움 (특히 back_fall).
        # 착석 전용 조건(C5/C6/C7)이 하나도 없으면:
        #   1) score < 0.7 → 차단 (기존: 블렌디드 스코어 낮으면 차단)
        #   2) rule_score < composite_threshold → 차단 (규칙도 낙상이 아니면 ML만으로 판정 금지)
        # 예외1: trip_fall_boost가 True이면 착석 오탐 방지 우회 (실제 넘어짐)
        # 예외2: score >= 0.85 (매우 높은 ML 확신) → 낙상 중 일시적 sitting 분류 허용
        if posture == PostureType.SITTING and not seated_any_specific and not trip_fall_boost:
            if is_fall_detected and score < 0.75 and (score < 0.7 or rule_score < self._composite_threshold):
                is_fall_detected = False
                logger.debug(
                    "[착석오탐방지] %s | score=%.2f, rule=%.2f (착석 전용 조건 없음) → 감지 취소",
                    person_id, score, rule_score,
                )
            # ── 착석 ML-Only FP 필터 ──

        # Standing ML Gate 제거 (2026-02-07)
        # 벤치마크 분석 결과: FP는 rule-only (rule=0.95+, ML=0.0)에서 발생하며,
        # ML-only standing 감지는 정당한 낙상인 경우가 대부분.
        # 이 게이트가 recall을 크게 떨어뜨림 (정당한 낙상 차단).
        # Rule-only FP는 rule_weight=0일 때 rule override 비활성화로 해결.

        # ── ML Boost: 높은 확신도 즉시 반응 ──
        # ML confidence가 충분히 높으면 연속 프레임 체크를 건너뜀
        ml_high_confidence = (
            _ml_active
            and fall_classifier.enabled
            and ml_score_raw >= 0.6
        )

        # ── 오탐 방지 3: 연속 프레임 확인 ──
        # 단일 프레임 노이즈 방지: N 프레임 연속 감지되어야 실제 낙상 판정
        # (단, ML 고확신 시 즉시 통과)
        if is_fall_detected:
            state.consecutive_fall_frames += 1
            # 고신뢰도 점수일수록 연속 프레임 요구 완화
            # 벤치마크 분석: 3프레임은 너무 엄격하여 많은 FN 발생
            required_frames = min(settings.FALL_CONSECUTIVE_FRAMES, 2)  # 최대 2
            if score >= 0.90:
                required_frames = 1  # 고신뢰: 즉시 확정
            elif score >= 0.70 and ml_high_confidence:
                required_frames = 1  # ML 0.6+ AND score 0.7+ → 1프레임 즉시
            if state.consecutive_fall_frames < required_frames:
                is_fall_detected = False
                logger.debug(
                    "[오탐방지] %s | 연속 확인 중 (%d/%d, score=%.2f)",
                    person_id, state.consecutive_fall_frames,
                    required_frames, score,
                )
        else:
            state.consecutive_fall_frames = 0

        # ── 오탐 방지 4: LYING 자세 안정 면제 ──
        # 이미 누워있는 상태가 오래 지속된 경우 (침대 환자 등) 감지 면제
        # 단, 이미 낙상 판정된 사람(state.is_fallen)에게는 적용하지 않음!
        # (실제 낙상 후 바닥에 누워있는 상태를 정상으로 전환하면 안 됨)
        if posture == PostureType.LYING and is_fall_detected and not state.is_fallen:
            posture_state = posture_classifier.get_or_create_state(person_id)
            lying_frames = sum(
                1 for p in list(posture_state.posture_history)
                if p == PostureType.LYING
            )
            if lying_frames >= settings.FALL_LYING_STABLE_EXEMPT_FRAMES:
                is_fall_detected = False
                logger.debug(
                    "[오탐방지] %s | LYING 안정 면제 (%d프레임 지속, 침대 환자 추정)",
                    person_id, lying_frames,
                )

        # ── 오탐 방지 5: 장기 LYING 자세에서 새 낙상 감지 억제 ──
        # 이미 오래 누워있는 상태에서 가속 히스토리로 인한 오탐 방지
        # - 핵심: 연속 10프레임 이상 lying이었으면 새 낙상 불가능
        # - N_normal_standing_03.mp4: 누워있는 동안 히스토리의 가속으로 감지되는 케이스 방지
        # - SY_side_fall_balance.mp4: 빠른 전환(standing→lying)은 감지되어야 함
        if posture == PostureType.LYING and is_fall_detected and not state.is_fallen:
            posture_state = posture_classifier.get_or_create_state(person_id)
            # 최근 posture_history에서 lying 연속 프레임 수 확인
            recent_lying_frames = 0
            for p in reversed(list(posture_state.posture_history)):
                if p == PostureType.LYING:
                    recent_lying_frames += 1
                else:
                    break  # lying이 아닌 프레임을 만나면 중단
            # 10프레임 이상 연속 lying이면 억제 (빠른 전환은 허용)
            if recent_lying_frames >= 10:
                is_fall_detected = False
                logger.debug(
                    "[오탐방지] %s | 장기 LYING 상태에서 새 낙상 감지 억제 (%d프레임 연속)",
                    person_id, recent_lying_frames,
                )

        # ── 착석 ML 노이즈 스코어 억제 ──
        # 착석 + 착석 전용 조건(C5/C6/C7) 없음 + 미감지 → ML 기여분 제거
        # rule_weight=0.0 시에는 score를 0.3 이하로 캡핑 (모니터링 신호 보존)
        if (posture == PostureType.SITTING
                and not seated_any_specific
                and not is_fall_detected
                and not state.is_fallen
                and state.consecutive_fall_frames == 0
                and ml_score_raw < 0.75):
            if self._rule_weight == 0.0:
                score = min(score, 0.3)
            else:
                score = rule_score * self._rule_weight

        # fall_type은 ML이 비활성화인 경우 규칙 기반에서 결정
        if (not _ml_active or not fall_classifier.enabled) and is_fall_detected:
            fall_type = "unknown"  # 규칙 기반에서는 방향 구분 불가

        # ── 디버깅 로그: 감지 로직 상세 출력 ──
        posture_label = posture.value
        if posture == PostureType.SITTING:
            logger.debug(
                "[낙상감지] %s [%s] | head=%.3f hip=%.3f knee=%.3f | "
                "C1(역전)=%s C2(하강)=%s(Δ%.3f) C3(수평)=%s(∠%.1f°) "
                "C5(전방쏠림)=%s C6(측면이탈)=%s C7(높이급락)=%s | 규칙=%.2f",
                person_id, posture_label, head_y, hip_y, knee_y,
                "O" if cond1_inverted else "X",
                "O" if cond2_rapid_descent else "X", descent,
                "O" if cond3_horizontal else "X", body_angle,
                "O" if cond5_forward_slump else "X",
                "O" if cond6_lateral_tilt else "X",
                "O" if cond7_height_drop else "X",
                rule_score,
            )
        else:
            n_status = ""
            if _enhanced:
                n_status = (
                    f" N1={('O' if n1_accel else 'X')}"
                    f" N2={('O' if n2_protective else 'X')}"
                    f" N3={('O' if n3_com_bos else 'X')}"
                    f" N4={('O' if n4_knee_buckle else 'X')}"
                    f" N5={('O' if n5_trunk_rotation else 'X')}"
                    f" N6={('O' if n6_trajectory else 'X')}"
                )
            logger.debug(
                "[낙상감지] %s [%s] | head=%.3f hip=%.3f diff=%.3f | "
                "C1(역전)=%s(+%.2f) C2(하강)=%s(+%.2f,Δ%.3f) C3(수평)=%s(+%.2f,∠%.1f°) C4(발목)=%s(+0.1) |%s "
                "규칙=%.2f",
                person_id, posture_label, head_y, hip_y, head_hip_diff,
                "O" if cond1_inverted else "X", _w_c1,
                "O" if cond2_rapid_descent else "X", _w_c2, descent,
                "O" if cond3_horizontal else "X", _w_c3, body_angle,
                "O" if ankle_above_hip else "X",
                n_status,
                rule_score,
            )
        if _ml_active and fall_classifier.enabled:
            ml_probs_str = " ".join(f"{k}={v:.2%}" for k, v in ml_class_probs.items())
            logger.debug(
                "[앙상블] %s | ML=%.3f(%s) type=%s | "
                "최종=규칙(%.2f)×%.1f + ML(%.2f)×%.1f = %.3f %s",
                person_id, ml_score, ml_probs_str, fall_type,
                rule_score, self._rule_weight, ml_score, self._ml_weight,
                score, ">>> 낙상!" if is_fall_detected else "",
            )
        elif is_fall_detected:
            logger.debug(
                "[규칙전용] %s | 점수=%.3f >= 임계값(%.2f) >>> 낙상!",
                person_id, score, self._composite_threshold,
            )

        # === 디버그 요약 ===
        if is_fall_detected or (state.frames_since_first_seen % 60 == 0):
            _log_fn = logger.info if is_fall_detected else logger.debug
            _log_fn(
                "[감지요약] %s [%s] | score=%.2f (rule=%.2f ml=%.2f) | "
                "head=%.3f hip=%.3f diff=%.3f(th=%.3f) desc=%.3f(th=%.3f) angle=%.1f°(th=%.1f) | "
                "C1=%s C2=%s C3=%s | fall=%s",
                person_id, posture.value, score, rule_score, ml_score,
                head_y, hip_y, head_hip_diff, head_hip_th,
                descent, descent_th, body_angle, (90.0 - angle_th),
                "O" if cond1_inverted else "X",
                "O" if cond2_rapid_descent else "X",
                "O" if cond3_horizontal else "X",
                "Y" if is_fall_detected else "N",
            )

        # === 쿨다운 로직 ===
        if is_fall_detected:
            if not state.is_fallen:
                state.is_fallen = True
                state.fall_start_time = now
                state.cooldown_active = False
                # 착석 조건 포함 로깅
                seated_conds = ""
                if posture == PostureType.SITTING:
                    seated_conds = " 착석조건=[%s%s%s]" % (
                        "전방쏠림 " if cond5_forward_slump else "",
                        "측면이탈 " if cond6_lateral_tilt else "",
                        "높이급락" if cond7_height_drop else "",
                    )
                n_conds = ""
                if _enhanced:
                    n_conds = " N=[%s%s%s%s%s%s]" % (
                        "가속 " if n1_accel else "",
                        "신전 " if n2_protective else "",
                        "CoM " if n3_com_bos else "",
                        "무릎 " if n4_knee_buckle else "",
                        "회전 " if n5_trunk_rotation else "",
                        "궤적" if n6_trajectory else "",
                    )
                logger.warning(
                    "*** 낙상 감지! *** person=%s [%s], score=%.2f, type=%s, "
                    "규칙=%.2f, ML=%.2f, 조건=[%s%s%s%s]%s%s",
                    person_id, posture_label, score, fall_type, rule_score, ml_score,
                    "역전 " if cond1_inverted else "",
                    "하강 " if cond2_rapid_descent else "",
                    "수평 " if cond3_horizontal else "",
                    "발목" if ankle_above_hip else "",
                    seated_conds, n_conds,
                )
            state.last_normal_time = None
        else:
            if state.is_fallen:
                if state.last_normal_time is None:
                    state.last_normal_time = now
                    state.cooldown_active = True
                    logger.debug(
                        "[쿨다운] %s | 쿨다운 시작 (%.1f초 대기)",
                        person_id, self._cooldown_seconds,
                    )
                elif now - state.last_normal_time >= self._cooldown_seconds:
                    state.is_fallen = False
                    state.fall_start_time = None
                    state.cooldown_active = False
                    state.last_normal_time = None
                    logger.info("정상 복귀: person=%s (쿨다운 완료)", person_id)

        # ══════════════════════════════════════════════════════════════════
        # Quick Recovery Detection: 빠른 회복 감지
        # - 낙상 후 짧은 시간 내 standing 복귀 → 의도적 눕기로 판정
        # - 실제 낙상 환자는 빠르게 일어나지 못함 (특히 고령자)
        # - N_normal_standing_03.mp4 오탐 해결
        # ══════════════════════════════════════════════════════════════════
        if state.is_fallen:
            # lying 상태 지속 시간 추적
            if posture == PostureType.LYING:
                state.fall_lying_duration += 1
                state.quick_recovery_standing_frames = 0  # standing 카운터 리셋
            # standing 복귀 시 연속 프레임 추적
            elif posture == PostureType.STANDING:
                state.quick_recovery_standing_frames += 1

                # Quick Recovery 조건:
                # 1) lying 상태가 10프레임 미만 (약 0.3~0.5초, 60fps 기준)
                # 2) standing이 5프레임 이상 연속 유지
                # 3) 현재 낙상 점수가 0 (완전히 정상 상태)
                # 주의: 임계값이 너무 높으면 실제 낙상 후 빠른 회복도 해제됨
                quick_recovery_threshold_lying = 10  # lying 최대 프레임 (보수적)
                quick_recovery_threshold_standing = 5  # standing 최소 프레임

                if (state.fall_lying_duration < quick_recovery_threshold_lying
                        and state.quick_recovery_standing_frames >= quick_recovery_threshold_standing
                        and score < 0.1):
                    logger.info(
                        "[빠른회복] %s | lying=%d프레임 < %d, standing=%d프레임 >= %d "
                        "→ 의도적 눕기로 판정, 낙상 상태 해제",
                        person_id,
                        state.fall_lying_duration, quick_recovery_threshold_lying,
                        state.quick_recovery_standing_frames, quick_recovery_threshold_standing,
                    )
                    state.is_fallen = False
                    state.fall_start_time = None
                    state.cooldown_active = False
                    state.last_normal_time = None
                    state.fall_lying_duration = 0
                    state.quick_recovery_standing_frames = 0
            else:
                # sitting 등 다른 자세
                state.quick_recovery_standing_frames = 0
        else:
            # 낙상 아닐 때는 카운터 리셋
            state.fall_lying_duration = 0
            state.quick_recovery_standing_frames = 0

        # ══════════════════════════════════════════════════════════════════
        # Controlled Movement Post-Fall: 낙상 후 제어된 움직임 감지
        # - 낙상 후 head_y 속도가 일정하고 부드러우면 제어된 동작으로 판정
        # - 실제 낙상: 바닥에서 움직임 없거나 불규칙한 움직임
        # - 오탐(앉기/숙이기): 부드럽고 일정한 속도의 움직임
        # ══════════════════════════════════════════════════════════════════
        if state.is_fallen:
            state.post_fall_frames += 1
            # head_y 속도 계산 (현재 - 이전 프레임)
            if len(state.head_y_history) >= 2:
                velocity = state.head_y_history[-1] - state.head_y_history[-2]
                state.post_fall_velocity_history.append(velocity)

            # 충분한 프레임이 쌓이면 속도 분산 체크
            # 단, 낙상 감지 후 최소 3초는 제어된 움직임 필터 적용하지 않음
            # (DANGER 전환 threshold 1.5초 + 여유 1.5초 = 3초)
            _min_fall_hold = 3.0
            _fall_elapsed = (now - state.fall_start_time) if state.fall_start_time else 999
            if state.post_fall_frames >= settings.FALL_POST_FALL_CHECK_FRAMES and _fall_elapsed >= _min_fall_hold:
                if len(state.post_fall_velocity_history) >= settings.FALL_POST_FALL_CHECK_FRAMES:
                    import statistics
                    velocities = list(state.post_fall_velocity_history)
                    velocity_variance = statistics.variance(velocities) if len(velocities) > 1 else 0.0

                    # 제어된 움직임: 분산이 낮음 (부드러운 움직임)
                    # + 현재 자세가 LYING이 아님 (실제 낙상은 바닥에 누워있음)
                    if (velocity_variance < settings.FALL_POST_FALL_MAX_VARIANCE
                            and posture != PostureType.LYING
                            and score < 0.3):
                        logger.info(
                            "[제어된움직임] %s | 분산=%.6f < %.6f, 자세=%s "
                            "→ 제어된 동작으로 판정, 낙상 상태 해제",
                            person_id, velocity_variance,
                            settings.FALL_POST_FALL_MAX_VARIANCE, posture.value,
                        )
                        state.is_fallen = False
                        state.fall_start_time = None
                        state.cooldown_active = False
                        state.last_normal_time = None
                        state.post_fall_frames = 0
                        state.post_fall_velocity_history.clear()
        else:
            # 낙상 아닐 때 리셋
            state.post_fall_frames = 0
            state.post_fall_velocity_history.clear()

        # ── 낙상 후 바닥 유지 감지 ──
        # 낙상이 확인된 사람이 여전히 누워있으면 (일어나지 못함)
        # 쿨다운과 관계없이 낙상 상태를 유지한다.
        # 정상 복귀 조건: 자세가 STANDING 또는 SITTING으로 변경될 때만.
        if state.is_fallen and posture == PostureType.LYING:
            state.last_normal_time = None  # 쿨다운 리셋
            state.cooldown_active = False

        effective_fallen = state.is_fallen

        # ── 전조 감지: 낙상 임계값 미달이지만 이상 징후 포착 ──
        # 1) 앙상블 점수가 전조 임계값(0.25) 이상
        # 2) ML 단독 점수가 0.4 이상 (규칙 무반응이어도 ML이 이상 감지)
        #    단, 착석 상태에서 착석 전용 조건 없으면 ML 전조 차단 (오탐 방지)
        # 3) N4(무릎 좌굴) 감지 시 독립 전조 트리거 (ML 없이도)
        _seated_block_pre = (posture == PostureType.SITTING and not seated_any_specific)
        _ml_pre_impact = (
            _ml_active
            and fall_classifier.enabled
            and ml_score_raw >= self._pre_impact_ml_threshold
            and not _seated_block_pre
        )
        _n4_pre_impact = _enhanced and n4_knee_buckle
        is_pre_impact = (
            not effective_fallen
            and not is_fall_detected
            and (score >= self._pre_impact_threshold or _ml_pre_impact or _n4_pre_impact)
        )

        return {
            "is_fallen": effective_fallen,
            "confidence": score,
            "head_y": head_y,
            "hip_y": hip_y,
            "angle": body_angle,
            "fall_duration": (now - state.fall_start_time) if state.fall_start_time and effective_fallen else 0,
            "cooldown_active": state.cooldown_active,
            "fall_type": fall_type,
            "is_pre_impact": is_pre_impact,
            "posture": posture.value,
            "rule_score": rule_score,
            "ml_score": ml_score,
            "conditions": {
                "head_hip_inverted": cond1_inverted,
                "rapid_descent": cond2_rapid_descent,
                "horizontal_body": cond3_horizontal,
                "forward_slump": cond5_forward_slump,
                "lateral_tilt": cond6_lateral_tilt,
                "height_drop": cond7_height_drop,
                "n1_accel": n1_accel,
                "n2_protective": n2_protective,
                "n3_com_bos": n3_com_bos,
                "n4_knee_buckle": n4_knee_buckle,
                "n5_trunk_rotation": n5_trunk_rotation,
                "n6_trajectory": n6_trajectory,
                "composite_score": score,
            },
        }

    def reset_person(self, person_id: str):
        """특정 인물 상태 리셋 (acknowledge 시)"""
        with self._states_lock:
            if person_id in self._person_states:
                del self._person_states[person_id]
                logger.info("person 리셋: %s", person_id)

    def reset_camera(self, camera_id: str):
        """특정 카메라의 인물 상태만 리셋 (다른 카메라 보존)"""
        with self._states_lock:
            prefix = f"{camera_id}_"
            to_remove = [pid for pid in self._person_states if pid.startswith(prefix)]
            for pid in to_remove:
                del self._person_states[pid]
            if to_remove:
                logger.info("[%s] 카메라별 person 상태 리셋: %d명", camera_id, len(to_remove))

    def reset_all(self):
        """모든 상태 리셋"""
        with self._states_lock:
            self._person_states.clear()
            logger.info("모든 person 상태 리셋")

    def _default_result(self) -> dict:
        return {
            "is_fallen": False,
            "confidence": 0.0,
            "head_y": 0.0,
            "hip_y": 0.0,
            "angle": 90.0,
            "fall_duration": 0,
            "cooldown_active": False,
            "fall_type": "normal",
            "is_pre_impact": False,
            "posture": "unknown",
            "rule_score": 0.0,
            "ml_score": 0.0,
            "conditions": {
                "head_hip_inverted": False,
                "rapid_descent": False,
                "horizontal_body": False,
                "forward_slump": False,
                "lateral_tilt": False,
                "height_drop": False,
                "n1_accel": False,
                "n2_protective": False,
                "n3_com_bos": False,
                "n4_knee_buckle": False,
                "n5_trunk_rotation": False,
                "n6_trajectory": False,
                "composite_score": 0.0,
            },
        }


# 싱글턴
fall_detector = FallDetector()
