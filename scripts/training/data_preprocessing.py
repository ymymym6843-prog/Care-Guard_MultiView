"""
Sentio - 다중 데이터셋 전처리 및 통합 파이프라인

OpenPose 18점 → MediaPipe 33점 좌표 매핑을 수행하고,
Pre-VFall / AI Hub 데이터를 통합 .npz 포맷으로 변환합니다.

지원 입력:
  1. Pre-VFall CSV (OpenPose 18-point keypoints + phase labels)
  2. AI Hub .npz (이미 MediaPipe 33-point, extract_landmarks.py로 추출된 것)

출력 포맷:
  .npz 파일:
    X: (N, 30, 99)  - 30프레임 × 33랜드마크 × 3좌표(x,y,z)
    y: (N,)          - 클래스 라벨
    class_names: 클래스 이름 배열

확장된 5클래스:
  0: Normal (비낙상)
  1: Front Fall (전면 낙상)
  2: Back Fall (후면 낙상)
  3: Side Fall (측면 낙상)
  4: Pre-impact (낙상 전조)

Usage:
    # Pre-VFall CSV → .npz 변환
    python scripts/training/data_preprocessing.py \\
        --source prevfall \\
        --input-dir D:/PreVFall_Data \\
        --output D:/PreVFall_Data/landmarks/prevfall_landmarks.npz

    # AI Hub + Pre-VFall 통합
    python scripts/training/data_preprocessing.py \\
        --source merge \\
        --aihub-npz D:/AIHub_Fall_Data/landmarks/training_landmarks.npz \\
        --prevfall-npz D:/PreVFall_Data/landmarks/prevfall_landmarks.npz \\
        --output D:/merged_landmarks.npz

    # 통합 데이터 통계 확인
    python scripts/training/data_preprocessing.py \\
        --source stats \\
        --input-npz D:/merged_landmarks.npz
"""

import argparse
import csv
import os
import sys
from pathlib import Path

import numpy as np


# ──────────────────────────────────────────────────────
# OpenPose 18점 → MediaPipe 33점 매핑
# ──────────────────────────────────────────────────────

# OpenPose COCO 18-point 인덱스
OPENPOSE_NAMES = [
    "nose",          # 0
    "neck",          # 1
    "r_shoulder",    # 2
    "r_elbow",       # 3
    "r_wrist",       # 4
    "l_shoulder",    # 5
    "l_elbow",       # 6
    "l_wrist",       # 7
    "r_hip",         # 8
    "r_knee",        # 9
    "r_ankle",       # 10
    "l_hip",         # 11
    "l_knee",        # 12
    "l_ankle",       # 13
    "r_eye",         # 14
    "l_eye",         # 15
    "r_ear",         # 16
    "l_ear",         # 17
]

# MediaPipe 33-point 인덱스
MEDIAPIPE_NAMES = [
    "nose",           # 0
    "l_eye_inner",    # 1
    "l_eye",          # 2
    "l_eye_outer",    # 3
    "r_eye_inner",    # 4
    "r_eye",          # 5
    "r_eye_outer",    # 6
    "l_ear",          # 7
    "r_ear",          # 8
    "mouth_l",        # 9
    "mouth_r",        # 10
    "l_shoulder",     # 11
    "r_shoulder",     # 12
    "l_elbow",        # 13
    "r_elbow",        # 14
    "l_wrist",        # 15
    "r_wrist",        # 16
    "l_pinky",        # 17
    "r_pinky",        # 18
    "l_index",        # 19
    "r_index",        # 20
    "l_thumb",        # 21
    "r_thumb",        # 22
    "l_hip",          # 23
    "r_hip",          # 24
    "l_knee",         # 25
    "r_knee",         # 26
    "l_ankle",        # 27
    "r_ankle",        # 28
    "l_heel",         # 29
    "r_heel",         # 30
    "l_foot_index",   # 31
    "r_foot_index",   # 32
]

# 직접 매핑: OpenPose index → MediaPipe index
# 매핑 불가능한 MediaPipe 포인트는 보간으로 채움
DIRECT_MAPPING = {
    # OpenPose idx → MediaPipe idx
    0: 0,     # nose → nose
    15: 2,    # l_eye → l_eye
    14: 5,    # r_eye → r_eye
    17: 7,    # l_ear → l_ear
    16: 8,    # r_ear → r_ear
    5: 11,    # l_shoulder → l_shoulder
    2: 12,    # r_shoulder → r_shoulder
    6: 13,    # l_elbow → l_elbow
    3: 14,    # r_elbow → r_elbow
    7: 15,    # l_wrist → l_wrist
    4: 16,    # r_wrist → r_wrist
    11: 23,   # l_hip → l_hip
    8: 24,    # r_hip → r_hip
    12: 25,   # l_knee → l_knee
    9: 26,    # r_knee → r_knee
    13: 27,   # l_ankle → l_ankle
    10: 28,   # r_ankle → r_ankle
}


