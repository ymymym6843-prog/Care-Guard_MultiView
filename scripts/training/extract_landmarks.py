"""
AIHub 낙상 데이터셋 → MediaPipe 포즈 랜드마크 추출

영상에서 33개 포즈 랜드마크(x,y,z)를 추출하여 .npz 파일로 저장합니다.
기존 fall_classifier.py 입력 형식(30, 99)에 맞춰 30fps 시퀀스를 생성합니다.

4클래스 분류 지원:
  0: Normal (비낙상)
  1: Front Fall (FY, 전면 낙상)
  2: Back Fall (BY, 후면 낙상)
  3: Side Fall (SY, 측면 낙상)

데이터 증강:
  --augment 플래그로 제어 (기본 ON)
  - Gaussian jitter (sigma=0.003)
  - Horizontal flip (33 랜드마크 쌍 교환)
  - Scale variation (0.9~1.1)
  - Temporal noise (프레임 드롭/복제)

MediaPipe Tasks API (0.10.20+) 사용.

Usage:
    python scripts/training/extract_landmarks.py \
        --data-root D:/AIHub_Fall_Data \
        --output-dir D:/AIHub_Fall_Data/landmarks \
        --max-per-class 0 \
        --workers 1 \
        --augment
"""

import argparse
import json
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import cv2
import numpy as np

# MediaPipe Tasks API
import mediapipe as mp
from mediapipe.tasks.python import BaseOptions
from mediapipe.tasks.python.vision import (
    PoseLandmarker,
    PoseLandmarkerOptions,
    RunningMode,
)

# 모델 경로 (자동 다운로드)
_MODEL_PATH = "D:/AIHub_Fall_Data/pose_landmarker_lite.task"
_MODEL_URL = "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/latest/pose_landmarker_lite.task"

# 4클래스 라벨 매핑
FALL_TYPE_LABEL = {
    "N": 0,   # Normal
    "FY": 1,  # Front Fall
    "BY": 2,  # Back Fall
    "SY": 3,  # Side Fall
}
CLASS_NAMES = ["normal", "front_fall", "back_fall", "side_fall"]

# MediaPipe 좌우 랜드마크 쌍 (수평 반전 시 교환)
_FLIP_PAIRS = [
    (1, 4), (2, 5), (3, 6),       # eyes
    (7, 8),                         # ears
    (9, 10),                        # mouth
    (11, 12),                       # shoulders
    (13, 14),                       # elbows
    (15, 16),                       # wrists
    (17, 18),                       # pinkies
    (19, 20),                       # index fingers
    (21, 22),                       # thumbs
    (23, 24),                       # hips
    (25, 26),                       # knees
    (27, 28),                       # ankles
    (29, 30),                       # heels
    (31, 32),                       # foot indices
]


def ensure_model():
    """포즈 모델 파일이 없으면 다운로드"""
    if not os.path.exists(_MODEL_PATH):
        print(f"포즈 모델 다운로드 중: {_MODEL_URL}")
        import urllib.request
        os.makedirs(os.path.dirname(_MODEL_PATH), exist_ok=True)
        urllib.request.urlretrieve(_MODEL_URL, _MODEL_PATH)
        print(f"  완료: {os.path.getsize(_MODEL_PATH) / 1024 / 1024:.1f} MB")


