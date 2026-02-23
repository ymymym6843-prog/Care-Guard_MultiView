"""
Pre-VFall 데이터셋 다운로드 및 압축 해제

Figshare에서 Pre-VFall.rar (21.1 GB)를 다운로드하고
7-Zip으로 압축을 해제합니다.

Usage:
    python scripts/download_prevfall.py --output-dir D:/PreVFall_Data
"""

import hashlib
import os
import subprocess
import sys
import time
import urllib.request

FIGSHARE_URL = "https://ndownloader.figshare.com/files/54008555"
EXPECTED_MD5 = "0308622d728063f8513367d823e07c2a"
FILE_NAME = "Pre-VFall.rar"
EXPECTED_SIZE = 21_096_978_752  # bytes

SEVEN_ZIP = r"C:\Program Files\7-Zip\7z.exe"


def format_size(b: int) -> str:
    if b >= 1024**3:
        return f"{b / 1024**3:.2f} GB"
    elif b >= 1024**2:
        return f"{b / 1024**2:.1f} MB"
    return f"{b / 1024:.0f} KB"


def format_eta(seconds: float) -> str:
    if seconds < 0 or seconds > 86400 * 7:
        return "??:??:??"
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    return f"{h}:{m:02d}:{s:02d}"


def download(url: str, dest: str) -> bool:
    """진행률 표시 + 이어받기 지원 다운로드"""

    # 이어받기: 이미 부분 다운로드된 파일이 있으면 이어서 받기
    existing_size = 0
    if os.path.exists(dest):
        existing_size = os.path.getsize(dest)
        if existing_size >= EXPECTED_SIZE:
            print(f"  이미 다운로드 완료: {dest} ({format_size(existing_size)})")
            return True
        print(f"  이어받기: 기존 {format_size(existing_size)}부터 시작")

    headers = {"User-Agent": "Sentio/1.0"}
    if existing_size > 0:
        headers["Range"] = f"bytes={existing_size}-"

    req = urllib.request.Request(url, headers=headers)

    try:
        response = urllib.request.urlopen(req, timeout=60)
    except urllib.error.URLError as e:
        print(f"  연결 실패: {e}")
        return False

    # Content-Range 확인 (이어받기 지원 여부)
    content_range = response.headers.get("Content-Range")
    if existing_size > 0 and not content_range:
        print("  서버가 이어받기를 지원하지 않습니다. 처음부터 다시 시작합니다.")
        existing_size = 0

    total = EXPECTED_SIZE
    downloaded = existing_size

    mode = "ab" if existing_size > 0 else "wb"
    start_time = time.time()

    chunk_size = 1024 * 1024  # 1 MB

    try:
        with open(dest, mode) as f:
            while True:
                chunk = response.read(chunk_size)
                if not chunk:
                    break
                f.write(chunk)
                downloaded += len(chunk)

                elapsed = time.time() - start_time
                speed = (downloaded - existing_size) / elapsed if elapsed > 0 else 0
                remaining = (total - downloaded) / speed if speed > 0 else 0
                pct = downloaded / total * 100 if total > 0 else 0

                bar_len = 40
                filled = int(pct / 100 * bar_len)
                bar = "=" * filled + ">" + " " * (bar_len - filled - 1)

                print(
                    f"\r  [{bar}] {pct:.1f}% "
                    f"{format_size(downloaded)}/{format_size(total)} "
                    f"({format_size(int(speed))}/s, ETA {format_eta(remaining)})",
                    end="", flush=True,
                )

        print()  # newline
        return True

    except Exception as e:
        print(f"\n  다운로드 중단: {e}")
        print(f"  다시 실행하면 이어받기합니다.")
        return False


def verify_md5(file_path: str, expected: str) -> bool:
    """MD5 체크섬 검증"""
    print(f"  MD5 검증 중... (파일 크기: {format_size(os.path.getsize(file_path))})")
    md5 = hashlib.md5()
    with open(file_path, "rb") as f:
        while True:
            chunk = f.read(1024 * 1024 * 8)  # 8MB chunks
            if not chunk:
                break
            md5.update(chunk)
    actual = md5.hexdigest()
    if actual == expected:
        print(f"  MD5 일치: {actual}")
        return True
    print(f"  MD5 불일치! 기대={expected}, 실제={actual}")
    return False


def extract_rar(rar_path: str, output_dir: str) -> bool:
    """7-Zip으로 RAR 압축 해제"""
    if not os.path.exists(SEVEN_ZIP):
        print(f"  7-Zip 미발견: {SEVEN_ZIP}")
        return False

    print(f"  압축 해제 중: {rar_path} → {output_dir}")
    cmd = [SEVEN_ZIP, "x", "-y", f"-o{output_dir}", rar_path]

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=3600,
        )
        if result.returncode == 0:
            print(f"  압축 해제 완료!")
            return True
        else:
            print(f"  압축 해제 실패: {result.stderr[:500]}")
            return False
    except subprocess.TimeoutExpired:
        print("  압축 해제 타임아웃 (1시간 초과)")
        return False


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Pre-VFall 데이터셋 다운로드")
    parser.add_argument("--output-dir", type=str, default="D:/PreVFall_Data")
    parser.add_argument("--skip-verify", action="store_true", help="MD5 검증 건너뛰기")
    parser.add_argument("--skip-extract", action="store_true", help="압축 해제 건너뛰기")
    args = parser.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)
    rar_path = os.path.join(args.output_dir, FILE_NAME)

    print(f"{'='*60}")
    print(f"Pre-VFall 데이터셋 다운로드")
    print(f"{'='*60}")
    print(f"  URL: {FIGSHARE_URL}")
    print(f"  크기: {format_size(EXPECTED_SIZE)}")
    print(f"  저장: {rar_path}")
    print()

    # 1단계: 다운로드
    print("[1/3] 다운로드")
    if not download(FIGSHARE_URL, rar_path):
        print("다운로드 실패. 네트워크 확인 후 다시 실행하세요.")
        sys.exit(1)

    # 2단계: MD5 검증
    if not args.skip_verify:
        print("\n[2/3] MD5 검증")
        if not verify_md5(rar_path, EXPECTED_MD5):
            print("파일이 손상되었을 수 있습니다. 삭제 후 다시 다운로드하세요.")
            sys.exit(1)
    else:
        print("\n[2/3] MD5 검증 건너뜀")

    # 3단계: 압축 해제
    if not args.skip_extract:
        print("\n[3/3] 압축 해제 (7-Zip)")
        if not extract_rar(rar_path, args.output_dir):
            print(f"수동 해제: \"{SEVEN_ZIP}\" x \"{rar_path}\" -o\"{args.output_dir}\"")
            sys.exit(1)
    else:
        print("\n[3/3] 압축 해제 건너뜀")

    # 결과 확인
    print(f"\n{'='*60}")
    print(f"완료!")
    print(f"  경로: {args.output_dir}")

    # 폴더 구조 표시
    for item in sorted(os.listdir(args.output_dir)):
        full = os.path.join(args.output_dir, item)
        if os.path.isdir(full):
            n_files = sum(1 for _ in os.scandir(full))
            print(f"  {item}/ ({n_files} items)")
        elif item != FILE_NAME:
            print(f"  {item} ({format_size(os.path.getsize(full))})")

    print(f"\n다음 단계:")
    print(f"  python scripts/training/data_preprocessing.py \\")
    print(f"      --source prevfall --input-dir {args.output_dir} \\")
    print(f"      --output {args.output_dir}/landmarks/prevfall_landmarks.npz")


if __name__ == "__main__":
    main()
