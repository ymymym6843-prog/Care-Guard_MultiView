"""
프레젠테이션용 프레임 추출 스크립트

데모 영상에서 발표자료에 사용할 깔끔한 이미지를 생성합니다.

사용법:
    python scripts/extract_presentation_frames.py \
        --source demo_videos/wheelchair_test.mp4 \
        --output docs/presentation_frames \
        --mode simple \
        --frames 15,43,84

모드:
    clean  - 원본 프레임만 (어노테이션 없음)
    simple - 발표용 최소 어노테이션 (바운딩 박스 + 한글 라벨 + 스켈레톤 점)
    full   - 디버그용 전체 정보 (score, ML값, 버퍼 크기 등)
"""

import argparse
import sys
from pathlib import Path

import cv2
import numpy as np


# MediaPipe Pose 33-point 연결선
POSE_CONNECTIONS = [
    (11, 12), (11, 13), (13, 15), (12, 14), (14, 16),  # 상체
    (11, 23), (12, 24), (23, 24),                         # 몸통
    (23, 25), (25, 27), (24, 26), (26, 28),               # 하체
    (15, 17), (15, 19), (16, 18), (16, 20),               # 손
    (27, 29), (27, 31), (28, 30), (28, 32),               # 발
]

# 한글 라벨 렌더링을 위한 PIL (없으면 OpenCV 영문 폴백)
try:
    from PIL import Image, ImageDraw, ImageFont
    HAS_PIL = True
except ImportError:
    HAS_PIL = False


def draw_rounded_rect(img, pt1, pt2, color, thickness, radius=12):
    """둥근 모서리 사각형 그리기"""
    x1, y1 = pt1
    x2, y2 = pt2
    r = min(radius, abs(x2 - x1) // 4, abs(y2 - y1) // 4)

    # 4개의 직선
    cv2.line(img, (x1 + r, y1), (x2 - r, y1), color, thickness)
    cv2.line(img, (x1 + r, y2), (x2 - r, y2), color, thickness)
    cv2.line(img, (x1, y1 + r), (x1, y2 - r), color, thickness)
    cv2.line(img, (x2, y1 + r), (x2, y2 - r), color, thickness)

    # 4개의 모서리 호
    cv2.ellipse(img, (x1 + r, y1 + r), (r, r), 180, 0, 90, color, thickness)
    cv2.ellipse(img, (x2 - r, y1 + r), (r, r), 270, 0, 90, color, thickness)
    cv2.ellipse(img, (x1 + r, y2 - r), (r, r), 90, 0, 90, color, thickness)
    cv2.ellipse(img, (x2 - r, y2 - r), (r, r), 0, 0, 90, color, thickness)


def put_korean_text(img, text, position, font_size=28, color=(255, 255, 255)):
    """한글 텍스트 렌더링 (PIL 사용, 없으면 OpenCV 폴백)"""
    if HAS_PIL:
        pil_img = Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
        draw = ImageDraw.Draw(pil_img)
        try:
            font = ImageFont.truetype("malgun.ttf", font_size)
        except OSError:
            try:
                font = ImageFont.truetype("/usr/share/fonts/truetype/noto/NotoSansKR-Bold.ttf", font_size)
            except OSError:
                font = ImageFont.load_default()
        draw.text(position, text, font=font, fill=color)
        result = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)
        np.copyto(img, result)
    else:
        cv2.putText(img, text, position, cv2.FONT_HERSHEY_SIMPLEX,
                    font_size / 28, color, 2, cv2.LINE_AA)


def draw_skeleton_dots(img, landmarks, w, h, color=(0, 255, 255), radius=5):
    """스켈레톤 관절점만 그리기 (발표용 간결한 스타일)"""
    for lm in landmarks:
        x, y, vis = int(lm[0] * w), int(lm[1] * h), lm[3] if len(lm) > 3 else 1.0
        if vis < 0.3:
            continue
        cv2.circle(img, (x, y), radius, color, -1, cv2.LINE_AA)


def draw_skeleton_lines(img, landmarks, w, h, color=(0, 255, 255), thickness=2):
    """스켈레톤 연결선 그리기"""
    for start_idx, end_idx in POSE_CONNECTIONS:
        if start_idx >= len(landmarks) or end_idx >= len(landmarks):
            continue
        s = landmarks[start_idx]
        e = landmarks[end_idx]
        s_vis = s[3] if len(s) > 3 else 1.0
        e_vis = e[3] if len(e) > 3 else 1.0
        if s_vis < 0.3 or e_vis < 0.3:
            continue
        sx, sy = int(s[0] * w), int(s[1] * h)
        ex, ey = int(e[0] * w), int(e[1] * h)
        cv2.line(img, (sx, sy), (ex, ey), color, thickness, cv2.LINE_AA)


def detect_persons_simple(frame):
    """간단한 인물 감지 (YOLO 없이 MediaPipe 사용)

    Returns list of dicts: {bbox: (x1,y1,x2,y2) normalized, landmarks: [...], is_fallen: bool}
    """
    try:
        import mediapipe as mp
        mp_pose = mp.solutions.pose
    except ImportError:
        print("[WARN] mediapipe not available, returning empty detections")
        return []

    results = []
    h, w = frame.shape[:2]
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

    with mp_pose.Pose(
        static_image_mode=True,
        model_complexity=2,
        min_detection_confidence=0.5,
    ) as pose:
        result = pose.process(rgb)
        if result.pose_landmarks:
            landmarks = []
            xs, ys = [], []
            for lm in result.pose_landmarks.landmark:
                landmarks.append([lm.x, lm.y, lm.z, lm.visibility])
                if lm.visibility > 0.3:
                    xs.append(lm.x)
                    ys.append(lm.y)

            if xs and ys:
                pad = 0.05
                bbox = (
                    max(0, min(xs) - pad),
                    max(0, min(ys) - pad),
                    min(1, max(xs) + pad),
                    min(1, max(ys) + pad),
                )

                # 간단한 낙상 판정: 머리 y > 엉덩이 y
                head_y = landmarks[0][1] if landmarks[0][3] > 0.3 else 0
                hip_y = (landmarks[23][1] + landmarks[24][1]) / 2
                is_fallen = head_y > hip_y + 0.02

                results.append({
                    "bbox": bbox,
                    "landmarks": landmarks,
                    "is_fallen": is_fallen,
                })

    return results