def extract_landmarks_from_video(video_path: str, target_fps: int = 30) -> np.ndarray | None:
    """
    영상에서 MediaPipe 33-point 랜드마크를 추출합니다.

    Args:
        video_path: MP4 파일 경로
        target_fps: 추출 대상 FPS (원본 60fps → 30fps로 다운샘플)

    Returns:
        landmarks: (N_frames, 33, 3) numpy array 또는 None
    """
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        return None

    src_fps = cap.get(cv2.CAP_PROP_FPS)
    if src_fps <= 0:
        cap.release()
        return None

    # 프레임 스킵 비율 계산 (60fps → 30fps = 매 2프레임마다)
    skip_ratio = max(1, round(src_fps / target_fps))

    # PoseLandmarker를 VIDEO 모드로 생성
    options = PoseLandmarkerOptions(
        base_options=BaseOptions(model_asset_path=_MODEL_PATH),
        running_mode=RunningMode.VIDEO,
        num_poses=1,
        min_pose_detection_confidence=0.5,
        min_tracking_confidence=0.5,
    )

    landmarks_list = []
    frame_idx = 0

    with PoseLandmarker.create_from_options(options) as landmarker:
        while True:
            if frame_idx % skip_ratio != 0:
                ret = cap.grab()
                if not ret:
                    break
                frame_idx += 1
                continue

            ret, frame = cap.read()
            if not ret:
                break

            # 4K → 640x480 리사이즈 (속도 최적화)
            small = cv2.resize(frame, (640, 480))
            rgb = cv2.cvtColor(small, cv2.COLOR_BGR2RGB)

            mp_image = mp.Image(
                image_format=mp.ImageFormat.SRGB,
                data=rgb,
            )

            # 타임스탬프는 밀리초 단위, 단조 증가 필수
            timestamp_ms = int(frame_idx * 1000 / src_fps)
            result = landmarker.detect_for_video(mp_image, timestamp_ms)

            if result.pose_landmarks and len(result.pose_landmarks) > 0:
                frame_lm = []
                for lm in result.pose_landmarks[0]:
                    frame_lm.append([lm.x, lm.y, lm.z])
                landmarks_list.append(frame_lm)
            else:
                if landmarks_list:
                    landmarks_list.append(landmarks_list[-1])
                else:
                    landmarks_list.append([[0.0, 0.0, 0.0]] * 33)

            frame_idx += 1

    cap.release()

    if not landmarks_list:
        return None

    return np.array(landmarks_list, dtype=np.float32)  # (N, 33, 3)


# ──────────────────────────────────────────────────────
# 데이터 증강 함수
# ──────────────────────────────────────────────────────

def augment_jitter(sequence: np.ndarray, sigma: float = 0.003, rng: np.random.RandomState = None) -> np.ndarray:
    """좌표 가우시안 노이즈 (sigma=0.003)

    Args:
        sequence: (seq_len, 99) 플랫 랜드마크 시퀀스
        sigma: 노이즈 표준편차
        rng: 난수 생성기
    Returns:
        augmented: (seq_len, 99) 노이즈 추가된 시퀀스
    """
    if rng is None:
        rng = np.random.RandomState()
    noise = rng.normal(0, sigma, sequence.shape).astype(np.float32)
    return sequence + noise


def augment_horizontal_flip(sequence: np.ndarray) -> np.ndarray:
    """좌우 반전 (33개 랜드마크 쌍 교환, x좌표 반전)

    Args:
        sequence: (seq_len, 99) 플랫 랜드마크 시퀀스
    Returns:
        flipped: (seq_len, 99) 좌우 반전 시퀀스
    """
    seq_len = sequence.shape[0]
    # (seq_len, 99) → (seq_len, 33, 3)
    lm = sequence.reshape(seq_len, 33, 3).copy()

    # x 좌표 반전 (MediaPipe 좌표계: 0~1, 좌→우)
    lm[:, :, 0] = 1.0 - lm[:, :, 0]

    # 좌우 쌍 교환
    for left, right in _FLIP_PAIRS:
        lm[:, [left, right], :] = lm[:, [right, left], :]

    return lm.reshape(seq_len, -1)


def augment_scale(sequence: np.ndarray, scale_range: tuple = (0.9, 1.1), rng: np.random.RandomState = None) -> np.ndarray:
    """체형 변화 시뮬레이션 (0.9~1.1배 스케일링)

    중심점 기준으로 스케일링하여 위치는 유지하되 체형만 변경합니다.

    Args:
        sequence: (seq_len, 99) 플랫 랜드마크 시퀀스
        scale_range: 스케일 범위 (min, max)
        rng: 난수 생성기
    Returns:
        scaled: (seq_len, 99) 스케일 조정된 시퀀스
    """
    if rng is None:
        rng = np.random.RandomState()
    scale = rng.uniform(scale_range[0], scale_range[1])

    seq_len = sequence.shape[0]
    # (seq_len, 99) → (seq_len, 33, 3)
    lm = sequence.reshape(seq_len, 33, 3).copy()

    # 각 프레임의 중심점 기준 스케일링
    center = lm.mean(axis=1, keepdims=True)  # (seq_len, 1, 3)
    lm = center + (lm - center) * scale

    return lm.reshape(seq_len, -1).astype(np.float32)