def openpose18_to_mediapipe33(
    openpose_kps: np.ndarray,
    has_confidence: bool = True,
) -> np.ndarray:
    """
    OpenPose 18-point 키포인트를 MediaPipe 33-point 형식으로 변환합니다.

    Args:
        openpose_kps: (18, 3) 또는 (18, 2) - OpenPose 키포인트
                      [x, y, conf] 또는 [x, y]
        has_confidence: True면 3번째 값이 confidence

    Returns:
        mediapipe_kps: (33, 3) - MediaPipe 형식 [x, y, z]
                       z는 OpenPose에 없으므로 0.0으로 채움
    """
    n_kp = openpose_kps.shape[0]
    dim = openpose_kps.shape[1] if len(openpose_kps.shape) > 1 else 1

    # (18, 2) 또는 (18, 3) → 정규화된 (18, 2) xy좌표
    if dim >= 3 and has_confidence:
        xy = openpose_kps[:, :2].copy()
        conf = openpose_kps[:, 2].copy()
    elif dim == 2:
        xy = openpose_kps[:, :2].copy()
        conf = np.ones(n_kp, dtype=np.float32)
    else:
        xy = openpose_kps.reshape(n_kp, -1)[:, :2].copy()
        conf = np.ones(n_kp, dtype=np.float32)

    # MediaPipe 33점 초기화 (x, y, z)
    mp33 = np.zeros((33, 3), dtype=np.float32)

    # 1단계: 직접 매핑
    for op_idx, mp_idx in DIRECT_MAPPING.items():
        if op_idx < n_kp and conf[op_idx] > 0.1:
            mp33[mp_idx, 0] = xy[op_idx, 0]  # x
            mp33[mp_idx, 1] = xy[op_idx, 1]  # y
            # z = 0 (OpenPose는 2D)

    # 2단계: 보간으로 누락 포인트 채우기

    # l_eye_inner (1): l_eye(2)와 nose(0)의 중점
    mp33[1] = _midpoint(mp33[2], mp33[0])

    # l_eye_outer (3): l_eye(2)와 l_ear(7)의 중점
    mp33[3] = _midpoint(mp33[2], mp33[7])

    # r_eye_inner (4): r_eye(5)와 nose(0)의 중점
    mp33[4] = _midpoint(mp33[5], mp33[0])

    # r_eye_outer (6): r_eye(5)와 r_ear(8)의 중점
    mp33[6] = _midpoint(mp33[5], mp33[8])

    # mouth_l (9): nose(0)와 l_shoulder(11)의 가중 평균 (nose 쪽 75%)
    mp33[9] = _weighted_avg(mp33[0], mp33[11], 0.75)

    # mouth_r (10): nose(0)와 r_shoulder(12)의 가중 평균 (nose 쪽 75%)
    mp33[10] = _weighted_avg(mp33[0], mp33[12], 0.75)

    # l_pinky (17): l_wrist(15) 기준 약간 이동
    mp33[17] = _offset_from(mp33[15], mp33[13], scale=0.1)

    # r_pinky (18): r_wrist(16) 기준 약간 이동
    mp33[18] = _offset_from(mp33[16], mp33[14], scale=0.1)

    # l_index (19): l_wrist(15) 기준
    mp33[19] = _offset_from(mp33[15], mp33[13], scale=0.12)

    # r_index (20): r_wrist(16) 기준
    mp33[20] = _offset_from(mp33[16], mp33[14], scale=0.12)

    # l_thumb (21): l_wrist(15) 기준
    mp33[21] = _offset_from(mp33[15], mp33[13], scale=0.08)

    # r_thumb (22): r_wrist(16) 기준
    mp33[22] = _offset_from(mp33[16], mp33[14], scale=0.08)

    # l_heel (29): l_ankle(27) 기준 약간 아래
    mp33[29] = mp33[27].copy()
    mp33[29, 1] += 0.02  # y축으로 약간 아래

    # r_heel (30): r_ankle(28) 기준 약간 아래
    mp33[30] = mp33[28].copy()
    mp33[30, 1] += 0.02

    # l_foot_index (31): l_ankle(27) 기준 약간 앞
    mp33[31] = mp33[27].copy()
    mp33[31, 0] += 0.02  # x축으로 약간 앞
    mp33[31, 1] += 0.03

    # r_foot_index (32): r_ankle(28) 기준 약간 앞
    mp33[32] = mp33[28].copy()
    mp33[32, 0] -= 0.02
    mp33[32, 1] += 0.03

    return mp33


