"""
자세 분류기 (Posture Classifier)

MediaPipe 33-point 랜드마크 기반으로 서있음/앉아있음/누워있음을 분류합니다.
요양병원 대기실 특성상 휠체어/의자 착석 환자를 정확히 구분하여
자세별 다른 낙상 감지 임계값을 적용하기 위한 서비스입니다.

분류 기준:
  - 서있음(STANDING): 무릎 펴짐, 체형 수직, 전체 키 높이 큼
  - 앉아있음(SITTING): 무릎 굽힘(허벅지 수평), 상체 수직, 키 높이 줄어듦
  - 누워있음(LYING): 체형 수평, 머리와 발목 높이 유사
"""

import math
from collections import deque
from dataclasses import dataclass, field
from enum import Enum

from app.config import settings
from app.core.logging_config import get_logger

logger = get_logger("app.services.posture_classifier")


class PostureType(str, Enum):
    """자세 유형"""
    STANDING = "standing"
    SITTING = "sitting"
    LYING = "lying"
    UNKNOWN = "unknown"


@dataclass
class PostureState:
    """개인별 자세 상태"""
    person_id: str
    current_posture: PostureType = PostureType.UNKNOWN
    posture_history: deque = field(default_factory=lambda: deque(maxlen=15))
    # 앉은 상태 기준선 (baseline) 추적
    sitting_baseline_head_y: float = 0.0
    sitting_baseline_frames: int = 0
    # 어깨 기울기 히스토리 (측면 이탈 감지용)
    shoulder_tilt_history: deque = field(default_factory=lambda: deque(maxlen=10))