def annotate_simple(frame, persons, frame_time_sec, step_label=""):
    """발표용 간결한 어노테이션"""
    img = frame.copy()
    h, w = img.shape[:2]

    for person in persons:
        bbox = person["bbox"]
        is_fallen = person["is_fallen"]
        landmarks = person["landmarks"]

        # 바운딩 박스 색상
        color = (0, 0, 255) if is_fallen else (0, 220, 0)  # BGR: 빨강 or 초록
        x1 = int(bbox[0] * w)
        y1 = int(bbox[1] * h)
        x2 = int(bbox[2] * w)
        y2 = int(bbox[3] * h)

        # 둥근 모서리 바운딩 박스
        draw_rounded_rect(img, (x1, y1), (x2, y2), color, 3)

        # 한글 라벨
        label = "낙상 감지!" if is_fallen else "정상"
        label_color = (80, 80, 255) if is_fallen else (80, 220, 80)
        put_korean_text(img, label, (x1, y1 - 35), font_size=26, color=label_color)

        # 스켈레톤 (선 + 점)
        skel_color = (100, 100, 255) if is_fallen else (255, 255, 0)
        draw_skeleton_lines(img, landmarks, w, h, color=skel_color, thickness=2)
        draw_skeleton_dots(img, landmarks, w, h, color=skel_color, radius=4)

    # 하단 시간 표시
    time_text = f"T={frame_time_sec:.1f}s"
    if step_label:
        time_text = f"{step_label}  |  {time_text}"

    # 반투명 배경 바
    overlay = img.copy()
    cv2.rectangle(overlay, (0, h - 50), (w, h), (0, 0, 0), -1)
    cv2.addWeighted(overlay, 0.6, img, 0.4, 0, img)
    put_korean_text(img, time_text, (20, h - 42), font_size=22, color=(220, 220, 220))

    return img


def extract_frames(source: str, output_dir: str, mode: str, frame_numbers: list[int]):
    """메인 프레임 추출 로직"""
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    cap = cv2.VideoCapture(source)
    if not cap.isOpened():
        print(f"[ERROR] Cannot open video: {source}")
        sys.exit(1)

    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    print(f"Video: {source}")
    print(f"  FPS: {fps}, Total frames: {total_frames}")
    print(f"  Mode: {mode}, Target frames: {frame_numbers}")

    step_labels = ["1단계: 사람 찾기", "2단계: 자세 분석", "3단계: 낙상 감지"]
    step_filenames = [
        "wheelchair_step1_detect.jpg",
        "wheelchair_step2_analyze.jpg",
        "wheelchair_step3_alert.jpg",
    ]

    extracted = 0
    for i, frame_num in enumerate(frame_numbers):
        if frame_num >= total_frames:
            print(f"  [SKIP] Frame {frame_num} exceeds total ({total_frames})")
            continue

        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_num)
        ret, frame = cap.read()
        if not ret:
            print(f"  [SKIP] Cannot read frame {frame_num}")
            continue

        time_sec = frame_num / fps

        if mode == "clean":
            out_frame = frame.copy()
        elif mode == "simple":
            persons = detect_persons_simple(frame)
            label = step_labels[i] if i < len(step_labels) else ""
            out_frame = annotate_simple(frame, persons, time_sec, step_label=label)
        else:  # full
            persons = detect_persons_simple(frame)
            label = step_labels[i] if i < len(step_labels) else ""
            out_frame = annotate_simple(frame, persons, time_sec, step_label=label)

        filename = step_filenames[i] if i < len(step_filenames) else f"frame_{frame_num:06d}.jpg"
        out_file = out_path / filename
        cv2.imwrite(str(out_file), out_frame, [cv2.IMWRITE_JPEG_QUALITY, 92])
        print(f"  [OK] Frame {frame_num} -> {out_file} ({time_sec:.1f}s)")
        extracted += 1

    cap.release()
    print(f"\nDone: {extracted} frames extracted to {out_path}")
    return extracted


def main():
    parser = argparse.ArgumentParser(
        description="프레젠테이션용 프레임 추출 (SENTIO Phase 23)"
    )
    parser.add_argument(
        "--source", required=True,
        help="데모 영상 파일 경로 (예: demo_videos/wheelchair_test.mp4)"
    )
    parser.add_argument(
        "--output", default="docs/presentation_frames",
        help="출력 디렉토리 (기본: docs/presentation_frames)"
    )
    parser.add_argument(
        "--mode", choices=["clean", "simple", "full"], default="simple",
        help="모드: clean(원본), simple(발표용), full(디버그)"
    )
    parser.add_argument(
        "--frames", default="15,43,84",
        help="추출할 프레임 번호 (콤마 구분, 예: 15,43,84)"
    )

    args = parser.parse_args()
    frame_numbers = [int(f.strip()) for f in args.frames.split(",")]
    extract_frames(args.source, args.output, args.mode, frame_numbers)


if __name__ == "__main__":
    main()
