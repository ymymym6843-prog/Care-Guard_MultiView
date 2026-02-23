"""
렌더링된 데모 영상을 GIF로 변환
- 10fps로 샘플링 (원본 60fps → 파일 크기 대폭 감소)
- 720p → 480p 리사이즈 (발표자료 그리드에 맞게)
- ffmpeg 사용
"""
import subprocess
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
INPUT_DIR = PROJECT_ROOT / "docs" / "01_presentation" / "rendered_demos"
OUTPUT_DIR = INPUT_DIR  # 같은 폴더에 저장
FFMPEG = r'C:\Users\dbals\anaconda3\Lib\site-packages\imageio_ffmpeg\binaries\ffmpeg-win-x86_64-v7.1.exe'

# 변환할 영상 목록
VIDEOS = {
    "scene5_front_full_h264.mp4": "scene5_front.gif",
    "scene5_back_full_h264.mp4": "scene5_back.gif",
    "scene5_side_full_h264.mp4": "scene5_side.gif",
    "scene5_normal_full_h264.mp4": "scene5_normal.gif",
    "scene4_main_full_h264.mp4": "scene4_full.gif",
    "scene4_main_blur_h264.mp4": "scene4_blur.gif",
}

def convert_to_gif(input_path, output_path, fps=10, width=480):
    """ffmpeg로 MP4 → GIF 변환 (팔레트 최적화)"""
    palette_path = str(output_path) + "_palette.png"

    # 1단계: 최적 팔레트 생성
    subprocess.run([
        FFMPEG, '-y', '-i', str(input_path),
        '-vf', f'fps={fps},scale={width}:-1:flags=lanczos,palettegen=stats_mode=diff',
        palette_path
    ], capture_output=True)

    # 2단계: 팔레트 사용하여 GIF 생성
    subprocess.run([
        FFMPEG, '-y', '-i', str(input_path), '-i', palette_path,
        '-lavfi', f'fps={fps},scale={width}:-1:flags=lanczos[x];[x][1:v]paletteuse=dither=bayer:bayer_scale=3',
        '-loop', '0',
        str(output_path)
    ], capture_output=True)

    # 팔레트 임시 파일 삭제
    if os.path.exists(palette_path):
        os.unlink(palette_path)

    if os.path.exists(output_path):
        mb = os.path.getsize(output_path) / 1024 / 1024
        print(f"  {output_path.name}: {mb:.1f}MB")
    else:
        print(f"  ERROR: {output_path.name} not created")


def main():
    print("Converting MP4 → GIF (palette-optimized)...")
    print(f"Settings: 10fps, 480px wide, loop forever\n")

    for mp4_name, gif_name in VIDEOS.items():
        input_path = INPUT_DIR / mp4_name
        output_path = OUTPUT_DIR / gif_name

        if not input_path.exists():
            print(f"  SKIP: {mp4_name} not found")
            continue

        print(f"  {mp4_name} → {gif_name}...")
        convert_to_gif(input_path, output_path)

    print("\nAll done!")


if __name__ == "__main__":
    main()