def augment_temporal_noise(sequence: np.ndarray, rng: np.random.RandomState = None) -> np.ndarray:
    """프레임 드롭/복제로 시간적 노이즈 추가

    랜덤하게 일부 프레임을 이웃 프레임으로 복제하여
    실제 영상에서의 프레임 드롭 효과를 시뮬레이션합니다.

    Args:
        sequence: (seq_len, 99) 플랫 랜드마크 시퀀스
        rng: 난수 생성기
    Returns:
        noisy: (seq_len, 99) 시간적 노이즈 시퀀스
    """
    if rng is None:
        rng = np.random.RandomState()

    result = sequence.copy()
    seq_len = result.shape[0]

    # 전체 프레임의 ~10% 를 드롭/복제
    n_replace = max(1, seq_len // 10)
    indices = rng.choice(range(1, seq_len), size=min(n_replace, seq_len - 1), replace=False)

    for idx in indices:
        # 이전 프레임을 복제 (프레임 드롭 시뮬레이션)
        result[idx] = result[idx - 1]

    return result


def apply_augmentations(
    sequence: np.ndarray,
    label: int,
    rng: np.random.RandomState,
) -> list[tuple[np.ndarray, int]]:
    """원본 시퀀스에 증강을 적용하여 2~3개의 추가 복사본을 생성합니다.

    Args:
        sequence: (seq_len, 99) 원본 시퀀스
        label: 클래스 라벨
        rng: 난수 생성기
    Returns:
        list of (augmented_sequence, label) 튜플
    """
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
# 시퀀스 생성
# ──────────────────────────────────────────────────────

def create_sequences(
    landmarks: np.ndarray,
    seq_len: int = 30,
    fall_start: int = 0,
    fall_end: int = 0,
    fall_type: str = "N",
    stride: int = 15,
) -> list[tuple[np.ndarray, int]]:
    """
    랜드마크 시퀀스에서 30-프레임 윈도우를 생성합니다.

    Args:
        landmarks: (N_frames, 33, 3)
        seq_len: 윈도우 크기 (30 프레임 = 1초)
        fall_start: 낙상 시작 프레임 (원본 fps 기준 라벨)
        fall_end: 낙상 종료 프레임 (원본 fps 기준 라벨)
        fall_type: 낙상 유형 ("N", "FY", "BY", "SY")
        stride: 슬라이딩 윈도우 간격

    Returns:
        list of (sequence(30, 99), label)
    """
    n_frames = landmarks.shape[0]
    if n_frames < seq_len:
        return []

    # (N, 33, 3) → (N, 99)
    flat = landmarks.reshape(n_frames, -1)

    is_fall = fall_type != "N"
    label = FALL_TYPE_LABEL.get(fall_type, 0)

    sequences = []

    if is_fall and fall_start > 0:
        # 낙상 영상: 낙상 구간 중심으로 시퀀스 추출
        # 60fps 라벨을 30fps로 변환
        fs = fall_start // 2
        fe = fall_end // 2

        # 낙상 포함 윈도우 (해당 fall_type 라벨)
        for start in range(max(0, fs - seq_len), min(fe, n_frames - seq_len), stride):
            end = start + seq_len
            if end <= n_frames:
                seq = flat[start:end]
                # 윈도우가 낙상 구간과 겹치면 해당 fall_type 라벨
                overlap = max(0, min(end, fe) - max(start, fs))
                seq_label = label if overlap > seq_len // 3 else 0
                sequences.append((seq, seq_label))

        # 낙상 전 정상 구간 (label=0)
        if fs > seq_len:
            for start in range(0, fs - seq_len, stride * 2):
                end = start + seq_len
                sequences.append((flat[start:end], 0))
    else:
        # 비낙상 영상: 전체에서 균일 샘플링 (label=0)
        for start in range(0, n_frames - seq_len, stride):
            end = start + seq_len
            sequences.append((flat[start:end], 0))

    return sequences


def process_single_video(args: tuple) -> dict | None:
    """단일 영상 처리"""
    video_path, label_path, fall_type, scene_id = args

    try:
        # 라벨 로드
        fall_start = 0
        fall_end = 0
        if label_path and os.path.exists(label_path):
            with open(label_path, "r", encoding="utf-8") as f:
                label_data = json.load(f)
            fall_start = label_data.get("sensordata", {}).get("fall_start_frame", 0)
            fall_end = label_data.get("sensordata", {}).get("fall_end_frame", 0)

        # 랜드마크 추출
        landmarks = extract_landmarks_from_video(video_path, target_fps=30)
        if landmarks is None or len(landmarks) < 30:
            return None

        # 시퀀스 생성
        seqs = create_sequences(
            landmarks,
            seq_len=30,
            fall_start=fall_start,
            fall_end=fall_end,
            fall_type=fall_type,
            stride=15,
        )

        if not seqs:
            return None

        # Shape 검증: 모든 시퀀스가 (30, 99) 인지 확인
        valid_seqs = [(s, l) for s, l in seqs if s.shape == (30, 99)]
        if not valid_seqs:
            return None

        X = np.array([s[0] for s in valid_seqs], dtype=np.float32)
        y = np.array([s[1] for s in valid_seqs], dtype=np.int64)

        return {"scene_id": scene_id, "X": X, "y": y}

    except Exception as e:
        print(f"  [ERROR] {scene_id}: {e}", flush=True)
        return None


def scan_dataset(data_root: str, split: str = "Training") -> list[dict]:
    """데이터셋 스캔하여 영상/라벨 경로 목록 생성"""
    base = Path(data_root) / split
    video_base = base / "source" / "영상"
    label_base = base / "label" / "영상"

    entries = []

    # 낙상 유형: FY(전면), BY(후면), SY(측면)
    for fall_type in ["FY", "BY", "SY"]:
        vdir = video_base / "Y" / fall_type
        ldir = label_base / "Y" / fall_type
        if not vdir.exists():
            continue
        for scene_dir in sorted(vdir.iterdir()):
            if not scene_dir.is_dir():
                continue
            scene_id = scene_dir.name
            mp4_files = list(scene_dir.glob("*.mp4"))
            if not mp4_files:
                continue
            video_path = str(mp4_files[0])
            label_path = str(ldir / scene_id / f"{scene_id}.json")
            entries.append({
                "video_path": video_path,
                "label_path": label_path,
                "fall_type": fall_type,
                "scene_id": scene_id,
            })

    # 비낙상
    ndir = video_base / "N" / "N"
    nldir = label_base / "N" / "N"
    if ndir.exists():
        for scene_dir in sorted(ndir.iterdir()):
            if not scene_dir.is_dir():
                continue
            scene_id = scene_dir.name
            mp4_files = list(scene_dir.glob("*.mp4"))
            if not mp4_files:
                continue
            video_path = str(mp4_files[0])
            label_path = str(nldir / scene_id / f"{scene_id}.json")
            entries.append({
                "video_path": video_path,
                "label_path": label_path,
                "fall_type": "N",
                "scene_id": scene_id,
            })

    return entries


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


def main():
    parser = argparse.ArgumentParser(description="AIHub 낙상 데이터셋 랜드마크 추출 (4클래스)")
    parser.add_argument("--data-root", type=str, default="D:/AIHub_Fall_Data")
    parser.add_argument("--output-dir", type=str, default="D:/AIHub_Fall_Data/landmarks")
    parser.add_argument("--split", type=str, default="Training")
    parser.add_argument("--max-per-class", type=int, default=0,
                        help="클래스당 최대 영상 수 (0=전체)")
    parser.add_argument("--workers", type=int, default=4,
                        help="병렬 처리 워커 수 (기본: 4, ProcessPoolExecutor 기반)")
    parser.add_argument("--seq-len", type=int, default=30)
    parser.add_argument("--chunk-size", type=int, default=100,
                        help="청크당 영상 수 (메모리 관리용, 0=전체 한번에)")
    parser.add_argument("--augment", action="store_true", default=True,
                        help="데이터 증강 활성화 (기본: ON)")
    parser.add_argument("--no-augment", action="store_true",
                        help="데이터 증강 비활성화")
    parser.add_argument("--resume", action="store_true", default=False,
                        help="이전 실행에서 중단된 지점부터 재개 (완료된 청크 건너뜀)")
    args = parser.parse_args()

    if args.no_augment:
        args.augment = False

    os.makedirs(args.output_dir, exist_ok=True)

    # 모델 다운로드 확인
    ensure_model()

    print(f"데이터셋 스캔 중: {args.data_root}/{args.split}")
    entries = scan_dataset(args.data_root, args.split)
    print(f"  총 영상: {len(entries)}")

    # 클래스별 카운트
    by_type = {}
    for e in entries:
        ft = e["fall_type"]
        by_type.setdefault(ft, []).append(e)

    for ft, items in by_type.items():
        label_id = FALL_TYPE_LABEL[ft]
        print(f"  {ft} (label={label_id}): {len(items)}")

    # 클래스당 샘플링
    sampled = []
    for ft, items in by_type.items():
        if args.max_per_class > 0 and len(items) > args.max_per_class:
            np.random.seed(42)
            indices = np.random.choice(len(items), args.max_per_class, replace=False)
            items = [items[i] for i in indices]
        sampled.extend(items)

    # 클래스 균형 셔플 (모든 청크에 4클래스 골고루 분배)
    np.random.seed(42)
    np.random.shuffle(sampled)

    print(f"\n샘플링 후 총 영상: {len(sampled)} (셔플 완료)")
    print(f"증강: {'ON (원본당 2~3개 복사본)' if args.augment else 'OFF'}")

    # 작업 목록 생성
    tasks = [
        (e["video_path"], e["label_path"], e["fall_type"], e["scene_id"])
        for e in sampled
    ]

    # 청크 처리
    chunk_size = args.chunk_size if args.chunk_size > 0 else len(tasks)
    chunks = [tasks[i:i + chunk_size] for i in range(0, len(tasks), chunk_size)]

    # 청크별 저장 디렉토리
    chunk_dir = os.path.join(args.output_dir, "chunks")
    os.makedirs(chunk_dir, exist_ok=True)

    processed = 0
    failed = 0
    skipped_chunks = 0
    start_time = time.time()
    rng = np.random.RandomState(42)

    n_workers = min(args.workers, os.cpu_count() or 4)
    print(f"\n랜드마크 추출 시작... ({len(chunks)} 청크, 청크당 {chunk_size}, 워커 {n_workers}개)")
    if args.resume:
        print("  재개 모드: 완료된 청크를 건너뜁니다.")

    for chunk_idx, chunk in enumerate(chunks):
        chunk_path = os.path.join(chunk_dir, f"chunk_{chunk_idx:04d}.npz")

        # 재개 모드: 이미 저장된 청크는 건너뜀
        if args.resume and os.path.exists(chunk_path):
            try:
                saved = np.load(chunk_path)
                processed += int(saved.get("processed", 0))
                failed += int(saved.get("failed", 0))
                skipped_chunks += 1
                # rng 상태를 동기화 (일관된 증강 결과를 위해)
                for _ in range(len(chunk)):
                    rng.random()  # advance rng state
                continue
            except Exception:
                pass  # 손상된 청크는 재처리

        print(f"\n--- 청크 {chunk_idx + 1}/{len(chunks)} ({len(chunk)} 영상, 워커 {n_workers}) ---")

        chunk_X = []
        chunk_y = []
        chunk_processed = 0
        chunk_failed = 0

        # 멀티프로세싱으로 영상 병렬 처리
        results_map = {}  # index -> result (순서 보존용)
        with ProcessPoolExecutor(max_workers=n_workers) as executor:
            future_to_idx = {
                executor.submit(process_single_video, task): i
                for i, task in enumerate(chunk)
            }
            done_count = 0
            for future in as_completed(future_to_idx):
                idx = future_to_idx[future]
                done_count += 1
                try:
                    result = future.result()
                except Exception:
                    result = None
                results_map[idx] = result

                # 진행률 표시
                global_idx = chunk_idx * chunk_size + done_count - 1
                if done_count % 10 == 0 or done_count == len(chunk):
                    elapsed = time.time() - start_time
                    total_done = chunk_idx * chunk_size + done_count
                    # 건너뛴 청크의 영상 수도 포함
                    total_done += skipped_chunks * chunk_size
                    speed = total_done / elapsed if elapsed > 0 else 0
                    remaining = (len(tasks) - total_done) / speed if speed > 0 else 0
                    pct = min(total_done / len(tasks) * 100, 100)
                    print(
                        f"  [{total_done}/{len(tasks)}] {pct:.1f}% | "
                        f"처리={processed + chunk_processed + done_count}, 실패={failed + chunk_failed} | "
                        f"속도={speed:.1f}/s, ETA={format_eta(remaining)}",
                        flush=True,
                    )

        # 순서대로 결과 처리 (증강 rng 일관성 보장)
        for i in range(len(chunk)):
            result = results_map.get(i)
            if result:
                chunk_X.append(result["X"])
                chunk_y.append(result["y"])

                if args.augment:
                    for seq, lbl in zip(result["X"], result["y"]):
                        aug_pairs = apply_augmentations(seq, lbl, rng)
                        if aug_pairs:
                            aug_X = np.array([a[0] for a in aug_pairs], dtype=np.float32)
                            aug_y = np.array([a[1] for a in aug_pairs], dtype=np.int64)
                            chunk_X.append(aug_X)
                            chunk_y.append(aug_y)

                chunk_processed += 1
            else:
                chunk_failed += 1

        # 청크 저장 (즉시 디스크에 기록)
        if chunk_X:
            cX = np.concatenate(chunk_X, axis=0)
            cy = np.concatenate(chunk_y, axis=0)
            np.savez_compressed(
                chunk_path, X=cX, y=cy,
                processed=np.array(chunk_processed),
                failed=np.array(chunk_failed),
            )
            print(f"  ✓ 청크 저장: {chunk_path} ({cX.shape[0]} 시퀀스, {os.path.getsize(chunk_path) / 1024:.0f} KB)")
        else:
            # 빈 청크도 기록 (재개 시 건너뛰기 위해)
            np.savez_compressed(
                chunk_path, X=np.empty((0, 30, 99), dtype=np.float32),
                y=np.empty(0, dtype=np.int64),
                processed=np.array(chunk_processed),
                failed=np.array(chunk_failed),
            )

        processed += chunk_processed
        failed += chunk_failed

    if args.resume and skipped_chunks > 0:
        print(f"\n재개: {skipped_chunks}개 청크 건너뜀 (이전 실행에서 완료)")

    # ── 모든 청크 병합 ──
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
    for cls_id, cls_name in enumerate(CLASS_NAMES):
        count = int(np.sum(y == cls_id))
        print(f"  {cls_name} ({cls_id}): {count}")
    print(f"  Shape: X={X.shape}, y={y.shape}")

    # 최종 통합 파일 저장
    out_path = os.path.join(args.output_dir, f"{args.split.lower()}_landmarks.npz")
    np.savez_compressed(
        out_path,
        X=X,
        y=y,
        class_names=np.array(CLASS_NAMES),
    )
    print(f"\n저장: {out_path} ({os.path.getsize(out_path) / 1024 / 1024:.1f} MB)")


if __name__ == "__main__":
    main()
