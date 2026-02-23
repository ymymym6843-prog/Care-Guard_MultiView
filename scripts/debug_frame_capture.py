"""
프레임별 낙상 감지 분석 스크립트 (스크린샷 저장)

영상을 프레임별로 처리하고 주요 프레임을 이미지로 저장합니다:
- 매 30프레임마다 상태 스냅샷
- 낙상 감지 시점 전후 프레임
- score 변화가 큰 프레임

출력: output_dir에 프레임 이미지 + 분석 로그(CSV)
"""

import os
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

import argparse
import csv
import sys
import time
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.config import settings


def main():
    parser = argparse.ArgumentParser(description="프레임별 낙상 감지 분석")
    parser.add_argument("--source", required=True, help="영상 파일 경로")
    parser.add_argument("--output", default="debug_frames", help="출력 디렉토리")
    parser.add_argument("--interval", type=int, default=15, help="정기 캡처 간격 (프레임)")
    parser.add_argument("--max-frames", type=int, default=0, help="최대 프레임 수 (0=전체)")
    args = parser.parse_args()

    cap = cv2.VideoCapture(args.source)
    if not cap.isOpened():
        print(f"ERROR: 영상을 열 수 없습니다: {args.source}")
        return

    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    video_fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    print(f"영상: {args.source}")
    print(f"해상도: {w}x{h}, FPS: {video_fps:.1f}, 총 프레임: {total_frames}")

    # 출력 디렉토리
    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)

    # 모델 로딩
    print("모델 로딩 중...")
    from app.services.multi_person_detector import multi_person_detector
    from app.services.walking_aid_detector import walking_aid_detector
    from app.services.pose_service import pose_service
    from app.services.fall_detector import fall_detector
    from app.services.fall_classifier import fall_classifier
    from app.services.posture_classifier import posture_classifier

    print(f"  YOLO: {'ON' if multi_person_detector.enabled else 'OFF'}")
    print(f"  Walking aid: {'ON' if walking_aid_detector.enabled else 'OFF'}")
    print(f"  ML classifier: {'ON' if fall_classifier.enabled else 'OFF'}")
    print()

    # CSV 로그
    csv_path = out_dir / "analysis.csv"
    csv_file = open(csv_path, "w", newline="", encoding="utf-8")
    writer = csv.writer(csv_file)
    writer.writerow([
        "frame", "time_sec", "person_id", "posture", "score", "rule_score",
        "ml_score", "ml_raw", "ml_buf", "is_fallen", "fall_type",
        "c1_invert", "c2_descent", "c3_horiz", "c5_slump", "c6_tilt", "c7_drop",
        "visibility", "saved_img"
    ])

    frame_num = 0
    prev_scores = {}  # person_id → prev score
    saved_count = 0

    max_frames = args.max_frames if args.max_frames > 0 else total_frames

    while frame_num < max_frames:
        ret, frame = cap.read()
        if not ret:
            break
        frame_num += 1
        time_sec = frame_num / video_fps

        h_frame, w_frame = frame.shape[:2]
        display = frame.copy()

        # YOLO
        yolo_result = multi_person_detector.detect(frame)
        # Walking Aid
        aid_dets = walking_aid_detector.detect(frame)

        # 보행도구 표시
        for ad in aid_dets:
            ax1, ay1 = int(ad.bbox_xyxy[0]), int(ad.bbox_xyxy[1])
            ax2, ay2 = int(ad.bbox_xyxy[2]), int(ad.bbox_xyxy[3])
            cv2.rectangle(display, (ax1, ay1), (ax2, ay2), (0, 200, 255), 2)
            cv2.putText(display, f"{ad.class_name} {ad.confidence:.0%}",
                        (ax1, ay1 - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 200, 255), 1)

        should_save = (frame_num % args.interval == 0)  # 정기 캡처
        frame_persons = []

        for person in yolo_result.persons:
            person_id = f"person_{person.track_id}"
            bx1 = int(person.bbox[0] * w_frame)
            by1 = int(person.bbox[1] * h_frame)
            bx2 = int(person.bbox[2] * w_frame)
            by2 = int(person.bbox[3] * h_frame)

            # MediaPipe
            landmarks_result = pose_service.process_roi_sync(frame, person.bbox, person_id)
            if landmarks_result is None:
                cv2.rectangle(display, (bx1, by1), (bx2, by2), (128, 128, 128), 2)
                cv2.putText(display, f"ID:{person.track_id} NO POSE",
                            (bx1, by1 - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (128, 128, 128), 1)
                continue

            landmarks = landmarks_result.landmarks

            # 가시성
            key_indices = [0, 11, 12, 23, 24]
            avg_vis = sum(landmarks[i].get("visibility", 0) for i in key_indices) / len(key_indices)

            # 낙상 감지
            fall_result = fall_detector.detect(landmarks, person_id)
            state = fall_detector.get_or_create_state(person_id)

            is_fallen = fall_result["is_fallen"]
            rule_score = fall_result["rule_score"]
            ml_score = fall_result["ml_score"]
            confidence = fall_result["confidence"]
            fall_type = fall_result["fall_type"]
            posture = fall_result.get("posture", "unknown")
            conditions = fall_result["conditions"]

            # ML 버퍼
            try:
                ml_buf = fall_classifier._get_buffer(person_id)
                ml_buf_len = len(ml_buf)
            except:
                ml_buf_len = 0

            # ML raw
            try:
                ml_raw = fall_classifier.predict_detailed(person_id).fall_probability
            except:
                ml_raw = 0.0

            # 색상
            if is_fallen:
                color = (0, 0, 255)
            elif confidence >= 0.35:
                color = (0, 165, 255)
            elif confidence >= 0.2:
                color = (0, 255, 255)
            else:
                color = (0, 255, 0)

            cv2.rectangle(display, (bx1, by1), (bx2, by2), color, 2)

            # 랜드마크
            for lm in landmarks:
                lx, ly = int(lm["x"] * w_frame), int(lm["y"] * h_frame)
                vis = lm.get("visibility", 0)
                pt_color = (0, 255, 0) if vis > 0.5 else (0, 255, 255) if vis > 0.3 else (0, 0, 255)
                cv2.circle(display, (lx, ly), 3, pt_color, -1)

            # 텍스트
            y_text = by2 + 15
            lines = [
                f"ID:{person.track_id} [{posture}] vis={avg_vis:.2f}",
                f"Score:{confidence:.2f} (R={rule_score:.2f} ML={ml_score:.2f}) buf={ml_buf_len}/30",
            ]
            if is_fallen:
                lines.append(f"FALL! {fall_type} dur={fall_result['fall_duration']:.1f}s")

            for li, line in enumerate(lines):
                cv2.putText(display, line, (bx1, y_text + li * 16),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.4, color, 1)

            # score 변화 체크
            prev = prev_scores.get(person_id, 0.0)
            score_delta = abs(confidence - prev)
            prev_scores[person_id] = confidence

            # 저장 조건: 낙상 감지, score 급변 (0.15+), 전조(0.2+)
            if is_fallen or score_delta > 0.15 or (confidence >= 0.2 and prev < 0.2):
                should_save = True

            frame_persons.append({
                "person_id": person_id, "posture": posture,
                "score": confidence, "rule_score": rule_score,
                "ml_score": ml_score, "ml_raw": ml_raw, "ml_buf": ml_buf_len,
                "is_fallen": is_fallen, "fall_type": fall_type,
                "conditions": conditions, "visibility": avg_vis,
            })

        # 프레임 상단 정보
        info = f"F:{frame_num}/{total_frames} T:{time_sec:.1f}s P:{len(yolo_result.persons)} A:{len(aid_dets)}"
        cv2.putText(display, info, (10, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)

        # 저장
        saved_img = ""
        if should_save:
            img_name = f"f{frame_num:05d}_t{time_sec:.1f}s.jpg"
            cv2.imwrite(str(out_dir / img_name), display, [cv2.IMWRITE_JPEG_QUALITY, 85])
            saved_img = img_name
            saved_count += 1

        # CSV
        for p in frame_persons:
            c = p["conditions"]
            writer.writerow([
                frame_num, f"{time_sec:.2f}", p["person_id"], p["posture"],
                f"{p['score']:.3f}", f"{p['rule_score']:.3f}",
                f"{p['ml_score']:.3f}", f"{p['ml_raw']:.3f}", p["ml_buf"],
                p["is_fallen"], p["fall_type"],
                c["head_hip_inverted"], c["rapid_descent"], c["horizontal_body"],
                c["forward_slump"], c["lateral_tilt"], c["height_drop"],
                f"{p['visibility']:.2f}", saved_img,
            ])

        if frame_num % 100 == 0:
            print(f"  처리 중: {frame_num}/{total_frames} ({frame_num/total_frames*100:.0f}%) 저장={saved_count}장")

    csv_file.close()
    cap.release()
    print(f"\n완료! 총 {frame_num}프레임 처리, {saved_count}장 저장")
    print(f"  이미지: {out_dir}")
    print(f"  분석 CSV: {csv_path}")


if __name__ == "__main__":
    main()
