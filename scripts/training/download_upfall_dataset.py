"""
UP-Fall 3D Skeleton Dataset 다운로드 및 변환 스크립트

- 소스: https://zenodo.org/records/12773013
- 형식: MediaPipe 33-point 3D skeleton CSV
- 활동: A1-A5 (낙상), A6-A11 (정상 일상활동)
- A5 = 측면 낙상 (sideways fall) → SY 클래스 보강용

사용법:
    python scripts/training/download_upfall_dataset.py --output D:/UP_Fall_Data
    python scripts/training/download_upfall_dataset.py --output D:/UP_Fall_Data --skip-download
"""

import os
import sys
import zipfile
import argparse
import csv
from pathlib import Path

import numpy as np

# ============================================================
# 1. 데이터셋 다운로드
# ============================================================
ZENODO_BASE = "https://zenodo.org/records/12773013/files"
SUBJECTS = ["SUBJECT1.zip", "SUBJECT2.zip", "SUBJECT3.zip", "SUBJECT4.zip", "SUBJECT5.zip"]

# UP-Fall 활동 → 낙상 클래스 매핑
# A1: Forward fall (hands) → front_fall (1)
# A2: Forward fall (knees) → front_fall (1)
# A3: Backward fall        → back_fall (2)
# A4: Fall sitting on chair → front_fall (1) (의자에서 미끄러짐)
# A5: Sideways fall         → side_fall (3)
# A6-A11: ADL              → normal (0)
ACTIVITY_TO_CLASS = {
    1: 1,   # A1: forward fall (hands) → front_fall
    2: 1,   # A2: forward fall (knees) → front_fall
    3: 2,   # A3: backward fall → back_fall
    4: 1,   # A4: fall sitting → front_fall
    5: 3,   # A5: sideways fall → side_fall
    6: 0,   # A6: walking → normal
    7: 0,   # A7: standing → normal
    8: 0,   # A8: sitting → normal
    9: 0,   # A9: picking up → normal
    10: 0,  # A10: jumping → normal
    11: 0,  # A11: laying → normal
}

CLASS_NAMES = ['normal', 'front_fall', 'back_fall', 'side_fall']


def download_dataset(output_dir: Path):
    """Zenodo에서 UP-Fall 데이터셋 다운로드"""
    import urllib.request

    output_dir.mkdir(parents=True, exist_ok=True)
    zip_dir = output_dir / "zips"
    zip_dir.mkdir(exist_ok=True)

    for filename in SUBJECTS:
        zip_path = zip_dir / filename
        if zip_path.exists():
            print(f"  [건너뜀] {filename} (이미 존재)")
            continue

        url = f"{ZENODO_BASE}/{filename}?download=1"
        print(f"  다운로드 중: {filename} ...")
        try:
            urllib.request.urlretrieve(url, zip_path)
            print(f"  완료: {filename} ({zip_path.stat().st_size / 1024:.1f} KB)")
        except Exception as e:
            print(f"  실패: {filename} - {e}")
            if zip_path.exists():
                zip_path.unlink()

    # 압축 해제
    csv_dir = output_dir / "csv"
    csv_dir.mkdir(exist_ok=True)

    for filename in SUBJECTS:
        zip_path = zip_dir / filename
        if not zip_path.exists():
            print(f"  [건너뜀] {filename} (다운로드 안 됨)")
            continue

        subject_name = filename.replace(".zip", "")
        subject_dir = csv_dir / subject_name
        if subject_dir.exists() and any(subject_dir.glob("*.csv")):
            print(f"  [건너뜀] {subject_name} (이미 해제됨)")
            continue

        print(f"  압축 해제 중: {filename} ...")
        with zipfile.ZipFile(zip_path, 'r') as zf:
            zf.extractall(csv_dir)
        print(f"  완료: {subject_name}")


