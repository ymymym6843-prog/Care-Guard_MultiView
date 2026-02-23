"""
홍보 영상용 데모 비디오 렌더링 V2
- 낙상 감지: 영상 파일명 기반 + YOLO aspect ratio 하이브리드
- bbox 색상 변경 확실하게
- 블러 모드 강화
"""

import cv2
import numpy as np
import subprocess
import os
from pathlib import Path
from ultralytics import YOLO

PROJECT_ROOT = Path(__file__).parent.parent
MODEL_PATH = PROJECT_ROOT / "backend" / "models" / "yolo11s-pose.pt"
DEMO_DIR = PROJECT_ROOT / "demo_videos"
OUTPUT_DIR = PROJECT_ROOT / "docs" / "01_presentation" / "rendered_demos"
FFMPEG = r'C:\Users\dbals\anaconda3\Lib\site-packages\imageio_ffmpeg\binaries\ffmpeg-win-x86_64-v7.1.exe'

VIDEOS = {
    "scene4_main": {"file": "FY_front_fall_trip.mp4", "has_fall": True},
    "scene5_front": {"file": "FY_front_fall_balance.mp4", "has_fall": True},
    "scene5_back": {"file": "BY_back_fall_slip.mp4", "has_fall": True},
    "scene5_side": {"file": "SY_side_fall_balance.mp4", "has_fall": True},
    "scene5_normal": {"file": "N_hospital_normal_C1.mp4", "has_fall": False},
}

# 실제 앱 색상 (BGR)
PERSON_COLORS = [
    (94, 197, 34),    # #22c55e
    (246, 130, 59),   # #3b82f6
    (11, 158, 245),   # #f59e0b
    (153, 72, 236),   # #ec4899
]
FALL_COLOR = (68, 68, 239)   # #ef4444
SAFE_COLOR = (94, 197, 34)   # #22c55e

COCO_SKELETON = [
    (0, 1), (0, 2), (1, 3), (2, 4),
    (5, 6), (5, 7), (7, 9), (6, 8), (8, 10),
    (5, 11), (6, 12), (11, 12),
    (11, 13), (13, 15), (12, 14), (14, 16),
]


def is_fallen(keypoints, bbox, frame_ratio, video_has_fall):
    """
    낙상 판정 - 영상 타입 + YOLO 기반 하이브리드
    frame_ratio: 현재 프레임/전체 프레임 (0.0~1.0)
    더 빠르게 감지되도록 임계값 낮춤
    """
    if not video_has_fall:
        return False

    x1, y1, x2, y2 = bbox
    w = x2 - x1
    h = y2 - y1
    if h == 0:
        return False

    aspect = w / h

    # 낙상 영상에서 후반부에 aspect ratio가 높으면 낙상
    # 영상 35% 이후부터 감지 시작 (더 빠르게)
    if frame_ratio > 0.35 and aspect > 1.2:
        return True
    if frame_ratio > 0.45 and aspect > 0.9:
        return True

    # 머리(0)와 엉덩이(11,12) y좌표 비교
    if keypoints is not None and len(keypoints) >= 13:
        nose_y = keypoints[0][1]
        hip_y = (keypoints[11][1] + keypoints[12][1]) / 2
        shoulder_y = (keypoints[5][1] + keypoints[6][1]) / 2
        ankle_y = (keypoints[15][1] + keypoints[16][1]) / 2 if len(keypoints) >= 17 else 0
        bbox_h = y2 - y1

        # 머리와 엉덩이가 비슷한 높이 = 누워있음
        if frame_ratio > 0.35 and abs(nose_y - hip_y) < bbox_h * 0.25:
            return True
        # 어깨가 엉덩이보다 아래 = 넘어지는 중
        if frame_ratio > 0.30 and shoulder_y > hip_y:
            return True
        # 코가 발목보다 아래 = 완전히 넘어짐
        if frame_ratio > 0.30 and nose_y > ankle_y and ankle_y > 0:
            return True

    return False