class PostureClassifier:
    """자세 분류기 (싱글톤)

    MediaPipe 랜드마크에서 무릎 굽힘 비율, 체형 각도, 높이 비율을 분석하여
    서있음/앉아있음/누워있음을 분류합니다.

    자세 안정화: 최근 N프레임의 다수결로 떨림을 방지합니다.
    """

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

    def __init__(self):
        self._person_states: dict[str, PostureState] = {}
        self._knee_bend_sitting = settings.POSTURE_KNEE_BEND_SITTING
        self._knee_bend_standing = settings.POSTURE_KNEE_BEND_STANDING
        self._lying_angle = settings.POSTURE_LYING_ANGLE
        self._stability_frames = settings.POSTURE_STABILITY_FRAMES

    def get_or_create_state(self, person_id: str) -> PostureState:
        if person_id not in self._person_states:
            self._person_states[person_id] = PostureState(person_id=person_id)
        return self._person_states[person_id]

    def classify(self, landmarks: list[dict], person_id: str = "person_0") -> PostureType:
        """랜드마크에서 자세를 분류합니다.

        Args:
            landmarks: MediaPipe 33-point 랜드마크 리스트
            person_id: 인물 고유 ID

        Returns:
            PostureType: STANDING, SITTING, LYING, UNKNOWN
        """
        if len(landmarks) < 33:
            return PostureType.UNKNOWN

        state = self.get_or_create_state(person_id)

        # 주요 랜드마크 추출
        l_shoulder = landmarks[self.LEFT_SHOULDER]
        r_shoulder = landmarks[self.RIGHT_SHOULDER]
        l_hip = landmarks[self.LEFT_HIP]
        r_hip = landmarks[self.RIGHT_HIP]
        l_knee = landmarks[self.LEFT_KNEE]
        r_knee = landmarks[self.RIGHT_KNEE]
        l_ankle = landmarks[self.LEFT_ANKLE]
        r_ankle = landmarks[self.RIGHT_ANKLE]
        nose = landmarks[self.NOSE]

        # 중심점 계산
        head_y = nose["y"]
        shoulder_y = (l_shoulder["y"] + r_shoulder["y"]) / 2
        hip_y = (l_hip["y"] + r_hip["y"]) / 2
        knee_y = (l_knee["y"] + r_knee["y"]) / 2
        ankle_y = (l_ankle["y"] + r_ankle["y"]) / 2

        shoulder_mid_x = (l_shoulder["x"] + r_shoulder["x"]) / 2
        hip_mid_x = (l_hip["x"] + r_hip["x"]) / 2

        # ── 지표 1: 무릎 굽힘 비율 ──
        # hip-knee 거리 / knee-ankle 거리
        # 서있음: ≈1.0 (상하체 균등), 앉아있음: <0.4 (허벅지 수평, 종아리 수직)
        hip_knee_dist = abs(hip_y - knee_y)
        knee_ankle_dist = abs(knee_y - ankle_y)
        knee_bend_ratio = hip_knee_dist / knee_ankle_dist if knee_ankle_dist > 0.01 else 1.0

        # ── 지표 2: 체형 각도 (수직 기준: 0°=서있음, 90°=누워있음) ──
        dx = hip_mid_x - shoulder_mid_x
        dy = hip_y - shoulder_y
        body_length = math.sqrt(dx * dx + dy * dy)
        if body_length > 1e-6:
            body_angle = math.degrees(math.acos(min(abs(dy) / body_length, 1.0)))
        else:
            body_angle = 0.0  # 체형 벡터 없음 → 수직 가정

        # ── 지표 3: 전체 높이 비율 ──
        # 머리~발목 전체 높이 (normalized)
        total_height = abs(ankle_y - head_y)

        # ── 지표 4: 어깨 좌우 기울기 (부호 포함: 양수=왼어깨↓, 음수=오른어깨↓) ──
        shoulder_tilt = l_shoulder["y"] - r_shoulder["y"]
        state.shoulder_tilt_history.append(shoulder_tilt)

        # ── 자세 판정 ──
        raw_posture = PostureType.UNKNOWN

        # 1) 누워있음: 체형이 수평에 가깝고, 머리와 발목 높이 유사
        if body_angle > (90 - self._lying_angle) and total_height < 0.25:
            raw_posture = PostureType.LYING

        # 2) 앉아있음: 무릎 굽힘 비율이 낮고, 상체는 수직
        elif knee_bend_ratio < self._knee_bend_sitting and head_y < hip_y:
            raw_posture = PostureType.SITTING

        # 3) 서있음: 무릎 비율 높고, 전체 키가 큼
        elif knee_bend_ratio > self._knee_bend_standing and head_y < hip_y:
            raw_posture = PostureType.STANDING

        # 4) 애매한 경우: 무릎 비율 중간대 → 이전 자세 유지
        else:
            raw_posture = state.current_posture if state.current_posture != PostureType.UNKNOWN else PostureType.STANDING

        # ── 자세 안정화 (다수결 투표) ──
        state.posture_history.append(raw_posture)

        if len(state.posture_history) >= self._stability_frames:
            # 최근 N프레임에서 가장 많은 자세를 채택
            from collections import Counter
            votes = Counter(list(state.posture_history)[-self._stability_frames:])
            stable_posture = votes.most_common(1)[0][0]
        else:
            stable_posture = raw_posture

        # 자세 전환 로깅
        if stable_posture != state.current_posture and state.current_posture != PostureType.UNKNOWN:
            logger.info(
                "[자세변경] %s: %s → %s (knee_bend=%.2f, angle=%.1f°, height=%.3f)",
                person_id, state.current_posture.value, stable_posture.value,
                knee_bend_ratio, body_angle, total_height,
            )

        state.current_posture = stable_posture

        # ── 앉은 상태 기준선 업데이트 ──
        if stable_posture == PostureType.SITTING:
            if state.sitting_baseline_frames < 30:
                # 초기 30프레임 동안 기준선 누적 평균
                n = state.sitting_baseline_frames
                state.sitting_baseline_head_y = (state.sitting_baseline_head_y * n + head_y) / (n + 1)
                state.sitting_baseline_frames += 1
            else:
                # 안정화 후에는 이동 평균 (느리게 적응)
                alpha = 0.02
                state.sitting_baseline_head_y = (1 - alpha) * state.sitting_baseline_head_y + alpha * head_y
        else:
            # 앉은 상태가 아니면 기준선 리셋
            state.sitting_baseline_frames = 0
            state.sitting_baseline_head_y = 0.0

        logger.debug(
            "[자세] %s | %s | knee_bend=%.2f body_angle=%.1f° height=%.3f tilt=%.3f | baseline_head=%.3f",
            person_id, stable_posture.value,
            knee_bend_ratio, body_angle, total_height, shoulder_tilt,
            state.sitting_baseline_head_y,
        )

        return stable_posture

    def get_sitting_baseline(self, person_id: str) -> float:
        """앉은 상태의 머리 높이 기준선 반환"""
        state = self._person_states.get(person_id)
        if state and state.sitting_baseline_frames >= 10:
            return state.sitting_baseline_head_y
        return 0.0

    def get_shoulder_tilt_delta(self, person_id: str) -> float:
        """최근 어깨 기울기 변화량 반환 (측면 이탈 감지용)

        연속 프레임 간 최대 변화량을 사용하여 자연스러운 흔들림과
        급격한 기울기 변화를 구분합니다.
        """
        state = self._person_states.get(person_id)
        if state and len(state.shoulder_tilt_history) >= 5:
            recent = list(state.shoulder_tilt_history)
            # 연속 프레임 간 최대 변화량 (급격한 기울기 변화만 감지)
            max_delta = 0.0
            for i in range(1, len(recent)):
                delta = abs(recent[i] - recent[i - 1])
                max_delta = max(max_delta, delta)
            return max_delta
        return 0.0

    def reset_person(self, person_id: str) -> None:
        self._person_states.pop(person_id, None)


# 싱글톤
posture_classifier = PostureClassifier()
