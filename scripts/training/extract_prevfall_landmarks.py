"""
Pre-VFall 이미지 데이터셋 → MediaPipe 33-point 랜드마크 추출

Pre-VFall 이미지 프레임에서 MediaPipe Pose 33개 랜드마크(x,y,z)를 추출하여
train_v2.py 호환 NPZ 파일로 저장합니다.

5클래스 분류:
  0: Normal (비낙상)
  1: Front Fall (전면 낙상) - dizziness_fall_forward, weakness_fall_forward의 Fall
  2: Back Fall (후면 낙상) - Pre-VFall에는 없음
  3: Side Fall (측면 낙상) - dizziness_fall_side, weakness_fall_side의 Fall
  4: Pre-impact (낙상 전조) - 모든 시나리오의 Abnormal

Dataset Structure:
  D:/PreVFall_Data/Pre-VFallp/
  +-- confusion_delirium/    (Normal, Abnormal - separator: _)
  +-- confusion_nph/         (Normal, Abnormal - separator: -)
  +-- dizziness_fall_forward/ (Normal, Abnormal, Fall - separator: -)
  +-- dizziness_fall_side/    (Normal, Abnormal, Fall - separator: -)
  +-- weakness_fall_forward/  (Normal, Abnormal, Fall - separator: -)
  +-- weakness_fall_side/     (Normal, Abnormal, Fall - separator: -)

  각 시나리오: 18 actors, actor 폴더 안에 이미지 + *-json/ OpenPose JSON
  이미지 이름: _{ActorID}_{FrameNumber}.jpg

Extraction Modes:
  --mode mediapipe: MediaPipe IMAGE 모드로 직접 추출 (정확, 느림)
  --mode openpose:  기존 OpenPose 25-point JSON → MediaPipe 33-point 변환 (빠름, z=0)

Usage:
    python scripts/training/extract_prevfall_landmarks.py \\
        --data-root D:/PreVFall_Data/Pre-VFallp \\
        --output-dir D:/PreVFall_Data/landmarks \\
        --mode mediapipe \\
        --resume
"""

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

import cv2
import numpy as np

# ──────────────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────────────

CLASS_NAMES = ["normal", "front_fall", "back_fall", "side_fall", "pre_impact"]

# Scenario definitions
# (scenario_name, separator, folder_types, fall_class)
# fall_class: None = no Fall folder, 1 = front_fall, 3 = side_fall
SCENARIOS = {
    "confusion_delirium":    {"sep": "_", "has_fall": False, "fall_class": None},
    "confusion_nph":         {"sep": "-", "has_fall": False, "fall_class": None},
    "dizziness_fall_forward": {"sep": "-", "has_fall": True,  "fall_class": 1},
    "dizziness_fall_side":    {"sep": "-", "has_fall": True,  "fall_class": 3},
    "weakness_fall_forward":  {"sep": "-", "has_fall": True,  "fall_class": 1},
    "weakness_fall_side":     {"sep": "-", "has_fall": True,  "fall_class": 3},
}

# MediaPipe model
_MODEL_PATH = "D:/AIHub_Fall_Data/pose_landmarker_lite.task"
_MODEL_URL = "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/latest/pose_landmarker_lite.task"

# MediaPipe flip pairs (for augmentation)
_FLIP_PAIRS = [
    (1, 4), (2, 5), (3, 6),
    (7, 8), (9, 10), (11, 12),
    (13, 14), (15, 16), (17, 18),
    (19, 20), (21, 22), (23, 24),
    (25, 26), (27, 28), (29, 30), (31, 32),
]

# OpenPose 25-point (BODY_25) → MediaPipe 33-point mapping
# OpenPose BODY_25 indices:
#  0: Nose, 1: Neck, 2: RShoulder, 3: RElbow, 4: RWrist,
#  5: LShoulder, 6: LElbow, 7: LWrist, 8: MidHip,
#  9: RHip, 10: RKnee, 11: RAnkle, 12: LHip, 13: LKnee, 14: LAnkle,
#  15: REye, 16: LEye, 17: REar, 18: LEar,
#  19: LBigToe, 20: LSmallToe, 21: LHeel,
#  22: RBigToe, 23: RSmallToe, 24: RHeel
OPENPOSE25_TO_MP33_DIRECT = {
    # OpenPose idx → MediaPipe idx
    0: 0,     # Nose → nose
    16: 2,    # LEye → l_eye
    15: 5,    # REye → r_eye
    18: 7,    # LEar → l_ear
    17: 8,    # REar → r_ear
    5: 11,    # LShoulder → l_shoulder
    2: 12,    # RShoulder → r_shoulder
    6: 13,    # LElbow → l_elbow
    3: 14,    # RElbow → r_elbow
    7: 15,    # LWrist → l_wrist
    4: 16,    # RWrist → r_wrist
    12: 23,   # LHip → l_hip
    9: 24,    # RHip → r_hip
    13: 25,   # LKnee → l_knee
    10: 26,   # RKnee → r_knee
    14: 27,   # LAnkle → l_ankle
    11: 28,   # RAnkle → r_ankle
    21: 29,   # LHeel → l_heel
    24: 30,   # RHeel → r_heel
    19: 31,   # LBigToe → l_foot_index
    22: 32,   # RBigToe → r_foot_index
}