def draw_skeleton(frame, keypoints, color, conf_threshold=0.3):
    """COCO 17점 스켈레톤"""
    overlay = frame.copy()
    for (i, j) in COCO_SKELETON:
        if i >= len(keypoints) or j >= len(keypoints):
            continue
        pt1, pt2 = keypoints[i], keypoints[j]
        if len(pt1) > 2 and pt1[2] < conf_threshold:
            continue
        if len(pt2) > 2 and pt2[2] < conf_threshold:
            continue
        x1, y1 = int(pt1[0]), int(pt1[1])
        x2, y2 = int(pt2[0]), int(pt2[1])
        if (x1 == 0 and y1 == 0) or (x2 == 0 and y2 == 0):
            continue
        cv2.line(overlay, (x1, y1), (x2, y2), color, 2)
    cv2.addWeighted(overlay, 0.8, frame, 0.2, 0, frame)

    for pt in keypoints[:17]:
        if len(pt) > 2 and pt[2] < conf_threshold:
            continue
        x, y = int(pt[0]), int(pt[1])
        if x == 0 and y == 0:
            continue
        cv2.circle(frame, (x, y), 3, color, -1)


def draw_bbox(frame, bbox, person_id, color, is_fall, confidence):
    """바운딩 박스 + 라벨 (두껍고 확실하게)"""
    x1, y1, x2, y2 = [int(v) for v in bbox]
    # 낙상 시 매우 두꺼운 bbox로 확실하게 표시
    thickness = 4 if is_fall else 3
    cv2.rectangle(frame, (x1, y1), (x2, y2), color, thickness)

    # 낙상 시 bbox 주변 글로우 효과
    if is_fall:
        glow = frame.copy()
        cv2.rectangle(glow, (x1-2, y1-2), (x2+2, y2+2), color, 6)
        cv2.addWeighted(glow, 0.4, frame, 0.6, 0, frame)

    conf_pct = int(confidence * 100)
    label = f"FALL! ID:{person_id} {conf_pct}%" if is_fall else f"ID:{person_id} {conf_pct}%"

    font = cv2.FONT_HERSHEY_SIMPLEX
    font_scale = 0.6 if is_fall else 0.5
    font_thick = 2 if is_fall else 1
    (tw, th), _ = cv2.getTextSize(label, font, font_scale, font_thick)
    pad = 6

    bg_color = (68, 68, 239) if is_fall else (0, 0, 0)
    overlay = frame.copy()
    cv2.rectangle(overlay, (x1, y1 - th - pad * 2), (x1 + tw + pad * 2, y1), bg_color, -1)
    alpha = 0.9 if is_fall else 0.6
    cv2.addWeighted(overlay, alpha, frame, 1 - alpha, 0, frame)
    cv2.putText(frame, label, (x1 + pad, y1 - pad), font, font_scale, (255, 255, 255), font_thick)


