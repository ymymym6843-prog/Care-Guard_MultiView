"""
키포인트 어댑터 (Keypoint Adapter)

COCO 17점 ↔ MediaPipe 33점 변환을 담당합니다.
YOLO Pose 모델의 출력(COCO 17점)을 기존 낙상 감지 로직에서 사용할 수 있도록 변환합니다.

COCO 17 Keypoints:
    0: nose, 1: left_eye, 2: right_eye, 3: left_ear, 4: right_ear,
    5: left_shoulder, 6: right_shoulder, 7: left_elbow, 8: right_elbow,
    9: left_wrist, 10: right_wrist, 11: left_hip, 12: right_hip,
    13: left_knee, 14: right_knee, 15: left_ankle, 16: right_ankle

MediaPipe 33 Landmarks:
    0: NOSE, 1-10: 얼굴 상세, 11-16: 상체, 17-22: 손가락,
    23-28: 하체, 29-32: 발

Phase 27: YOLO Pose 17점 전환
"""

from dataclasses import dataclass
from enum import Enum
from typing import Literal

import numpy as np

from app.core.logging_config import get_logger

logger = get_logger("app.services.keypoint_adapter")


class KeypointFormat(str, Enum):
    """키포인트 포맷 열거형"""
    MEDIAPIPE_33 = "mediapipe_33"
    COCO_17 = "coco_17"


@dataclass(frozen=True)
class KeypointIndices:
    """키포인트 인덱스 집합"""
    nose: int
    left_eye: int
    right_eye: int
    left_ear: int
    right_ear: int
    left_shoulder: int
    right_shoulder: int
    left_elbow: int
    right_elbow: int
    left_wrist: int
    right_wrist: int
    left_hip: int
    right_hip: int
    left_knee: int
    right_knee: int
    left_ankle: int
    right_ankle: int


# MediaPipe 33점 인덱스
MEDIAPIPE_INDICES = KeypointIndices(
    nose=0,
    left_eye=2,
    right_eye=5,
    left_ear=7,
    right_ear=8,
    left_shoulder=11,
    right_shoulder=12,
    left_elbow=13,
    right_elbow=14,
    left_wrist=15,
    right_wrist=16,
    left_hip=23,
    right_hip=24,
    left_knee=25,
    right_knee=26,
    left_ankle=27,
    right_ankle=28,
)

# COCO 17점 인덱스
COCO_INDICES = KeypointIndices(
    nose=0,
    left_eye=1,
    right_eye=2,
    left_ear=3,
    right_ear=4,
    left_shoulder=5,
    right_shoulder=6,
    left_elbow=7,
    right_elbow=8,
    left_wrist=9,
    right_wrist=10,
    left_hip=11,
    right_hip=12,
    left_knee=13,
    right_knee=14,
    left_ankle=15,
    right_ankle=16,
)


# COCO → MediaPipe 매핑 (17점의 각 인덱스가 33점의 어느 인덱스에 해당하는지)
COCO_TO_MEDIAPIPE_MAP = {
    0: 0,    # nose
    1: 2,    # left_eye
    2: 5,    # right_eye
    3: 7,    # left_ear
    4: 8,    # right_ear
    5: 11,   # left_shoulder
    6: 12,   # right_shoulder
    7: 13,   # left_elbow
    8: 14,   # right_elbow
    9: 15,   # left_wrist
    10: 16,  # right_wrist
    11: 23,  # left_hip
    12: 24,  # right_hip
    13: 25,  # left_knee
    14: 26,  # right_knee
    15: 27,  # left_ankle
    16: 28,  # right_ankle
}