# ──────────────────────────────────────────────────────
# Dataset Scanning
# ──────────────────────────────────────────────────────

def scan_prevfall_dataset(data_root: str, scenarios_filter: list[str] | None = None) -> list[dict]:
    """
    Pre-VFall 데이터셋을 스캔하여 actor/folder 엔트리 목록을 생성합니다.

    실제 디렉토리 구조 (2단계):
      scenario/ → actor/ → {ActorID}{sep}{Type}/ (이미지 폴더)
                           {ActorID}{sep}{Type}-json/ (OpenPose JSON)

    예시:
      confusion_delirium/CLFM1/CLFM1_Normal/     (sep=_)
      confusion_delirium/CLFM1/CLFM1_Abnormal/
      dizziness_fall_forward/FDFFM1/FDFFM1-Normal/  (sep=-)
      dizziness_fall_forward/FDFFM1/FDFFM1-Fall/

    Returns:
        list of {
            "scenario": str, "actor_id": str,
            "folder_path": str, "folder_type": str (Normal/Abnormal/Fall),
            "label": int, "json_folder": str | None
        }
    """
    root = Path(data_root)
    entries = []

    for scenario_name, info in SCENARIOS.items():
        if scenarios_filter and scenario_name not in scenarios_filter:
            continue

        scenario_dir = root / scenario_name
        if not scenario_dir.exists():
            print(f"  [WARN] 시나리오 폴더 없음: {scenario_dir}")
            continue

        sep = info["sep"]

        # 1단계: actor 폴더 열거 (e.g. CLFM1, FDFFM1)
        for actor_dir in sorted(scenario_dir.iterdir()):
            if not actor_dir.is_dir():
                continue
            # mp4 파일이 아닌 폴더만
            if actor_dir.suffix == ".mp4":
                continue

            actor_name = actor_dir.name

            # 2단계: actor 안의 타입 폴더 열거 (e.g. CLFM1_Normal, FDFFM1-Fall)
            for type_dir in sorted(actor_dir.iterdir()):
                if not type_dir.is_dir():
                    continue

                dirname = type_dir.name

                # json 폴더 건너뛰기
                if dirname.endswith("-json") or dirname.endswith("_json"):
                    continue

                # 타입 판별: ActorID{sep}Type 패턴에서 Type 추출
                # e.g. "CLFM1_Normal" → Type="Normal", "FDFFM1-Fall" → Type="Fall"
                folder_type = None

                # actor_name + sep + Type 패턴 매칭
                prefix = actor_name + sep
                if dirname.startswith(prefix):
                    folder_type = dirname[len(prefix):]
                else:
                    # 폴백: 이름에서 타입 키워드 검색
                    lower = dirname.lower()
                    if "normal" in lower and "abnormal" not in lower:
                        folder_type = "Normal"
                    elif "abnormal" in lower:
                        folder_type = "Abnormal"
                    elif "fall" in lower:
                        folder_type = "Fall"
                    else:
                        continue

                if folder_type is None:
                    continue

                # 라벨 결정
                folder_type_lower = folder_type.lower()
                if folder_type_lower == "normal":
                    label = 0
                elif folder_type_lower == "abnormal":
                    label = 4  # pre_impact
                elif folder_type_lower == "fall":
                    if info["has_fall"] and info["fall_class"] is not None:
                        label = info["fall_class"]
                    else:
                        print(f"  [WARN] Fall 폴더가 has_fall=False 시나리오에 존재: {type_dir}")
                        continue
                else:
                    continue

                # OpenPose JSON 폴더 확인
                json_folder = None
                json_candidate = actor_dir / f"{dirname}-json"
                if json_candidate.exists():
                    json_folder = str(json_candidate)
                else:
                    json_candidate2 = actor_dir / f"{dirname}_json"
                    if json_candidate2.exists():
                        json_folder = str(json_candidate2)

                entries.append({
                    "scenario": scenario_name,
                    "actor_id": f"{scenario_name}/{actor_name}/{dirname}",
                    "folder_path": str(type_dir),
                    "folder_type": folder_type,
                    "label": label,
                    "json_folder": json_folder,
                })

    return entries