def _midpoint(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """두 점의 중점"""
    return (a + b) / 2.0


def _weighted_avg(a: np.ndarray, b: np.ndarray, w: float) -> np.ndarray:
    """가중 평균 (w: a의 가중치, 1-w: b의 가중치)"""
    return a * w + b * (1.0 - w)


def _offset_from(point: np.ndarray, ref: np.ndarray, scale: float) -> np.ndarray:
    """point에서 ref 방향의 반대로 scale만큼 이동"""
    direction = point - ref
    norm = np.linalg.norm(direction)
    if norm > 1e-6:
        direction = direction / norm
    return point + direction * scale


# ──────────────────────────────────────────────────────
# Pre-VFall 데이터 로드 및 변환
# ──────────────────────────────────────────────────────

# Pre-VFall phase → Sentio 클래스 매핑
PHASE_TO_CLASS = {
    0: 0,  # normal → Normal
    1: 4,  # pre-impact → Pre-impact (신규 클래스!)
    2: 1,  # impact → Fall (기본적으로 Front Fall로 매핑, 시나리오별 세분화)
    3: 0,  # post-impact → Normal (이미 넘어진 후 = 정적 상태)
    4: 0,  # recovery → Normal
}

# Pre-VFall 시나리오 → 낙상 유형 매핑
SCENARIO_FALL_TYPE = {
    "S01": 1,  # Forward_Fall → Front Fall
    "S02": 2,  # Backward_Fall → Back Fall
    "S03": 3,  # Lateral_Fall_Left → Side Fall
    "S04": 3,  # Lateral_Fall_Right → Side Fall
    "S05": 1,  # Syncope → Front Fall (실신 = 전방 쓰러짐)
    "S06": 1,  # Trip_Fall → Front Fall (걸림 = 전방)
    "S07": 2,  # Slip_Fall → Back Fall (미끄러짐 = 후방)
    "S08": 3,  # Chair_Fall → Side Fall (의자 = 측면)
    "S09": 1,  # Sit_to_Fall → Front Fall
    "S10": 3,  # Stagger_Fall → Side Fall (비틀거림)
    "S11": 1,  # Collapse → Front Fall (쓰러짐)
    "S12": 1,  # Mixed_Fall → Front Fall (기본값)
}


def load_prevfall_csv(csv_path: str) -> np.ndarray | None:
    """
    Pre-VFall CSV 파일에서 키포인트 로드

    Args:
        csv_path: CSV 파일 경로

    Returns:
        keypoints: (N_frames, 18, 3) - [x, y, confidence] 또는 None
    """
    frames = []

    try:
        with open(csv_path, "r", encoding="utf-8") as f:
            reader = csv.reader(f)
            for row in reader:
                # 코멘트 행 건너뛰기
                if not row or row[0].startswith("#"):
                    continue

                # 헤더 행 건너뛰기
                try:
                    float(row[0])
                except ValueError:
                    continue

                # frame_id + 18 keypoints * 3 values = 55 columns
                if len(row) < 55:
                    continue

                values = [float(v) for v in row[1:55]]  # frame_id 제외
                frame_kps = np.array(values, dtype=np.float32).reshape(18, 3)
                frames.append(frame_kps)

    except Exception as e:
        print(f"  [ERROR] CSV 로드 실패: {csv_path}: {e}")
        return None

    if not frames:
        return None

    return np.array(frames, dtype=np.float32)  # (N, 18, 3)


def load_prevfall_labels(label_path: str) -> dict[int, int] | None:
    """
    Pre-VFall 라벨 CSV 로드

    Args:
        label_path: 라벨 CSV 파일 경로

    Returns:
        labels: {frame_id: phase} 딕셔너리 또는 None
    """
    labels = {}

    try:
        with open(label_path, "r", encoding="utf-8") as f:
            reader = csv.reader(f)
            for row in reader:
                if not row or row[0].startswith("#"):
                    continue
                try:
                    frame_id = int(row[0])
                    phase = int(row[1])
                    labels[frame_id] = phase
                except (ValueError, IndexError):
                    continue
    except Exception:
        return None

    return labels if labels else None


def detect_scenario(file_path: str) -> str:
    """파일 경로에서 Pre-VFall 시나리오 코드 추출"""
    name = Path(file_path).stem.upper()
    for code in SCENARIO_FALL_TYPE:
        if code in name:
            return code
    return "S12"  # 기본값: Mixed


def convert_prevfall_to_sequences(
    keypoints_18: np.ndarray,
    labels: dict[int, int] | None,
    scenario: str,
    seq_len: int = 30,
    stride: int = 15,
) -> list[tuple[np.ndarray, int]]:
    """
    Pre-VFall 키포인트를 MediaPipe 33점 시퀀스로 변환

    Args:
        keypoints_18: (N_frames, 18, 3) OpenPose 키포인트
        labels: {frame_id: phase} 라벨 (없으면 전체 Normal)
        scenario: 시나리오 코드 (S01~S12)
        seq_len: 시퀀스 길이 (30 프레임)
        stride: 슬라이딩 윈도우 간격

    Returns:
        list of (sequence(30, 99), label)
    """
    n_frames = keypoints_18.shape[0]
    if n_frames < seq_len:
        return []

    # OpenPose → MediaPipe 변환 (전체 프레임)
    mp33_frames = np.zeros((n_frames, 33, 3), dtype=np.float32)
    for i in range(n_frames):
        mp33_frames[i] = openpose18_to_mediapipe33(keypoints_18[i])

    # (N, 33, 3) → (N, 99) 평탄화
    flat = mp33_frames.reshape(n_frames, -1)

    # 시나리오별 낙상 유형
    fall_type = SCENARIO_FALL_TYPE.get(scenario, 1)

    sequences = []

    for start in range(0, n_frames - seq_len + 1, stride):
        end = start + seq_len
        seq = flat[start:end]

        if seq.shape != (seq_len, 99):
            continue

        # 라벨 결정: 윈도우 내 다수결 phase
        if labels:
            phases = []
            for frame_idx in range(start, end):
                phase = labels.get(frame_idx, 0)
                phases.append(phase)

            # 다수결 phase
            phase_counts = {}
            for p in phases:
                phase_counts[p] = phase_counts.get(p, 0) + 1
            majority_phase = max(phase_counts, key=phase_counts.get)

            # Phase → 클래스 변환
            if majority_phase == 1:
                # Pre-impact → 클래스 4
                label = 4
            elif majority_phase == 2:
                # Impact → 시나리오별 낙상 유형
                label = fall_type
            else:
                # Normal / Post-impact / Recovery → 0
                label = 0
        else:
            label = 0

        sequences.append((seq, label))

    return sequences


def process_prevfall_dataset(
    input_dir: str,
    output_path: str,
    seq_len: int = 30,
    stride: int = 15,
):
    """
    Pre-VFall 데이터셋 전체 처리

    Args:
        input_dir: Pre-VFall 데이터 루트 경로
        output_path: 출력 .npz 파일 경로
        seq_len: 시퀀스 길이
        stride: 슬라이딩 윈도우 간격
    """
    input_path = Path(input_dir)
    kp_dir = input_path / "keypoints"
    label_dir = input_path / "labels"

    if not kp_dir.exists():
        print(f"키포인트 디렉토리 없음: {kp_dir}")
        sys.exit(1)

    csv_files = sorted(kp_dir.glob("*.csv"))
    csv_files = [f for f in csv_files if not f.name.startswith("_")]

    if not csv_files:
        print(f"CSV 파일 없음: {kp_dir}")
        sys.exit(1)

    print(f"\nPre-VFall 전처리 시작")
    print(f"  입력: {kp_dir} ({len(csv_files)}개 CSV)")
    print(f"  시퀀스 길이: {seq_len}, 스트라이드: {stride}")

    all_X = []
    all_y = []
    processed = 0
    failed = 0

    for i, csv_file in enumerate(csv_files):
        # 키포인트 로드
        kps = load_prevfall_csv(str(csv_file))
        if kps is None:
            failed += 1
            continue

        # 라벨 로드 (같은 이름의 CSV)
        label_file = label_dir / csv_file.name
        labels = load_prevfall_labels(str(label_file)) if label_file.exists() else None

        # 시나리오 감지
        scenario = detect_scenario(csv_file.name)

        # 시퀀스 변환
        seqs = convert_prevfall_to_sequences(
            kps, labels, scenario, seq_len=seq_len, stride=stride,
        )

        if seqs:
            X = np.array([s[0] for s in seqs], dtype=np.float32)
            y = np.array([s[1] for s in seqs], dtype=np.int64)
            all_X.append(X)
            all_y.append(y)
            processed += 1
        else:
            failed += 1

        if (i + 1) % 10 == 0 or i == len(csv_files) - 1:
            print(f"  [{i+1}/{len(csv_files)}] 처리={processed}, 실패={failed}")

    if not all_X:
        print("변환된 시퀀스가 없습니다.")
        sys.exit(1)

    X = np.concatenate(all_X, axis=0)
    y = np.concatenate(all_y, axis=0)

    class_names = ["normal", "front_fall", "back_fall", "side_fall", "pre_impact"]

    print(f"\n변환 완료:")
    print(f"  총 시퀀스: {len(X)}")
    print(f"  Shape: X={X.shape}, y={y.shape}")
    for cls_id, cls_name in enumerate(class_names):
        count = int(np.sum(y == cls_id))
        if count > 0:
            print(f"  {cls_name} ({cls_id}): {count}")

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    np.savez_compressed(
        output_path, X=X, y=y, class_names=np.array(class_names),
    )
    file_size = os.path.getsize(output_path) / 1024 / 1024
    print(f"\n저장: {output_path} ({file_size:.1f} MB)")


# ──────────────────────────────────────────────────────
# 데이터셋 병합
# ──────────────────────────────────────────────────────

def merge_datasets(
    aihub_path: str,
    prevfall_path: str,
    output_path: str,
    aihub_sample_ratio: float = 1.0,
):
    """
    AI Hub + Pre-VFall 데이터셋을 통합합니다.

    AI Hub: 4클래스 (0=Normal, 1=Front, 2=Back, 3=Side)
    Pre-VFall: 5클래스 (0~3 + 4=Pre-impact)

    통합 후: 5클래스 (Pre-impact 클래스 추가)

    Args:
        aihub_path: AI Hub .npz 경로
        prevfall_path: Pre-VFall .npz 경로
        output_path: 통합 .npz 출력 경로
        aihub_sample_ratio: AI Hub 데이터 사용 비율 (1.0 = 전체)
    """
    print(f"\n{'='*60}")
    print(f"데이터셋 병합")
    print(f"{'='*60}")

    # AI Hub 로드
    print(f"\n1. AI Hub 로드: {aihub_path}")
    aihub = np.load(aihub_path)
    aihub_X = aihub["X"]
    aihub_y = aihub["y"]
    print(f"   Shape: X={aihub_X.shape}, y={aihub_y.shape}")
    for cls_id in range(4):
        count = int(np.sum(aihub_y == cls_id))
        print(f"   class {cls_id}: {count}")

    # 샘플링 (필요 시)
    if aihub_sample_ratio < 1.0:
        rng = np.random.RandomState(42)
        n = int(len(aihub_X) * aihub_sample_ratio)
        indices = rng.choice(len(aihub_X), n, replace=False)
        aihub_X = aihub_X[indices]
        aihub_y = aihub_y[indices]
        print(f"   샘플링 후: {len(aihub_X)}")

    # Pre-VFall 로드
    print(f"\n2. Pre-VFall 로드: {prevfall_path}")
    prevfall = np.load(prevfall_path)
    prevfall_X = prevfall["X"]
    prevfall_y = prevfall["y"]
    print(f"   Shape: X={prevfall_X.shape}, y={prevfall_y.shape}")
    for cls_id in range(5):
        count = int(np.sum(prevfall_y == cls_id))
        if count > 0:
            print(f"   class {cls_id}: {count}")

    # 입력 차원 검증
    if aihub_X.shape[1:] != prevfall_X.shape[1:]:
        print(f"\n  오류: 시퀀스 shape 불일치!")
        print(f"    AI Hub: {aihub_X.shape[1:]}")
        print(f"    Pre-VFall: {prevfall_X.shape[1:]}")
        sys.exit(1)

    # 병합
    print(f"\n3. 병합 중...")
    X = np.concatenate([aihub_X, prevfall_X], axis=0)
    y = np.concatenate([aihub_y, prevfall_y], axis=0)

    # 셔플
    rng = np.random.RandomState(42)
    indices = rng.permutation(len(X))
    X = X[indices]
    y = y[indices]

    class_names = ["normal", "front_fall", "back_fall", "side_fall", "pre_impact"]

    print(f"\n병합 결과:")
    print(f"  총 시퀀스: {len(X)}")
    print(f"  Shape: X={X.shape}, y={y.shape}")
    for cls_id, cls_name in enumerate(class_names):
        count = int(np.sum(y == cls_id))
        pct = count / len(y) * 100 if len(y) > 0 else 0
        print(f"  {cls_name} ({cls_id}): {count} ({pct:.1f}%)")

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    np.savez_compressed(
        output_path, X=X, y=y, class_names=np.array(class_names),
        source_aihub=len(aihub_X), source_prevfall=len(prevfall_X),
    )
    file_size = os.path.getsize(output_path) / 1024 / 1024
    print(f"\n저장: {output_path} ({file_size:.1f} MB)")


def show_stats(npz_path: str):
    """NPZ 데이터 통계 표시"""
    data = np.load(npz_path)
    X = data["X"]
    y = data["y"]
    class_names = list(data.get("class_names", []))

    if not class_names:
        class_names = ["normal", "front_fall", "back_fall", "side_fall", "pre_impact"]

    print(f"\n{'='*60}")
    print(f"데이터 통계: {npz_path}")
    print(f"{'='*60}")
    print(f"  X shape: {X.shape}")
    print(f"  y shape: {y.shape}")
    print(f"  dtype: X={X.dtype}, y={y.dtype}")
    print(f"  파일 크기: {os.path.getsize(npz_path) / 1024 / 1024:.1f} MB")

    print(f"\n  클래스 분포:")
    for cls_id in range(max(int(y.max()) + 1, len(class_names))):
        count = int(np.sum(y == cls_id))
        pct = count / len(y) * 100 if len(y) > 0 else 0
        name = class_names[cls_id] if cls_id < len(class_names) else f"class_{cls_id}"
        bar = "#" * int(pct / 2)
        print(f"    {name:>12} ({cls_id}): {count:>6} ({pct:5.1f}%) {bar}")

    print(f"\n  값 범위:")
    print(f"    X min={X.min():.4f}, max={X.max():.4f}, mean={X.mean():.4f}")

    # 소스 정보 (병합된 데이터인 경우)
    if "source_aihub" in data:
        print(f"\n  소스 구성:")
        print(f"    AI Hub: {int(data['source_aihub'])}")
        print(f"    Pre-VFall: {int(data['source_prevfall'])}")


# ──────────────────────────────────────────────────────
# 메인
# ──────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Sentio 다중 데이터셋 전처리 및 통합"
    )
    parser.add_argument(
        "--source",
        type=str,
        required=True,
        choices=["prevfall", "merge", "stats"],
        help="작업 모드: prevfall(변환), merge(통합), stats(통계)",
    )
    parser.add_argument("--input-dir", type=str, help="Pre-VFall 데이터 루트 경로")
    parser.add_argument("--input-npz", type=str, help="NPZ 파일 경로 (stats용)")
    parser.add_argument("--aihub-npz", type=str, help="AI Hub .npz 경로 (merge용)")
    parser.add_argument("--prevfall-npz", type=str, help="Pre-VFall .npz 경로 (merge용)")
    parser.add_argument("--output", type=str, help="출력 .npz 파일 경로")
    parser.add_argument("--seq-len", type=int, default=30, help="시퀀스 길이")
    parser.add_argument("--stride", type=int, default=15, help="슬라이딩 윈도우 간격")
    parser.add_argument(
        "--aihub-ratio", type=float, default=1.0,
        help="AI Hub 데이터 사용 비율 (0.0~1.0)",
    )
    args = parser.parse_args()

    if args.source == "prevfall":
        if not args.input_dir:
            parser.error("--input-dir 필수 (Pre-VFall 데이터 경로)")
        if not args.output:
            args.output = os.path.join(args.input_dir, "landmarks", "prevfall_landmarks.npz")
        process_prevfall_dataset(
            args.input_dir, args.output,
            seq_len=args.seq_len, stride=args.stride,
        )

    elif args.source == "merge":
        if not args.aihub_npz or not args.prevfall_npz:
            parser.error("--aihub-npz, --prevfall-npz 모두 필수")
        if not args.output:
            parser.error("--output 필수")
        merge_datasets(
            args.aihub_npz, args.prevfall_npz, args.output,
            aihub_sample_ratio=args.aihub_ratio,
        )

    elif args.source == "stats":
        if not args.input_npz:
            parser.error("--input-npz 필수")
        show_stats(args.input_npz)


if __name__ == "__main__":
    main()
