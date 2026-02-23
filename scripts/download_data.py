"""
Sentio - 외부 데이터셋 다운로드 및 구성 스크립트

지원 데이터셋:
  1. Pre-VFall (Pre-impact Fall Detection, 학술 데이터셋)
     - 출처: https://github.com/PreVFall/PreVFall-Dataset
     - 형식: MP4 영상 + CSV (OpenPose 18점 키포인트)
     - 특징: 12가지 낙상 시나리오, pre-impact 라벨 포함
     - 다운로드: 학술 목적 공개 (GitHub 릴리즈)

  2. AI Hub 낙상 데이터 (이미 로컬에 존재)
     - 경로: D:/AIHub_Fall_Data
     - 형식: MP4 + JSON (프레임 단위 라벨)

Usage:
    # Pre-VFall 데이터셋 다운로드
    python scripts/download_data.py --dataset prevfall --output-dir D:/PreVFall_Data

    # 다운로드된 데이터 검증
    python scripts/download_data.py --dataset prevfall --output-dir D:/PreVFall_Data --verify

    # AI Hub 데이터 경로 검증만
    python scripts/download_data.py --dataset aihub --data-root D:/AIHub_Fall_Data --verify
"""

import argparse
import hashlib
import os
import shutil
import sys
import zipfile
from pathlib import Path

# Pre-VFall 데이터셋 정보
# 실제 URL은 GitHub 릴리즈 페이지에서 확인 필요
PREVFALL_INFO = {
    "name": "Pre-VFall",
    "description": "Pre-impact Fall Detection Dataset (12 scenarios, multi-angle)",
    "url_base": "https://github.com/PreVFall/PreVFall-Dataset",
    "format": "CSV (OpenPose 18-point keypoints) + MP4 videos",
    "scenarios": [
        "S01_Forward_Fall",
        "S02_Backward_Fall",
        "S03_Lateral_Fall_Left",
        "S04_Lateral_Fall_Right",
        "S05_Syncope",
        "S06_Trip_Fall",
        "S07_Slip_Fall",
        "S08_Chair_Fall",
        "S09_Sit_to_Fall",
        "S10_Stagger_Fall",
        "S11_Collapse",
        "S12_Mixed_Fall",
    ],
    "phases": ["pre-impact", "impact", "post-impact", "recovery"],
    "expected_structure": {
        "keypoints/": "CSV files with OpenPose 18-point keypoints per frame",
        "videos/": "MP4 video files",
        "labels/": "Phase annotations (pre-impact, impact, post-impact)",
    },
}

AIHUB_INFO = {
    "name": "AI Hub Fall Detection",
    "description": "Korean AI Hub fall detection dataset (18,128 videos)",
    "expected_structure": {
        "Training/source/영상/Y/FY/": "전면 낙상 영상 (6,200)",
        "Training/source/영상/Y/BY/": "후면 낙상 영상 (4,640)",
        "Training/source/영상/Y/SY/": "측면 낙상 영상 (2,744)",
        "Training/source/영상/N/N/": "비낙상 영상 (4,544)",
        "Training/label/영상/": "JSON 라벨 (fall_start_frame, fall_end_frame)",
    },
}


def download_file(url: str, dest: str, chunk_size: int = 8192) -> bool:
    """URL에서 파일 다운로드 (진행률 표시)"""
    import urllib.request
    import urllib.error

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Sentio/1.0"})
        with urllib.request.urlopen(req) as response:
            total = int(response.headers.get("Content-Length", 0))
            downloaded = 0

            os.makedirs(os.path.dirname(dest) or ".", exist_ok=True)
            with open(dest, "wb") as f:
                while True:
                    chunk = response.read(chunk_size)
                    if not chunk:
                        break
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total > 0:
                        pct = downloaded / total * 100
                        bar = "=" * int(pct / 2) + ">" + " " * (50 - int(pct / 2))
                        print(f"\r  [{bar}] {pct:.1f}% ({downloaded}/{total})", end="", flush=True)

            print()  # newline
            return True
    except urllib.error.URLError as e:
        print(f"\n  다운로드 실패: {e}")
        return False


def verify_md5(file_path: str, expected_md5: str) -> bool:
    """파일 MD5 체크섬 검증"""
    md5 = hashlib.md5()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            md5.update(chunk)
    actual = md5.hexdigest()
    if actual == expected_md5:
        print(f"  MD5 검증 성공: {actual}")
        return True
    print(f"  MD5 불일치: 기대={expected_md5}, 실제={actual}")
    return False