def discover_frames(folder_path: str) -> list[tuple[int, str]]:
    """
    폴더에서 이미지 프레임을 발견하고 프레임 번호순으로 정렬합니다.

    이미지 이름 패턴: *_{FrameNumber}.jpg

    Returns:
        list of (frame_number, file_path) sorted by frame_number
    """
    pattern = re.compile(r"_(\d+)\.jpg$", re.IGNORECASE)
    frames = []

    folder = Path(folder_path)
    for img_path in folder.iterdir():
        if not img_path.is_file():
            continue
        if img_path.suffix.lower() not in (".jpg", ".jpeg", ".png"):
            continue

        match = pattern.search(img_path.name)
        if match:
            frame_num = int(match.group(1))
            frames.append((frame_num, str(img_path)))

    frames.sort(key=lambda x: x[0])
    return frames


# ──────────────────────────────────────────────────────
# MediaPipe Landmark Extraction (IMAGE mode)
# ──────────────────────────────────────────────────────

def ensure_model():
    """포즈 모델 파일이 없으면 다운로드"""
    if not os.path.exists(_MODEL_PATH):
        print(f"포즈 모델 다운로드 중: {_MODEL_URL}")
        import urllib.request
        os.makedirs(os.path.dirname(_MODEL_PATH), exist_ok=True)
        urllib.request.urlretrieve(_MODEL_URL, _MODEL_PATH)
        print(f"  완료: {os.path.getsize(_MODEL_PATH) / 1024 / 1024:.1f} MB")


def extract_landmarks_mediapipe(image_paths: list[str]) -> np.ndarray | None:
    """
    MediaPipe IMAGE 모드로 이미지 시퀀스에서 33-point 랜드마크를 추출합니다.

    Args:
        image_paths: 정렬된 이미지 경로 목록

    Returns:
        landmarks: (N_frames, 33, 3) numpy array 또는 None
    """
    import mediapipe as mp
    from mediapipe.tasks.python import BaseOptions
    from mediapipe.tasks.python.vision import (
        PoseLandmarker,
        PoseLandmarkerOptions,
        RunningMode,
    )

    options = PoseLandmarkerOptions(
        base_options=BaseOptions(model_asset_path=_MODEL_PATH),
        running_mode=RunningMode.IMAGE,
        num_poses=1,
        min_pose_detection_confidence=0.5,
    )

    landmarks_list = []

    with PoseLandmarker.create_from_options(options) as landmarker:
        for img_path in image_paths:
            frame = cv2.imread(img_path)
            if frame is None:
                # 읽기 실패: 이전 프레임 복사 또는 zero-pad
                if landmarks_list:
                    landmarks_list.append(landmarks_list[-1])
                else:
                    landmarks_list.append([[0.0, 0.0, 0.0]] * 33)
                continue

            # 리사이즈 (속도 최적화)
            small = cv2.resize(frame, (640, 480))
            rgb = cv2.cvtColor(small, cv2.COLOR_BGR2RGB)

            mp_image = mp.Image(
                image_format=mp.ImageFormat.SRGB,
                data=rgb,
            )

            result = landmarker.detect(mp_image)

            if result.pose_landmarks and len(result.pose_landmarks) > 0:
                frame_lm = []
                for lm in result.pose_landmarks[0]:
                    frame_lm.append([lm.x, lm.y, lm.z])
                landmarks_list.append(frame_lm)
            else:
                # 미감지 시 이전 프레임 복사 또는 zero-pad
                if landmarks_list:
                    landmarks_list.append(landmarks_list[-1])
                else:
                    landmarks_list.append([[0.0, 0.0, 0.0]] * 33)

    if not landmarks_list:
        return None

    return np.array(landmarks_list, dtype=np.float32)  # (N, 33, 3)


# ──────────────────────────────────────────────────────
# OpenPose 25-point JSON → MediaPipe 33-point Conversion
# ──────────────────────────────────────────────────────