class KeypointAdapter:
    """COCO 17점 ↔ MediaPipe 33점 변환 어댑터"""

    # 결측값 기본 visibility
    DEFAULT_VISIBILITY = 0.0

    @staticmethod
    def get_indices(keypoint_format: KeypointFormat | str) -> KeypointIndices:
        """키포인트 포맷에 따른 인덱스 반환"""
        if isinstance(keypoint_format, str):
            keypoint_format = KeypointFormat(keypoint_format)

        if keypoint_format == KeypointFormat.COCO_17:
            return COCO_INDICES
        return MEDIAPIPE_INDICES

    @staticmethod
    def coco_to_dict_list(
        coco_keypoints: np.ndarray,
        confidence_as_visibility: bool = True,
    ) -> list[dict]:
        """
        COCO 17점 배열을 dict 리스트로 변환 (낙상 감지 입력 형식)

        Args:
            coco_keypoints: (17, 3) 배열 [x, y, confidence] 또는 (17, 2) [x, y]
            confidence_as_visibility: True면 confidence를 visibility로 사용

        Returns:
            17개 dict 리스트 [{x, y, z, visibility}, ...]
        """
        if coco_keypoints is None:
            return []

        result = []
        for i in range(17):
            if i < len(coco_keypoints):
                kpt = coco_keypoints[i]
                if len(kpt) >= 3:
                    x, y, conf = kpt[0], kpt[1], kpt[2]
                else:
                    x, y, conf = kpt[0], kpt[1], 1.0

                result.append({
                    "x": float(x),
                    "y": float(y),
                    "z": 0.0,  # COCO는 z좌표 없음
                    "visibility": float(conf) if confidence_as_visibility else 1.0,
                })
            else:
                result.append({
                    "x": 0.0,
                    "y": 0.0,
                    "z": 0.0,
                    "visibility": 0.0,
                })

        return result

    @staticmethod
    def coco_to_mediapipe_33(
        coco_keypoints: np.ndarray | list,
        interpolate_missing: bool = True,
    ) -> list[dict]:
        """
        COCO 17점을 MediaPipe 33점 형식으로 변환

        결측 키포인트(손가락, 발 등)는 인접 점에서 보간하거나 기본값 사용

        Args:
            coco_keypoints: (17, 3) 배열 [x, y, confidence] 또는
                           17개 dict 리스트 [{x, y, z, visibility}, ...]
            interpolate_missing: True면 결측값 보간

        Returns:
            33개 dict 리스트 (MediaPipe 형식)
        """
        if coco_keypoints is None:
            return [{
                "x": 0.0, "y": 0.0, "z": 0.0, "visibility": 0.0
            } for _ in range(33)]

        # 33개 빈 랜드마크 초기화
        landmarks = []
        for _ in range(33):
            landmarks.append({
                "x": 0.0,
                "y": 0.0,
                "z": 0.0,
                "visibility": 0.0,
            })

        # 입력 형식 감지: list[dict] vs np.ndarray
        is_dict_list = (
            isinstance(coco_keypoints, list)
            and len(coco_keypoints) > 0
            and isinstance(coco_keypoints[0], dict)
        )

        # COCO 17점을 해당 MediaPipe 위치에 복사
        for coco_idx, mp_idx in COCO_TO_MEDIAPIPE_MAP.items():
            if coco_idx < len(coco_keypoints):
                kpt = coco_keypoints[coco_idx]

                if is_dict_list:
                    # list[dict] 형식: {x, y, z, visibility}
                    x = kpt.get("x", 0.0)
                    y = kpt.get("y", 0.0)
                    z = kpt.get("z", 0.0)
                    conf = kpt.get("visibility", 1.0)
                else:
                    # np.ndarray 형식: [x, y, confidence]
                    if len(kpt) >= 3:
                        x, y, conf = kpt[0], kpt[1], kpt[2]
                    else:
                        x, y, conf = kpt[0], kpt[1], 1.0
                    z = 0.0

                landmarks[mp_idx] = {
                    "x": float(x),
                    "y": float(y),
                    "z": float(z),
                    "visibility": float(conf),
                }

        if interpolate_missing:
            landmarks = KeypointAdapter._interpolate_missing(landmarks)

        return landmarks

    @staticmethod
    def _interpolate_missing(landmarks: list[dict]) -> list[dict]:
        """
        결측 키포인트 보간

        - 손가락 (17-22): 손목에서 보간
        - 발 (29-32): 발목에서 보간
        - 얼굴 상세 (1, 3, 4, 6, 9, 10): 코/눈/귀에서 보간
        """
        # 손가락 보간 (손목 기준)
        left_wrist = landmarks[15]
        right_wrist = landmarks[16]

        # 왼쪽 손가락 (17, 19, 21)
        for idx in [17, 19, 21]:
            if landmarks[idx]["visibility"] < 0.1:
                landmarks[idx] = {
                    "x": left_wrist["x"],
                    "y": left_wrist["y"] + 0.02,  # 약간 아래
                    "z": left_wrist["z"],
                    "visibility": left_wrist["visibility"] * 0.5,
                }

        # 오른쪽 손가락 (18, 20, 22)
        for idx in [18, 20, 22]:
            if landmarks[idx]["visibility"] < 0.1:
                landmarks[idx] = {
                    "x": right_wrist["x"],
                    "y": right_wrist["y"] + 0.02,
                    "z": right_wrist["z"],
                    "visibility": right_wrist["visibility"] * 0.5,
                }

        # 발 보간 (발목 기준)
        left_ankle = landmarks[27]
        right_ankle = landmarks[28]

        # 왼쪽 발 (29: heel, 31: foot_index)
        for idx in [29, 31]:
            if landmarks[idx]["visibility"] < 0.1:
                landmarks[idx] = {
                    "x": left_ankle["x"],
                    "y": left_ankle["y"] + 0.02,
                    "z": left_ankle["z"],
                    "visibility": left_ankle["visibility"] * 0.5,
                }

        # 오른쪽 발 (30: heel, 32: foot_index)
        for idx in [30, 32]:
            if landmarks[idx]["visibility"] < 0.1:
                landmarks[idx] = {
                    "x": right_ankle["x"],
                    "y": right_ankle["y"] + 0.02,
                    "z": right_ankle["z"],
                    "visibility": right_ankle["visibility"] * 0.5,
                }

        # 얼굴 상세 보간 (1, 3, 4, 6, 9, 10)
        nose = landmarks[0]
        left_eye = landmarks[2]
        right_eye = landmarks[5]

        # 눈 내측 (1: left_eye_inner, 4: right_eye_inner)
        if landmarks[1]["visibility"] < 0.1:
            landmarks[1] = {
                "x": (nose["x"] + left_eye["x"]) / 2,
                "y": left_eye["y"],
                "z": left_eye["z"],
                "visibility": min(nose["visibility"], left_eye["visibility"]) * 0.5,
            }
        if landmarks[4]["visibility"] < 0.1:
            landmarks[4] = {
                "x": (nose["x"] + right_eye["x"]) / 2,
                "y": right_eye["y"],
                "z": right_eye["z"],
                "visibility": min(nose["visibility"], right_eye["visibility"]) * 0.5,
            }

        # 눈 외측 (3: left_eye_outer, 6: right_eye_outer)
        left_ear = landmarks[7]
        right_ear = landmarks[8]

        if landmarks[3]["visibility"] < 0.1:
            landmarks[3] = {
                "x": (left_eye["x"] + left_ear["x"]) / 2,
                "y": left_eye["y"],
                "z": left_eye["z"],
                "visibility": min(left_eye["visibility"], left_ear["visibility"]) * 0.5,
            }
        if landmarks[6]["visibility"] < 0.1:
            landmarks[6] = {
                "x": (right_eye["x"] + right_ear["x"]) / 2,
                "y": right_eye["y"],
                "z": right_eye["z"],
                "visibility": min(right_eye["visibility"], right_ear["visibility"]) * 0.5,
            }

        # 입 (9: mouth_left, 10: mouth_right)
        left_shoulder = landmarks[11]
        right_shoulder = landmarks[12]

        if landmarks[9]["visibility"] < 0.1:
            landmarks[9] = {
                "x": nose["x"] - 0.02,
                "y": (nose["y"] + left_shoulder["y"]) / 2 * 0.3 + nose["y"] * 0.7,
                "z": nose["z"],
                "visibility": nose["visibility"] * 0.3,
            }
        if landmarks[10]["visibility"] < 0.1:
            landmarks[10] = {
                "x": nose["x"] + 0.02,
                "y": (nose["y"] + right_shoulder["y"]) / 2 * 0.3 + nose["y"] * 0.7,
                "z": nose["z"],
                "visibility": nose["visibility"] * 0.3,
            }

        return landmarks

    @staticmethod
    def normalize_keypoints(
        keypoints: list[dict],
        image_width: int,
        image_height: int,
    ) -> list[dict]:
        """
        픽셀 좌표를 0-1 정규화 좌표로 변환

        Args:
            keypoints: [{x, y, z, visibility}, ...] 픽셀 좌표
            image_width: 이미지 너비
            image_height: 이미지 높이

        Returns:
            정규화된 keypoints
        """
        if image_width <= 0 or image_height <= 0:
            return keypoints

        normalized = []
        for kpt in keypoints:
            normalized.append({
                "x": kpt["x"] / image_width,
                "y": kpt["y"] / image_height,
                "z": kpt.get("z", 0.0),
                "visibility": kpt.get("visibility", 1.0),
            })
        return normalized

    @staticmethod
    def get_keypoint_count(keypoint_format: KeypointFormat | str) -> int:
        """키포인트 포맷의 점 개수 반환"""
        if isinstance(keypoint_format, str):
            keypoint_format = KeypointFormat(keypoint_format)

        if keypoint_format == KeypointFormat.COCO_17:
            return 17
        return 33


# 모듈 레벨 싱글톤
keypoint_adapter = KeypointAdapter()