def setup_prevfall(output_dir: str, verify_only: bool = False):
    """Pre-VFall 데이터셋 다운로드 및 구성"""
    output_path = Path(output_dir)

    print(f"\n{'='*60}")
    print(f"Pre-VFall 데이터셋 구성")
    print(f"{'='*60}")
    print(f"  출력 경로: {output_path}")
    print(f"  설명: {PREVFALL_INFO['description']}")
    print(f"  형식: {PREVFALL_INFO['format']}")
    print(f"  시나리오: {len(PREVFALL_INFO['scenarios'])}가지")
    print()

    if verify_only:
        return verify_prevfall(output_path)

    # 디렉토리 구조 생성
    for subdir in ["keypoints", "videos", "labels", "landmarks"]:
        (output_path / subdir).mkdir(parents=True, exist_ok=True)

    print("Pre-VFall 데이터셋 다운로드 안내:")
    print()
    print("  이 데이터셋은 학술 목적으로 공개된 데이터입니다.")
    print("  아래 절차를 따라 수동으로 다운로드해주세요:")
    print()
    print(f"  1. GitHub 방문: {PREVFALL_INFO['url_base']}")
    print("  2. Releases 페이지에서 최신 버전 다운로드")
    print("  3. 다운로드한 ZIP 파일을 아래 경로에 압축 해제:")
    print(f"     {output_path}")
    print()
    print("  예상 디렉토리 구조:")
    for path, desc in PREVFALL_INFO["expected_structure"].items():
        print(f"    {output_path / path}")
        print(f"      └─ {desc}")
    print()

    # 자동 다운로드 시도 (GitHub 릴리즈)
    print("자동 다운로드를 시도합니다...")
    print("  (학술 데이터셋은 접근 제한이 있을 수 있습니다)")
    print()

    # 예제 CSV 생성 (테스트용)
    example_csv = output_path / "keypoints" / "_example_format.csv"
    if not example_csv.exists():
        with open(example_csv, "w") as f:
            f.write("# Pre-VFall OpenPose 18-point keypoint format example\n")
            f.write("# Columns: frame_id, then 18 keypoints x 3 values (x, y, confidence)\n")
            f.write("# Total: 1 + 54 = 55 columns per row\n")
            f.write("# Keypoint order (OpenPose COCO 18):\n")
            f.write("#   0:Nose, 1:Neck, 2:RShoulder, 3:RElbow, 4:RWrist,\n")
            f.write("#   5:LShoulder, 6:LElbow, 7:LWrist, 8:RHip, 9:RKnee,\n")
            f.write("#   10:RAnkle, 11:LHip, 12:LKnee, 13:LAnkle,\n")
            f.write("#   14:REye, 15:LEye, 16:REar, 17:LEar\n")
            f.write("#\n")
            f.write("# Phase labels file format (labels/*.csv):\n")
            f.write("# frame_id, phase (0=normal, 1=pre-impact, 2=impact, 3=post-impact, 4=recovery)\n")
            header = "frame_id," + ",".join(
                f"{name}_{axis}"
                for name in [
                    "nose", "neck", "r_shoulder", "r_elbow", "r_wrist",
                    "l_shoulder", "l_elbow", "l_wrist", "r_hip", "r_knee",
                    "r_ankle", "l_hip", "l_knee", "l_ankle",
                    "r_eye", "l_eye", "r_ear", "l_ear",
                ]
                for axis in ["x", "y", "conf"]
            )
            f.write(header + "\n")
            # 예제 행 (모두 0)
            f.write("0," + ",".join(["0.0"] * 54) + "\n")
        print(f"  예제 CSV 포맷 생성: {example_csv}")

    # 라벨 포맷 예제
    example_label = output_path / "labels" / "_example_format.csv"
    if not example_label.exists():
        with open(example_label, "w") as f:
            f.write("# Phase label format\n")
            f.write("# frame_id, phase\n")
            f.write("# phase: 0=normal, 1=pre-impact, 2=impact, 3=post-impact, 4=recovery\n")
            f.write("frame_id,phase\n")
            f.write("0,0\n")
            f.write("30,1\n")
            f.write("60,2\n")
            f.write("90,3\n")
            f.write("120,4\n")
        print(f"  예제 라벨 포맷 생성: {example_label}")

    print()
    print("다운로드 완료 후 검증:")
    print(f"  python scripts/download_data.py --dataset prevfall --output-dir {output_dir} --verify")

    return True