def openpose25_to_mediapipe33(kps_25: np.ndarray) -> np.ndarray:
    """
    OpenPose BODY_25 키포인트를 MediaPipe 33-point 형식으로 변환합니다.

    Args:
        kps_25: (25, 3) - [x, y, confidence]

    Returns:
        mp33: (33, 3) - [x, y, z] (z=0, OpenPose는 2D)
    """
    mp33 = np.zeros((33, 3), dtype=np.float32)
    n_kp = kps_25.shape[0]

    xy = kps_25[:, :2].copy()
    conf = kps_25[:, 2].copy() if kps_25.shape[1] >= 3 else np.ones(n_kp, dtype=np.float32)

    # 1단계: 직접 매핑 (21개 포인트)
    for op_idx, mp_idx in OPENPOSE25_TO_MP33_DIRECT.items():
        if op_idx < n_kp and conf[op_idx] > 0.1:
            mp33[mp_idx, 0] = xy[op_idx, 0]
            mp33[mp_idx, 1] = xy[op_idx, 1]
            # z = 0

    # 2단계: 보간 (12개 포인트)
    # l_eye_inner (1): l_eye(2)와 nose(0)의 중점
    mp33[1] = (mp33[2] + mp33[0]) / 2.0

    # l_eye_outer (3): l_eye(2)와 l_ear(7)의 중점
    mp33[3] = (mp33[2] + mp33[7]) / 2.0

    # r_eye_inner (4): r_eye(5)와 nose(0)의 중점
    mp33[4] = (mp33[5] + mp33[0]) / 2.0

    # r_eye_outer (6): r_eye(5)와 r_ear(8)의 중점
    mp33[6] = (mp33[5] + mp33[8]) / 2.0

    # mouth_l (9): nose(0)와 l_shoulder(11)의 가중 평균 (nose 75%)
    mp33[9] = mp33[0] * 0.75 + mp33[11] * 0.25

    # mouth_r (10): nose(0)와 r_shoulder(12)의 가중 평균 (nose 75%)
    mp33[10] = mp33[0] * 0.75 + mp33[12] * 0.25

    # l_pinky (17): l_wrist(15) 기준 이동
    mp33[17] = _offset_from(mp33[15], mp33[13], scale=0.1)

    # r_pinky (18): r_wrist(16) 기준 이동
    mp33[18] = _offset_from(mp33[16], mp33[14], scale=0.1)

    # l_index (19): l_wrist(15) 기준 이동
    mp33[19] = _offset_from(mp33[15], mp33[13], scale=0.12)

    # r_index (20): r_wrist(16) 기준 이동
    mp33[20] = _offset_from(mp33[16], mp33[14], scale=0.12)

    # l_thumb (21): l_wrist(15) 기준 이동
    mp33[21] = _offset_from(mp33[15], mp33[13], scale=0.08)

    # r_thumb (22): r_wrist(16) 기준 이동
    mp33[22] = _offset_from(mp33[16], mp33[14], scale=0.08)

    return mp33


def _offset_from(point: np.ndarray, ref: np.ndarray, scale: float) -> np.ndarray:
    """point에서 ref 방향의 반대로 scale만큼 이동"""
    direction = point - ref
    norm = np.linalg.norm(direction)
    if norm > 1e-6:
        direction = direction / norm
    return point + direction * scale


def extract_landmarks_openpose(
    json_folder: str,
    frame_nums: list[int],
    image_width: int = 640,
    image_height: int = 480,
) -> np.ndarray | None:
    """
    OpenPose JSON 파일에서 25-point 키포인트를 로드하고 MediaPipe 33-point로 변환합니다.

    OpenPose는 픽셀 좌표를 출력하므로 이미지 크기로 나누어 [0,1] 범위로 정규화합니다.

    Args:
        json_folder: OpenPose JSON 폴더 경로
        frame_nums: 프레임 번호 목록
        image_width: OpenPose가 처리한 이미지 너비 (정규화용)
        image_height: OpenPose가 처리한 이미지 높이 (정규화용)

    Returns:
        landmarks: (N_frames, 33, 3) numpy array 또는 None
    """
    json_dir = Path(json_folder)
    landmarks_list = []

    # 이미지 크기 자동 감지: JSON과 같은 폴더에 이미지가 있을 수 있음
    img_w, img_h = float(image_width), float(image_height)

    for frame_num in frame_nums:
        # OpenPose JSON 파일명 패턴 시도
        json_path = None
        for pattern in [
            f"*_{frame_num:012d}_keypoints.json",
            f"*_{frame_num:06d}_keypoints.json",
            f"*_{frame_num}_keypoints.json",
        ]:
            matches = list(json_dir.glob(pattern))
            if matches:
                json_path = matches[0]
                break

        if json_path is None:
            # 못 찾으면 이전 프레임 복사 또는 zero-pad
            if landmarks_list:
                landmarks_list.append(landmarks_list[-1])
            else:
                landmarks_list.append(np.zeros((33, 3), dtype=np.float32))
            continue

        try:
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            people = data.get("people", [])
            if not people:
                if landmarks_list:
                    landmarks_list.append(landmarks_list[-1])
                else:
                    landmarks_list.append(np.zeros((33, 3), dtype=np.float32))
                continue

            # 첫 번째 사람의 키포인트
            kps_flat = people[0].get("pose_keypoints_2d", [])
            if len(kps_flat) < 75:  # 25 * 3
                if landmarks_list:
                    landmarks_list.append(landmarks_list[-1])
                else:
                    landmarks_list.append(np.zeros((33, 3), dtype=np.float32))
                continue

            kps_25 = np.array(kps_flat[:75], dtype=np.float32).reshape(25, 3)

            # 픽셀 좌표를 [0,1] 범위로 정규화 (confidence는 유지)
            kps_25[:, 0] /= img_w
            kps_25[:, 1] /= img_h

            mp33 = openpose25_to_mediapipe33(kps_25)
            landmarks_list.append(mp33)

        except Exception:
            if landmarks_list:
                landmarks_list.append(landmarks_list[-1])
            else:
                landmarks_list.append(np.zeros((33, 3), dtype=np.float32))

    if not landmarks_list:
        return None

    return np.array(landmarks_list, dtype=np.float32)  # (N, 33, 3)