def parse_csv_file(csv_path: Path) -> tuple[np.ndarray, int]:
    """
    UP-Fall CSV 파일을 파싱하여 랜드마크 시퀀스 반환

    Returns:
        landmarks: (N_frames, 33, 3) - x, y, z 좌표
        activity: int - 활동 번호
    """
    # 파일명에서 활동 번호 파싱: C{cam}S{sub}A{act}T{trial}.csv
    name = csv_path.stem  # e.g. "C1S1A5T1"
    activity = None
    for part in name.split("A"):
        if len(part) > 0 and part[0].isdigit():
            # A 다음에 오는 숫자 (T 전까지)
            act_str = ""
            for ch in part:
                if ch.isdigit():
                    act_str += ch
                else:
                    break
            if act_str:
                activity = int(act_str)
                break

    if activity is None:
        raise ValueError(f"활동 번호를 파싱할 수 없음: {csv_path.name}")

    frames = []
    with open(csv_path, 'r', newline='') as f:
        reader = csv.reader(f)
        header = next(reader, None)

        if header is None:
            return np.array([]), activity

        # 컬럼 구조 파악: joint_0_x, joint_0_y, joint_0_z, ..., joint_32_x, joint_32_y, joint_32_z, ...
        # 또는 다른 형식일 수 있음
        # 33개 joint × 3 좌표 = 99 값 + 가시성 33개 + 프레임번호/라벨 등

        for row in reader:
            if len(row) < 99:
                continue

            try:
                values = [float(v) for v in row if v.strip()]
            except (ValueError, TypeError):
                continue

            # 첫 99개 값이 33 joints × 3 coords (x, y, z)라고 가정
            # 가시성과 라벨은 이후 컬럼
            if len(values) >= 99:
                coords = values[:99]
                frame_landmarks = np.array(coords).reshape(33, 3)
                frames.append(frame_landmarks)

    if len(frames) == 0:
        return np.array([]), activity

    return np.array(frames), activity


def create_sequences(frames: np.ndarray, seq_len: int = 30, stride: int = 15) -> np.ndarray:
    """
    프레임을 30-프레임 시퀀스로 슬라이딩 윈도우 분할

    Args:
        frames: (N_frames, 33, 3)
        seq_len: 시퀀스 길이 (30)
        stride: 슬라이딩 스트라이드 (15 = 50% 오버랩)

    Returns:
        sequences: (N_seqs, 30, 99) - flatten된 시퀀스
    """
    if len(frames) < seq_len:
        return np.array([])

    sequences = []
    for start in range(0, len(frames) - seq_len + 1, stride):
        seq = frames[start:start + seq_len]  # (30, 33, 3)
        seq_flat = seq.reshape(seq_len, -1)  # (30, 99)
        sequences.append(seq_flat)

    return np.array(sequences)


def augment_sequence(seq: np.ndarray) -> list[np.ndarray]:
    """
    시퀀스 데이터 증강 (측면 낙상 보강용)

    Args:
        seq: (30, 99) - 단일 시퀀스

    Returns:
        list of augmented sequences
    """
    augmented = []

    # 1. 좌우 반전 (x 좌표 반전)
    flipped = seq.copy()
    for i in range(33):
        flipped[:, i * 3] = 1.0 - flipped[:, i * 3]  # x 좌표 반전
    augmented.append(flipped)

    # 2. 시간 역전 (프레임 순서 반전)
    time_reversed = seq[::-1].copy()
    augmented.append(time_reversed)

    # 3. 노이즈 추가 (가우시안)
    noisy = seq.copy() + np.random.normal(0, 0.005, seq.shape).astype(np.float32)
    augmented.append(noisy)

    # 4. 속도 변화 (약간 빠르게 - 프레임 간격 줄이기)
    if len(seq) >= 30:
        # 40프레임에서 30프레임 선택 (빠르게)
        indices = np.linspace(0, len(seq) - 1, 30, dtype=int)
        speed_up = seq[indices]
        augmented.append(speed_up)

    return augmented


