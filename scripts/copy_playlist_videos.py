"""
AIHub 데이터셋에서 플레이리스트용 영상을 선별하여 demo_videos/에 복사하는 스크립트.

각 카메라별로 다양한 사람/각도의 영상을 선별합니다.
- 다양한 person ID (다른 사람)
- 병원 세팅 (H = Hospital)
- 다양한 카메라 각도 (C1~C8)
"""

import shutil
from pathlib import Path

DATASET_BASE = Path(r"D:\AIHub_Fall_Data\Training\source\영상")
DEMO_DIR = Path(r"C:\Users\dbals\VibeCoding\Care-guard\demo_videos")

# 선별 기준: 다양한 사람(ID) + 다양한 카메라 각도(C1~C8)
# 형식: (카테고리경로, 디렉토리명)
SELECTED_VIDEOS = [
    # === 정상 영상 (Normal) - 8개 추가 ===
    ("N/N", "00002_H_A_N_C3"),   # person 2, 각도 C3
    ("N/N", "00006_H_A_N_C1"),   # person 6, 각도 C1
    ("N/N", "00006_H_A_N_C5"),   # person 6, 각도 C5
    ("N/N", "00009_H_A_N_C2"),   # person 9, 각도 C2
    ("N/N", "00009_H_A_N_C7"),   # person 9, 각도 C7
    ("N/N", "00010_H_A_N_C1"),   # person 10, 각도 C1
    ("N/N", "00010_H_A_N_C4"),   # person 10, 각도 C4
    ("N/N", "00010_H_A_N_C8"),   # person 10, 각도 C8

    # === 후방 낙상 (BY) - 3개 추가 ===
    ("Y/BY", "00080_H_A_BY_C1"),  # person 80, 각도 C1
    ("Y/BY", "00080_H_A_BY_C5"),  # person 80, 각도 C5
    ("Y/BY", "00087_H_A_BY_C3"),  # person 87, 각도 C3

    # === 전방 낙상 (FY) - 3개 추가 ===
    ("Y/FY", "00007_H_A_FY_C3"),  # person 7, 각도 C3
    ("Y/FY", "00014_H_A_FY_C1"),  # person 14, 각도 C1
    ("Y/FY", "00021_H_A_FY_C5"),  # person 21, 각도 C5

    # === 측면 낙상 (SY) - 2개 추가 ===
    ("Y/SY", "00004_H_A_SY_C1"),  # person 4, 각도 C1
    ("Y/SY", "00008_H_A_SY_C5"),  # person 8, 각도 C5
]


def main():
    copied = 0
    skipped = 0
    errors = 0

    for cat_path, dir_name in SELECTED_VIDEOS:
        src_dir = DATASET_BASE / cat_path / dir_name
        src_file = src_dir / f"{dir_name}.mp4"

        if not src_file.exists():
            print(f"[ERROR] 파일 없음: {src_file}")
            errors += 1
            continue

        dst_file = DEMO_DIR / f"{dir_name}.mp4"
        if dst_file.exists():
            print(f"[SKIP] 이미 존재: {dst_file.name}")
            skipped += 1
            continue

        shutil.copy2(src_file, dst_file)
        size_mb = dst_file.stat().st_size / (1024 * 1024)
        print(f"[COPY] {dir_name}.mp4 ({size_mb:.1f} MB)")
        copied += 1

    print(f"\n완료: {copied}개 복사, {skipped}개 건너뜀, {errors}개 에러")
    print(f"demo_videos/ 총 파일 수: {len(list(DEMO_DIR.glob('*.mp4')))}개")


if __name__ == "__main__":
    main()