# ──────────────────────────────────────────────────────
# Sequence Processing
# ──────────────────────────────────────────────────────

def split_by_gaps(
    frame_nums: list[int],
    landmarks: np.ndarray,
    gap_threshold: int = 15,
) -> list[tuple[list[int], np.ndarray]]:
    """
    프레임 번호 간 갭이 threshold를 초과하면 시퀀스를 분리합니다.

    Args:
        frame_nums: 정렬된 프레임 번호 목록
        landmarks: (N, 33, 3) 랜드마크 배열
        gap_threshold: 갭 임계값

    Returns:
        list of (frame_nums_segment, landmarks_segment)
    """
    if len(frame_nums) == 0:
        return []

    segments = []
    seg_start = 0

    for i in range(1, len(frame_nums)):
        if frame_nums[i] - frame_nums[i - 1] > gap_threshold:
            segments.append((
                frame_nums[seg_start:i],
                landmarks[seg_start:i],
            ))
            seg_start = i

    # Last segment
    segments.append((
        frame_nums[seg_start:],
        landmarks[seg_start:],
    ))

    return segments


def pad_landmarks(landmarks: np.ndarray, seq_len: int = 30, min_frames: int = 10) -> np.ndarray | None:
    """
    짧은 랜드마크 시퀀스를 edge padding으로 seq_len까지 채웁니다.

    마지막 프레임을 반복하여 패딩합니다 (낙상 후 자세 유지에 자연스러움).

    Args:
        landmarks: (N_frames, 33, 3)
        seq_len: 목표 프레임 수
        min_frames: 최소 프레임 수 (이 미만은 패딩해도 무의미)

    Returns:
        padded: (seq_len, 33, 3) 또는 None (너무 짧은 경우)
    """
    n_frames = landmarks.shape[0]
    if n_frames >= seq_len:
        return landmarks
    if n_frames < min_frames:
        return None

    # Edge padding: 마지막 프레임 반복
    pad_count = seq_len - n_frames
    last_frame = landmarks[-1:, :, :]  # (1, 33, 3)
    padding = np.repeat(last_frame, pad_count, axis=0)  # (pad_count, 33, 3)
    padded = np.concatenate([landmarks, padding], axis=0)  # (seq_len, 33, 3)

    return padded


def create_sequences(
    landmarks: np.ndarray,
    label: int,
    seq_len: int = 30,
    stride: int = 15,
) -> list[tuple[np.ndarray, int]]:
    """
    랜드마크에서 슬라이딩 윈도우 시퀀스를 생성합니다.

    30프레임 미만(10프레임 이상)인 경우 edge padding으로 채운 뒤
    단일 시퀀스를 생성합니다.

    Args:
        landmarks: (N_frames, 33, 3)
        label: 클래스 라벨
        seq_len: 윈도우 크기
        stride: 윈도우 간격

    Returns:
        list of (sequence(seq_len, 99), label)
    """
    n_frames = landmarks.shape[0]

    # 짧은 클립: edge padding 적용
    if n_frames < seq_len:
        padded = pad_landmarks(landmarks, seq_len)
        if padded is None:
            return []
        flat = padded.reshape(seq_len, -1)  # (seq_len, 99)
        return [(flat, label)]

    flat = landmarks.reshape(n_frames, -1)  # (N, 99)
    sequences = []

    for start in range(0, n_frames - seq_len + 1, stride):
        end = start + seq_len
        seq = flat[start:end]
        if seq.shape == (seq_len, 99):
            sequences.append((seq, label))

    return sequences


# ──────────────────────────────────────────────────────
# Data Augmentation
# ──────────────────────────────────────────────────────

def augment_jitter(sequence: np.ndarray, sigma: float = 0.003, rng: np.random.RandomState = None) -> np.ndarray:
    """좌표 가우시안 노이즈"""
    if rng is None:
        rng = np.random.RandomState()
    noise = rng.normal(0, sigma, sequence.shape).astype(np.float32)
    return sequence + noise