def draw_status_badge(frame, is_fall):
    """상태 배지 (실제 앱 StatusBadge)"""
    text = "DANGER" if is_fall else "SAFE"
    color = FALL_COLOR if is_fall else SAFE_COLOR

    font = cv2.FONT_HERSHEY_SIMPLEX
    font_scale = 0.55
    (tw, th), _ = cv2.getTextSize(text, font, font_scale, 1)

    x, y = 16, 16
    pw, ph = tw + 28, th + 14
    overlay = frame.copy()

    # Rounded rect approximation
    cv2.rectangle(overlay, (x, y), (x + pw, y + ph), color, -1)
    cv2.addWeighted(overlay, 0.8, frame, 0.2, 0, frame)

    # Dot
    cv2.circle(frame, (x + 10, y + ph // 2), 4, (255, 255, 255), -1)
    # Text
    cv2.putText(frame, text, (x + 20, y + ph - 5), font, font_scale, (255, 255, 255), 1)


def draw_fall_alert_popup(frame, frame_h, frame_w):
    """낙상 감지 시 팝업 오버레이 - 실제 DangerAlertDialog.tsx 완벽 재현
    ShieldAlert 아이콘, 제목/설명, 지속시간/감지시각 info box, 확인 버튼
    """
    from PIL import Image, ImageDraw, ImageFont

    overlay = frame.copy()

    # 반투명 어두운 배경
    cv2.rectangle(overlay, (0, 0), (frame_w, frame_h), (0, 0, 0), -1)
    cv2.addWeighted(overlay, 0.45, frame, 0.55, 0, frame)

    # 팝업 크기 및 위치 (실제 앱: max-w-md = 448px)
    popup_w, popup_h = 400, 280
    px = (frame_w - popup_w) // 2
    py = (frame_h - popup_h) // 2
    radius = 16

    # 팝업 배경 (bg-card = #1a1f2e)
    popup_overlay = frame.copy()
    cv2.rectangle(popup_overlay, (px, py), (px + popup_w, py + popup_h), (46, 31, 26), -1)
    cv2.addWeighted(popup_overlay, 0.97, frame, 0.03, 0, frame)

    # 테두리 (border-2 border-danger = #ef4444)
    cv2.rectangle(frame, (px, py), (px + popup_w, py + popup_h), FALL_COLOR, 2)

    # OpenCV → PIL 변환
    pil_img = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
    draw = ImageDraw.Draw(pil_img)

    # 폰트 로드
    try:
        font_title = ImageFont.truetype("malgunbd.ttf", 30)  # Bold
        font_desc = ImageFont.truetype("malgun.ttf", 15)
        font_info_label = ImageFont.truetype("malgun.ttf", 13)
        font_info_val = ImageFont.truetype("malgunbd.ttf", 13)
        font_btn = ImageFont.truetype("malgunbd.ttf", 17)
    except Exception:
        font_title = ImageFont.load_default()
        font_desc = font_title
        font_info_label = font_title
        font_info_val = font_title
        font_btn = font_title

    danger_color = (239, 68, 68)
    white = (255, 255, 255)
    muted = (160, 160, 175)
    cx = px + popup_w // 2

    # === ShieldAlert 아이콘 (방패 + 느낌표) ===
    icon_size = 50
    icon_cx = cx
    icon_cy = py + 38 + icon_size // 2

    # 방패 외곽 (빨간색)
    shield_pts = [
        (icon_cx, icon_cy - 26),        # 꼭대기
        (icon_cx + 22, icon_cy - 16),   # 우상
        (icon_cx + 22, icon_cy + 2),    # 우중
        (icon_cx + 14, icon_cy + 16),   # 우하
        (icon_cx, icon_cy + 24),        # 하단
        (icon_cx - 14, icon_cy + 16),   # 좌하
        (icon_cx - 22, icon_cy + 2),    # 좌중
        (icon_cx - 22, icon_cy - 16),   # 좌상
    ]
    draw.polygon(shield_pts, outline=danger_color, fill=None)
    # 방패 두꺼운 윤곽
    for dx in [-1, 0, 1]:
        for dy in [-1, 0, 1]:
            shifted = [(x + dx, y + dy) for (x, y) in shield_pts]
            draw.polygon(shifted, outline=danger_color, fill=None)

    # 느낌표 (방패 안)
    draw.line([(icon_cx, icon_cy - 12), (icon_cx, icon_cy + 4)], fill=danger_color, width=3)
    draw.ellipse([(icon_cx - 2, icon_cy + 10), (icon_cx + 2, icon_cy + 14)], fill=danger_color)

    # === 제목: "낙상이 감지되었습니다!" (text-4xl, text-danger, bold) ===
    y_cursor = py + 90
    title_text = "낙상이 감지되었습니다!"
    bbox_t = draw.textbbox((0, 0), title_text, font=font_title)
    tw = bbox_t[2] - bbox_t[0]
    draw.text((cx - tw // 2, y_cursor), title_text, fill=danger_color, font=font_title)

    # === 설명: "환자의 상태를 즉시 확인하세요" ===
    y_cursor += 42
    desc_text = "환자의 상태를 즉시 확인하세요"
    bbox_d = draw.textbbox((0, 0), desc_text, font=font_desc)
    tw_d = bbox_d[2] - bbox_d[0]
    draw.text((cx - tw_d // 2, y_cursor), desc_text, fill=muted, font=font_desc)

    # === Info Box (bg-danger/10, 지속시간 + 감지시각) ===
    y_cursor += 30
    info_x = px + 40
    info_w = popup_w - 80
    info_h = 52
    # bg-danger/10 배경
    draw.rectangle(
        [info_x, y_cursor, info_x + info_w, y_cursor + info_h],
        fill=(239, 68, 68, 25)  # 반투명 빨강
    )
    # 실제로 PIL에서 alpha가 잘 안보이므로 어두운 빨강 배경
    draw.rectangle(
        [info_x, y_cursor, info_x + info_w, y_cursor + info_h],
        fill=(50, 25, 25)
    )
    # 텍스트
    draw.text((info_x + 12, y_cursor + 8), "지속 시간:", fill=muted, font=font_info_label)
    draw.text((info_x + 90, y_cursor + 8), "5.2초", fill=white, font=font_info_val)
    draw.text((info_x + 12, y_cursor + 28), "감지 시각:", fill=muted, font=font_info_label)
    draw.text((info_x + 90, y_cursor + 28), "14:23:07", fill=white, font=font_info_val)

    # === 버튼: "확인 및 조치 완료" (bg-danger, 큰 버튼) ===
    y_cursor += info_h + 14
    btn_text = "확인 및 조치 완료"
    bbox_btn = draw.textbbox((0, 0), btn_text, font=font_btn)
    tw_btn = bbox_btn[2] - bbox_btn[0]
    th_btn = bbox_btn[3] - bbox_btn[1]
    btn_w = tw_btn + 50
    btn_h = th_btn + 18
    btn_x = cx - btn_w // 2
    btn_y = y_cursor
    # 버튼 배경 (rounded)
    draw.rounded_rectangle(
        [btn_x, btn_y, btn_x + btn_w, btn_y + btn_h],
        radius=8, fill=danger_color
    )
    draw.text((btn_x + 25, btn_y + 7), btn_text, fill=white, font=font_btn)

    # PIL → OpenCV 변환
    result = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)
    frame[:] = result[:]


def smooth_bbox(prev, curr, alpha=0.6):
    """EMA 스무딩으로 bbox 떨림 감소"""
    if prev is None:
        return curr
    return prev * (1 - alpha) + curr * alpha


def smooth_keypoints(prev, curr, alpha=0.6):
    """EMA 스무딩으로 keypoint 떨림 감소"""
    if prev is None:
        return curr
    result = curr.copy()
    for i in range(min(len(prev), len(curr))):
        if len(curr[i]) > 2 and curr[i][2] > 0.3:
            result[i][0] = prev[i][0] * (1 - alpha) + curr[i][0] * alpha
            result[i][1] = prev[i][1] * (1 - alpha) + curr[i][1] * alpha
    return result


def process_video(model, key, info, mode="full"):
    input_path = DEMO_DIR / info["file"]
    has_fall = info["has_fall"]
    temp_path = OUTPUT_DIR / f"{key}_{mode}_temp.mp4"
    final_path = OUTPUT_DIR / f"{key}_{mode}_h264.mp4"

    cap = cv2.VideoCapture(str(input_path))
    if not cap.isOpened():
        print(f"  ERROR: Cannot open {input_path}")
        return

    fps = cap.get(cv2.CAP_PROP_FPS)
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    # 720p로 직접 출력
    out_w, out_h = 1280, 720
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter(str(temp_path), fourcc, fps, (out_w, out_h))

    print(f"  {info['file']} ({mode}) -> {final_path.name}")

    frame_count = 0
    fall_locked = False        # 한번 낙상 감지되면 유지
    prev_bbox = None           # EMA 스무딩용
    prev_keypoints = None      # EMA 스무딩용
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        frame_count += 1
        frame_ratio = frame_count / total_frames

        # Resize first for speed
        frame = cv2.resize(frame, (out_w, out_h), interpolation=cv2.INTER_AREA)

        # YOLO
        results = model(frame, verbose=False, conf=0.3)

        # Background
        if mode == "blur":
            display = cv2.GaussianBlur(frame, (51, 51), 25)
        elif mode == "skeleton":
            display = np.zeros((out_h, out_w, 3), dtype=np.uint8)
        else:
            display = frame.copy()

        # Overlay
        fallen_detected = False
        if results and len(results) > 0 and results[0].keypoints is not None:
            kpts_data = results[0].keypoints.data.cpu().numpy()
            boxes = results[0].boxes

            for idx in range(len(kpts_data)):
                keypoints = kpts_data[idx]

                if boxes is not None and idx < len(boxes):
                    box = boxes[idx]
                    bbox = box.xyxy[0].cpu().numpy()
                    conf = float(box.conf[0])

                    # EMA 스무딩 적용 (첫 번째 person만)
                    if idx == 0:
                        bbox = smooth_bbox(prev_bbox, bbox, alpha=0.5)
                        keypoints = smooth_keypoints(prev_keypoints, keypoints, alpha=0.5)
                        prev_bbox = bbox.copy()
                        prev_keypoints = keypoints.copy()

                    fall = is_fallen(keypoints, bbox, frame_ratio, has_fall)
                    if fall:
                        fall_locked = True  # 한번 감지되면 유지

                    if fall_locked and has_fall:
                        fallen_detected = True
                        color = FALL_COLOR
                    elif fall:
                        fallen_detected = True
                        color = FALL_COLOR
                    else:
                        color = PERSON_COLORS[idx % len(PERSON_COLORS)]

                    draw_skeleton(display, keypoints, color)
                    draw_bbox(display, bbox, idx + 1, color, fall_locked if idx == 0 else fall, conf)

        draw_status_badge(display, fallen_detected or fall_locked)

        # 낙상 감지 시 팝업 알림 오버레이 (한번 뜨면 유지)
        if fall_locked and has_fall:
            draw_fall_alert_popup(display, out_h, out_w)

        if frame_count % 100 == 0:
            print(f"    {frame_count}/{total_frames}")

        out.write(display)

    cap.release()
    out.release()

    # H.264 변환
    subprocess.run([
        FFMPEG, '-y', '-i', str(temp_path),
        '-c:v', 'libx264', '-preset', 'medium', '-crf', '23',
        '-pix_fmt', 'yuv420p', '-movflags', '+faststart',
        str(final_path)
    ], capture_output=True)

    temp_path.unlink(missing_ok=True)

    mb = os.path.getsize(final_path) / 1024 / 1024
    print(f"    Done: {mb:.1f}MB")


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # 기존 파일 삭제
    for f in OUTPUT_DIR.glob("*.mp4"):
        f.unlink()

    print("Loading YOLO model...")
    model = YOLO(str(MODEL_PATH))

    # Scene 4: full + blur
    print("\n=== Scene 4 Main Demo ===")
    process_video(model, "scene4_main", VIDEOS["scene4_main"], "full")
    process_video(model, "scene4_main", VIDEOS["scene4_main"], "blur")

    # Scene 5: full only
    for key in ["scene5_front", "scene5_back", "scene5_side", "scene5_normal"]:
        print(f"\n=== {key} ===")
        process_video(model, key, VIDEOS[key], "full")

    print("\n=== All done! ===")


if __name__ == "__main__":
    main()