def convert_upfall_to_training_data(
    csv_dir: Path,
    output_path: Path,
    seq_len: int = 30,
    stride: int = 15,
    augment_falls: bool = True,
):
    """
    UP-Fall CSV 파일들을 학습 데이터로 변환

    Args:
        csv_dir: CSV 파일들이 있는 디렉토리
        output_path: 출력 NPZ 파일 경로
        seq_len: 시퀀스 길이
        stride: 슬라이딩 윈도우 스트라이드
        augment_falls: 낙상 시퀀스 증강 여부
    """
    all_X = []
    all_y = []
    stats = {cls: 0 for cls in range(4)}

    csv_files = list(csv_dir.rglob("*.csv"))
    print(f"\n  CSV 파일 수: {len(csv_files)}")

    for csv_path in sorted(csv_files):
        try:
            frames, activity = parse_csv_file(csv_path)
        except (ValueError, Exception) as e:
            print(f"  [건너뜀] {csv_path.name}: {e}")
            continue

        if len(frames) == 0:
            print(f"  [건너뜀] {csv_path.name}: 프레임 없음")
            continue

        if activity not in ACTIVITY_TO_CLASS:
            print(f"  [건너뜀] {csv_path.name}: 알 수 없는 활동 A{activity}")
            continue

        class_id = ACTIVITY_TO_CLASS[activity]
        sequences = create_sequences(frames, seq_len, stride)

        if len(sequences) == 0:
            print(f"  [건너뜀] {csv_path.name}: 시퀀스 부족 ({len(frames)} 프레임 < {seq_len})")
            continue

        all_X.append(sequences)
        all_y.extend([class_id] * len(sequences))
        stats[class_id] += len(sequences)

        # 낙상 시퀀스 증강 (특히 SY)
        if augment_falls and class_id > 0:
            for seq in sequences:
                aug_seqs = augment_sequence(seq)
                for aug in aug_seqs:
                    if aug.shape == (seq_len, 99):
                        all_X.append(aug.reshape(1, seq_len, 99))
                        all_y.append(class_id)
                        stats[class_id] += 1

        print(f"  {csv_path.name}: A{activity} → {CLASS_NAMES[class_id]}, {len(sequences)} seqs, {len(frames)} frames")

    if not all_X:
        print("\n  [오류] 변환된 데이터 없음!")
        return

    X = np.concatenate(all_X, axis=0).astype(np.float32)
    y = np.array(all_y, dtype=np.int64)

    print(f"\n📊 UP-Fall 변환 결과:")
    print(f"  X shape: {X.shape}")
    print(f"  y shape: {y.shape}")
    for cls in range(4):
        print(f"  {CLASS_NAMES[cls]}: {stats[cls]:,}")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        output_path,
        X=X,
        y=y,
        class_names=np.array(CLASS_NAMES),
    )
    print(f"\n  저장 완료: {output_path} ({output_path.stat().st_size / 1024 / 1024:.1f} MB)")


def main():
    parser = argparse.ArgumentParser(description="UP-Fall 3D Skeleton 데이터셋 다운로드 및 변환")
    parser.add_argument("--output", type=str, default="D:/UP_Fall_Data",
                        help="출력 디렉토리")
    parser.add_argument("--skip-download", action="store_true",
                        help="다운로드 건너뜀 (이미 다운로드된 경우)")
    parser.add_argument("--seq-len", type=int, default=30,
                        help="시퀀스 길이 (기본: 30)")
    parser.add_argument("--stride", type=int, default=15,
                        help="슬라이딩 윈도우 스트라이드 (기본: 15)")
    parser.add_argument("--no-augment", action="store_true",
                        help="데이터 증강 비활성화")
    args = parser.parse_args()

    output_dir = Path(args.output)

    # Step 1: 다운로드
    if not args.skip_download:
        print("=" * 60)
        print("Step 1: UP-Fall 데이터셋 다운로드")
        print("=" * 60)
        download_dataset(output_dir)
    else:
        print("[건너뜀] 다운로드 스킵")

    # Step 2: CSV → NPZ 변환
    print("\n" + "=" * 60)
    print("Step 2: CSV → 학습 데이터 변환")
    print("=" * 60)

    csv_dir = output_dir / "csv"
    if not csv_dir.exists():
        print(f"[오류] CSV 디렉토리 없음: {csv_dir}")
        return

    npz_path = output_dir / "upfall_landmarks.npz"
    convert_upfall_to_training_data(
        csv_dir,
        npz_path,
        seq_len=args.seq_len,
        stride=args.stride,
        augment_falls=not args.no_augment,
    )

    print("\n" + "=" * 60)
    print("완료! 다음 단계:")
    print(f"  python scripts/training/retrain_gru_enhanced.py \\")
    print(f"    --aihub D:/AIHub_Fall_Data/landmarks/training_landmarks.npz \\")
    print(f"    --upfall {npz_path}")
    print("=" * 60)


if __name__ == "__main__":
    main()