def augment_horizontal_flip(sequence: np.ndarray) -> np.ndarray:
    """좌우 반전 (33개 랜드마크 쌍 교환, x좌표 반전)"""
    seq_len = sequence.shape[0]
    lm = sequence.reshape(seq_len, 33, 3).copy()
    lm[:, :, 0] = 1.0 - lm[:, :, 0]
    for left, right in _FLIP_PAIRS:
        lm[:, [left, right], :] = lm[:, [right, left], :]
    return lm.reshape(seq_len, -1)


def augment_scale(sequence: np.ndarray, scale_range: tuple = (0.9, 1.1), rng: np.random.RandomState = None) -> np.ndarray:
    """체형 변화 시뮬레이션"""
    if rng is None:
        rng = np.random.RandomState()
    scale = rng.uniform(scale_range[0], scale_range[1])
    seq_len = sequence.shape[0]
    lm = sequence.reshape(seq_len, 33, 3).copy()
    center = lm.mean(axis=1, keepdims=True)
    lm = center + (lm - center) * scale
    return lm.reshape(seq_len, -1).astype(np.float32)


def augment_temporal_noise(sequence: np.ndarray, rng: np.random.RandomState = None) -> np.ndarray:
    """프레임 드롭/복제 시뮬레이션"""
    if rng is None:
        rng = np.random.RandomState()
    result = sequence.copy()
    seq_len = result.shape[0]
    n_replace = max(1, seq_len // 10)
    indices = rng.choice(range(1, seq_len), size=min(n_replace, seq_len - 1), replace=False)
    for idx in indices:
        result[idx] = result[idx - 1]
    return result


def apply_augmentations(
    sequence: np.ndarray,
    label: int,
    rng: np.random.RandomState,
) -> list[tuple[np.ndarray, int]]:
    """원본 시퀀스에 증강 2~3개 추가 복사본 생성"""
    augmented = []

    # 증강 1: jitter + temporal noise
    aug1 = augment_jitter(sequence, sigma=0.003, rng=rng)
    aug1 = augment_temporal_noise(aug1, rng=rng)
    augmented.append((aug1, label))

    # 증강 2: horizontal flip + scale
    aug2 = augment_horizontal_flip(sequence)
    aug2 = augment_scale(aug2, rng=rng)
    augmented.append((aug2, label))

    # 증강 3 (50% 확률): jitter + scale + flip
    if rng.random() < 0.5:
        aug3 = augment_jitter(sequence, sigma=0.002, rng=rng)
        aug3 = augment_horizontal_flip(aug3)
        aug3 = augment_scale(aug3, scale_range=(0.92, 1.08), rng=rng)
        augmented.append((aug3, label))

    return augmented


# ──────────────────────────────────────────────────────
# Actor-level Processing
# ──────────────────────────────────────────────────────

def process_actor(
    entry: dict,
    mode: str,
    seq_len: int = 30,
    stride: int = 15,
    gap_threshold: int = 15,
) -> dict | None:
    """
    단일 actor 폴더를 처리하여 시퀀스를 생성합니다.

    Args:
        entry: scan_prevfall_dataset()에서 반환된 엔트리
        mode: "mediapipe" 또는 "openpose"
        seq_len: 시퀀스 길이
        stride: 슬라이딩 윈도우 간격
        gap_threshold: 프레임 갭 임계값

    Returns:
        {"actor_id": str, "X": ndarray, "y": ndarray} 또는 None
    """
    folder_path = entry["folder_path"]
    label = entry["label"]

    try:
        # 프레임 발견
        frames = discover_frames(folder_path)
        if not frames:
            return None

        frame_nums = [f[0] for f in frames]
        image_paths = [f[1] for f in frames]

        # 랜드마크 추출
        if mode == "openpose":
            if entry["json_folder"]:
                landmarks = extract_landmarks_openpose(entry["json_folder"], frame_nums)
            else:
                print(f"  [WARN] OpenPose JSON 없음, MediaPipe 폴백: {entry['actor_id']}")
                landmarks = extract_landmarks_mediapipe(image_paths)
        else:
            landmarks = extract_landmarks_mediapipe(image_paths)

        if landmarks is None or len(landmarks) < seq_len:
            return None

        # 프레임 갭으로 시퀀스 분리
        segments = split_by_gaps(frame_nums, landmarks, gap_threshold)

        all_seqs = []
        for seg_frames, seg_landmarks in segments:
            seqs = create_sequences(seg_landmarks, label, seq_len, stride)
            all_seqs.extend(seqs)

        if not all_seqs:
            return None

        # Shape 검증
        valid_seqs = [(s, l) for s, l in all_seqs if s.shape == (seq_len, 99)]
        if not valid_seqs:
            return None

        X = np.array([s for s, _ in valid_seqs], dtype=np.float32)
        y = np.array([l for _, l in valid_seqs], dtype=np.int64)

        return {"actor_id": entry["actor_id"], "X": X, "y": y}

    except Exception as e:
        print(f"  [ERROR] {entry['actor_id']}: {e}", flush=True)
        return None


# ──────────────────────────────────────────────────────
# Utility
# ──────────────────────────────────────────────────────

def format_eta(seconds: float) -> str:
    """초를 HH:MM:SS 형식으로 변환"""
    if seconds < 0 or seconds > 86400 * 7:
        return "??:??:??"
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    if h > 0:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


# ──────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Pre-VFall 이미지 데이터셋 → MediaPipe 33-point 랜드마크 추출"
    )
    parser.add_argument("--data-root", type=str, default="D:/PreVFall_Data/Pre-VFallp",
                        help="Pre-VFall 데이터 루트 경로")
    parser.add_argument("--output-dir", type=str, default="D:/PreVFall_Data/landmarks",
                        help="출력 디렉토리")
    parser.add_argument("--mode", type=str, default="mediapipe",
                        choices=["mediapipe", "openpose"],
                        help="추출 모드: mediapipe (정확) 또는 openpose (빠름)")
    parser.add_argument("--seq-len", type=int, default=30,
                        help="시퀀스 길이 (프레임)")
    parser.add_argument("--stride", type=int, default=15,
                        help="슬라이딩 윈도우 간격")
    parser.add_argument("--gap-threshold", type=int, default=15,
                        help="프레임 갭 임계값 (초과 시 시퀀스 분리)")
    parser.add_argument("--chunk-size", type=int, default=10,
                        help="청크당 actor 수 (메모리 관리)")
    parser.add_argument("--augment", action="store_true", default=True,
                        help="데이터 증강 활성화 (기본: ON)")
    parser.add_argument("--no-augment", action="store_true",
                        help="데이터 증강 비활성화")
    parser.add_argument("--resume", action="store_true", default=False,
                        help="이전 실행에서 중단된 지점부터 재개")
    parser.add_argument("--scenarios", type=str, nargs="+", default=None,
                        help="처리할 시나리오 목록 (기본: 전체)")
    args = parser.parse_args()

    if args.no_augment:
        args.augment = False

    os.makedirs(args.output_dir, exist_ok=True)

    # MediaPipe 모드일 때만 모델 필요
    if args.mode == "mediapipe":
        ensure_model()

    # 데이터셋 스캔
    print(f"데이터셋 스캔 중: {args.data_root}")
    entries = scan_prevfall_dataset(args.data_root, args.scenarios)
    print(f"  총 actor 폴더: {len(entries)}")

    if not entries:
        print("처리할 데이터가 없습니다.")
        sys.exit(1)

    # 시나리오별 카운트
    by_scenario = {}
    by_label = {}
    for e in entries:
        by_scenario.setdefault(e["scenario"], []).append(e)
        by_label.setdefault(e["label"], []).append(e)

    print("\n시나리오별 분포:")
    for scenario, items in sorted(by_scenario.items()):
        types = {}
        for item in items:
            types.setdefault(item["folder_type"], 0)
            types[item["folder_type"]] += 1
        type_str = ", ".join(f"{k}={v}" for k, v in sorted(types.items()))
        print(f"  {scenario}: {len(items)} ({type_str})")

    print("\n라벨별 분포:")
    for label, items in sorted(by_label.items()):
        print(f"  {CLASS_NAMES[label]} ({label}): {len(items)} actors")

    print(f"\n추출 모드: {args.mode}")
    print(f"시퀀스: {args.seq_len}프레임, 스트라이드={args.stride}, 갭={args.gap_threshold}")
    print(f"증강: {'ON (원본당 2~3개 복사본)' if args.augment else 'OFF'}")

    # 청크 처리
    chunk_size = args.chunk_size if args.chunk_size > 0 else len(entries)
    chunks = [entries[i:i + chunk_size] for i in range(0, len(entries), chunk_size)]

    chunk_dir = os.path.join(args.output_dir, "prevfall_chunks")
    os.makedirs(chunk_dir, exist_ok=True)

    processed = 0
    failed = 0
    skipped_chunks = 0
    start_time = time.time()
    rng = np.random.RandomState(42)

    print(f"\n랜드마크 추출 시작... ({len(chunks)} 청크, 청크당 {chunk_size} actors)")
    if args.resume:
        print("  재개 모드: 완료된 청크를 건너뜁니다.")

    for chunk_idx, chunk in enumerate(chunks):
        chunk_path = os.path.join(chunk_dir, f"chunk_{chunk_idx:04d}.npz")

        # 재개 모드: 이미 저장된 청크 건너뜀
        if args.resume and os.path.exists(chunk_path):
            try:
                saved = np.load(chunk_path)
                processed += int(saved.get("processed", 0))
                failed += int(saved.get("failed", 0))
                skipped_chunks += 1
                # rng 상태 동기화
                for _ in range(len(chunk)):
                    rng.random()
                continue
            except Exception:
                pass  # 손상된 청크는 재처리

        print(f"\n--- 청크 {chunk_idx + 1}/{len(chunks)} ({len(chunk)} actors) ---")

        chunk_X = []
        chunk_y = []
        chunk_processed = 0
        chunk_failed = 0

        for i, entry in enumerate(chunk):
            global_idx = chunk_idx * chunk_size + i

            result = process_actor(
                entry, args.mode,
                seq_len=args.seq_len,
                stride=args.stride,
                gap_threshold=args.gap_threshold,
            )

            if result:
                # 원본 시퀀스 추가
                chunk_X.append(result["X"])
                chunk_y.append(result["y"])

                # 데이터 증강
                if args.augment:
                    for seq, lbl in zip(result["X"], result["y"]):
                        aug_pairs = apply_augmentations(seq, lbl, rng)
                        if aug_pairs:
                            aug_X = np.array([a[0] for a in aug_pairs], dtype=np.float32)
                            aug_y = np.array([a[1] for a in aug_pairs], dtype=np.int64)
                            chunk_X.append(aug_X)
                            chunk_y.append(aug_y)

                chunk_processed += 1
                status = f"{result['X'].shape[0]} seqs"
            else:
                chunk_failed += 1
                status = "FAILED"

            # 진행률 표시
            elapsed = time.time() - start_time
            total_done = global_idx + 1
            speed = total_done / elapsed if elapsed > 0 else 0
            remaining = (len(entries) - total_done) / speed if speed > 0 else 0
            pct = total_done / len(entries) * 100

            print(
                f"  [{total_done}/{len(entries)}] {pct:.1f}% | "
                f"{entry['actor_id']} → {status} | "
                f"ETA={format_eta(remaining)}",
                flush=True,
            )

        # 청크 저장
        if chunk_X:
            cX = np.concatenate(chunk_X, axis=0)
            cy = np.concatenate(chunk_y, axis=0)
            np.savez_compressed(
                chunk_path, X=cX, y=cy,
                processed=np.array(chunk_processed),
                failed=np.array(chunk_failed),
            )
            size_kb = os.path.getsize(chunk_path) / 1024
            print(f"  -> 청크 저장: {chunk_path} ({cX.shape[0]} 시퀀스, {size_kb:.0f} KB)")
        else:
            np.savez_compressed(
                chunk_path,
                X=np.empty((0, args.seq_len, 99), dtype=np.float32),
                y=np.empty(0, dtype=np.int64),
                processed=np.array(chunk_processed),
                failed=np.array(chunk_failed),
            )

        processed += chunk_processed
        failed += chunk_failed

    if args.resume and skipped_chunks > 0:
        print(f"\n재개: {skipped_chunks}개 청크 건너뜀")

    # ── 청크 병합 ──
    print("\n청크 병합 중...")
    all_X = []
    all_y = []
    chunk_files = sorted(Path(chunk_dir).glob("chunk_*.npz"))

    for cf in chunk_files:
        try:
            data = np.load(str(cf))
            if data["X"].shape[0] > 0:
                all_X.append(data["X"])
                all_y.append(data["y"])
        except Exception as e:
            print(f"  [WARN] 청크 로드 실패: {cf.name}: {e}")

    if not all_X:
        print("추출된 시퀀스가 없습니다.")
        sys.exit(1)

    X = np.concatenate(all_X, axis=0)
    y = np.concatenate(all_y, axis=0)

    elapsed_total = time.time() - start_time

    print(f"\n추출 완료 (소요: {format_eta(elapsed_total)}):")
    print(f"  총 시퀀스: {len(X)}")
    print(f"  처리 actors: {processed}, 실패: {failed}")
    for cls_id, cls_name in enumerate(CLASS_NAMES):
        count = int(np.sum(y == cls_id))
        if count > 0:
            print(f"  {cls_name} ({cls_id}): {count}")
    print(f"  Shape: X={X.shape}, y={y.shape}")

    # 최종 통합 파일 저장
    out_path = os.path.join(args.output_dir, "prevfall_landmarks.npz")
    np.savez_compressed(
        out_path,
        X=X,
        y=y,
        class_names=np.array(CLASS_NAMES),
    )
    file_size = os.path.getsize(out_path) / 1024 / 1024
    print(f"\n저장: {out_path} ({file_size:.1f} MB)")


if __name__ == "__main__":
    main()