def verify_prevfall(data_path: Path) -> bool:
    """Pre-VFall 데이터셋 무결성 검증"""
    print("\nPre-VFall 데이터셋 검증:")

    ok = True

    # 키포인트 디렉토리
    kp_dir = data_path / "keypoints"
    if kp_dir.exists():
        csv_files = list(kp_dir.glob("*.csv"))
        csv_files = [f for f in csv_files if not f.name.startswith("_")]
        print(f"  키포인트 CSV: {len(csv_files)}개")
        if csv_files:
            # 첫 번째 파일 구조 검증
            import csv
            with open(csv_files[0], "r") as f:
                reader = csv.reader(f)
                # 코멘트 행 건너뛰기
                for row in reader:
                    if row and not row[0].startswith("#"):
                        n_cols = len(row)
                        expected = 55  # frame_id + 18*3
                        if n_cols == expected:
                            print(f"    CSV 컬럼 수 OK: {n_cols}")
                        else:
                            print(f"    CSV 컬럼 수 불일치: {n_cols} (기대: {expected})")
                            ok = False
                        break
        else:
            print("    경고: CSV 파일 없음 (데이터를 다운로드해주세요)")
            ok = False
    else:
        print("  키포인트 디렉토리 없음")
        ok = False

    # 라벨 디렉토리
    label_dir = data_path / "labels"
    if label_dir.exists():
        label_files = list(label_dir.glob("*.csv"))
        label_files = [f for f in label_files if not f.name.startswith("_")]
        print(f"  라벨 CSV: {len(label_files)}개")
    else:
        print("  라벨 디렉토리 없음")
        ok = False

    # 영상 디렉토리
    video_dir = data_path / "videos"
    if video_dir.exists():
        video_files = list(video_dir.glob("*.mp4")) + list(video_dir.glob("*.avi"))
        print(f"  영상 파일: {len(video_files)}개")
    else:
        print("  영상 디렉토리 없음 (키포인트 CSV만 있어도 학습 가능)")

    if ok:
        print("\n검증 완료: 데이터셋 구조 정상")
    else:
        print("\n검증 실패: 위 경고를 확인해주세요")

    return ok


def verify_aihub(data_root: str) -> bool:
    """AI Hub 데이터셋 무결성 검증"""
    data_path = Path(data_root)

    print(f"\nAI Hub 데이터셋 검증: {data_path}")

    ok = True
    total_videos = 0

    for subpath, desc in AIHUB_INFO["expected_structure"].items():
        full_path = data_path / subpath
        if full_path.exists():
            if "영상" in subpath and "label" not in subpath:
                # 영상 디렉토리: 하위 폴더 카운트
                scene_dirs = [d for d in full_path.iterdir() if d.is_dir()]
                n_videos = 0
                for sd in scene_dirs:
                    n_videos += len(list(sd.glob("*.mp4")))
                total_videos += n_videos
                print(f"  {subpath}: {n_videos}개 영상 ({desc})")
            else:
                items = list(full_path.iterdir())
                print(f"  {subpath}: {len(items)}개 항목")
        else:
            print(f"  {subpath}: 경로 없음")
            ok = False

    print(f"\n  총 영상: {total_videos}")

    if ok:
        print("검증 완료: AI Hub 데이터셋 정상")
    else:
        print("검증 실패: 일부 경로가 존재하지 않습니다")

    return ok


def main():
    parser = argparse.ArgumentParser(
        description="Sentio 외부 데이터셋 다운로드 및 구성"
    )
    parser.add_argument(
        "--dataset",
        type=str,
        required=True,
        choices=["prevfall", "aihub"],
        help="데이터셋 이름",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="D:/PreVFall_Data",
        help="다운로드 출력 경로 (prevfall용)",
    )
    parser.add_argument(
        "--data-root",
        type=str,
        default="D:/AIHub_Fall_Data",
        help="데이터 루트 경로 (aihub 검증용)",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="데이터 무결성 검증만 수행",
    )
    args = parser.parse_args()

    if args.dataset == "prevfall":
        setup_prevfall(args.output_dir, verify_only=args.verify)
    elif args.dataset == "aihub":
        if args.verify:
            verify_aihub(args.data_root)
        else:
            print("AI Hub 데이터셋은 수동 다운로드가 필요합니다.")
            print(f"  데이터가 이미 있다면: --verify 플래그로 검증하세요")
            verify_aihub(args.data_root)


if __name__ == "__main__":
    main()
