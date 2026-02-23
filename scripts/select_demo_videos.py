"""
AIHub 데이터셋에서 데모 영상 선별 및 복사

다양한 환경(각도, 낙상 유형)의 영상을 데모 폴더로 복사합니다.
"""

import shutil
from pathlib import Path


def select_and_copy_videos():
    """데모용 영상 선별 및 복사"""
    aihub_base = Path("D:/AIHub_Fall_Data/Validation/source/영상")
    demo_dir = Path("C:/Users/dbals/VibeCoding/Care-guard/demo_videos")

    # 선별 기준:
    # - 각 낙상 유형(FY, BY, SY)별 다양한 각도
    # - 정상(N) 영상도 포함 (오탐 테스트용)
    selected_videos = [
        # 전방 낙상 (FY) - 잘 감지됨, 대표 케이스
        ("Y/FY/00100_H_A_FY_C1/00100_H_A_FY_C1.mp4", "FY_hospital_front_C1.mp4"),
        ("Y/FY/00100_H_A_FY_C5/00100_H_A_FY_C5.mp4", "FY_hospital_front_C5.mp4"),

        # 후방 낙상 (BY) - 미탐 위험, 다양한 각도 테스트
        ("Y/BY/00074_H_A_BY_C1/00074_H_A_BY_C1.mp4", "BY_hospital_back_C1.mp4"),
        ("Y/BY/00074_H_A_BY_C3/00074_H_A_BY_C3.mp4", "BY_hospital_back_C3.mp4"),
        ("Y/BY/00074_H_A_BY_C5/00074_H_A_BY_C5.mp4", "BY_hospital_back_C5.mp4"),

        # 측면 낙상 (SY) - 미탐 위험, 다양한 각도
        ("Y/SY/00001_H_A_SY_C1/00001_H_A_SY_C1.mp4", "SY_hospital_side_C1.mp4"),
        ("Y/SY/00001_H_A_SY_C3/00001_H_A_SY_C3.mp4", "SY_hospital_side_C3.mp4"),
        ("Y/SY/00001_H_A_SY_C5/00001_H_A_SY_C5.mp4", "SY_hospital_side_C5.mp4"),

        # 정상 (N) - 오탐 테스트용
        ("N/N/00005_H_A_N_C1/00005_H_A_N_C1.mp4", "N_hospital_normal_C1.mp4"),
        ("N/N/00005_H_A_N_C5/00005_H_A_N_C5.mp4", "N_hospital_normal_C5.mp4"),
    ]

    print(f"데모 영상 복사 시작")
    print(f"원본: {aihub_base}")
    print(f"대상: {demo_dir}")
    print("-" * 50)

    copied_count = 0
    for src_rel, dst_name in selected_videos:
        src_path = aihub_base / src_rel
        dst_path = demo_dir / dst_name

        if not src_path.exists():
            print(f"[SKIP] 없음: {src_path.name}")
            continue

        if dst_path.exists():
            print(f"[SKIP] 이미 존재: {dst_name}")
            continue

        try:
            shutil.copy2(src_path, dst_path)
            print(f"[OK] {dst_name}")
            copied_count += 1
        except Exception as e:
            print(f"[ERROR] {dst_name}: {e}")

    print("-" * 50)
    print(f"복사 완료: {copied_count}개")

    # 현재 데모 폴더 내용 출력
    print(f"\n데모 폴더 내용 ({demo_dir}):")
    for f in sorted(demo_dir.glob("*.mp4")):
        size_mb = f.stat().st_size / (1024 * 1024)
        print(f"  {f.name:40s} {size_mb:.1f}MB")


if __name__ == "__main__":
    select_and_copy_videos()
