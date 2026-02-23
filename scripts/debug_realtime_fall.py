"""
실시간 낙상 감지 진단 스크립트

웹캠으로 실시간 감지 상태를 화면에 표시합니다:
- YOLO 인원 감지 (바운딩 박스 + track_id)
- MediaPipe 33점 랜드마크 (가시성 표시)
- 규칙 기반 + ML 낙상 점수 (각 조건 ON/OFF)
- 보행도구 감지 결과

사용법:
  python scripts/debug_realtime_fall.py              # 웹캠 0번
  python scripts/debug_realtime_fall.py --source 1   # 웹캠 1번
  python scripts/debug_realtime_fall.py --source video.mp4  # 영상 파일
"""

import os
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

import argparse
import sys
import time
from pathlib import Path

import cv2
import numpy as np

# backend를 import path에 추가
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.config import settings


def main():
    parser = argparse.ArgumentParser(description="실시간 낙상 감지 진단")
    parser.add_argument("--source", default="0", help="카메라 인덱스 또는 영상 파일 경로")
    parser.add_argument("--width", type=int, default=1280, help="표시 해상도 너비")
    args = parser.parse_args()

    # 소스 결정
    source = int(args.source) if args.source.isdigit() else args.source

    cap = cv2.VideoCapture(source)
    if not cap.isOpened():
        print(f"ERROR: 소스를 열 수 없습니다: {source}")
        return

    # 웹캠이면 해상도 설정
    if isinstance(source, int):
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)

    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    print(f"소스: {source} ({w}x{h})")

    # --- 모델 초기화 ---
    print("모델 로딩 중...")

    # YOLO (인원 감지)
    from app.services.multi_person_detector import multi_person_detector
    # Walking Aid YOLO
    from app.services.walking_aid_detector import walking_aid_detector
    # MediaPipe
    from app.services.pose_service import pose_service
    # Fall Detector
    from app.services.fall_detector import fall_detector
    from app.services.fall_classifier import fall_classifier
    from app.services.posture_classifier import posture_classifier

    print(f"  YOLO person: {'ON' if multi_person_detector.enabled else 'OFF'}")
    print(f"  Walking aid: {'ON' if walking_aid_detector.enabled else 'OFF'}")
    print(f"  ML classifier: {'ON' if fall_classifier.enabled else 'OFF'} (output_dim={fall_classifier.output_dim})")
    print(f"  설정: visibility>={settings.FALL_MIN_VISIBILITY}, grace={settings.FALL_GRACE_FRAMES}f, "
          f"composite_th={settings.FALL_COMPOSITE_THRESHOLD}, consecutive={settings.FALL_CONSECUTIVE_FRAMES}f")
    print()
    print("키 조작:")
    print("  q: 종료")
    print("  r: 낙상 상태 리셋")
    print("  v: 가시성 임계값 ±0.1 토글")
    print()

    frame_num = 0
    fps_timer = time.time()
    fps_count = 0
    display_fps = 0.0

    while True:
        ret, frame = cap.read()
        if not ret:
            if not isinstance(source, int):
                cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                continue
            break

        frame_num += 1
        fps_count += 1
        now = time.time()
        if now - fps_timer >= 1.0:
            display_fps = fps_count / (now - fps_timer)
            fps_count = 0
            fps_timer = now

        h_frame, w_frame = frame.shape[:2]

        # 표시용 프레임 복사
        display = frame.copy()

        # 1. YOLO 인원 감지
        yolo_result = multi_person_detector.detect(frame)
        # 2. Walking Aid 감지
        aid_dets = walking_aid_detector.detect(frame)

        # 좌상단: 기본 정보
        info_lines = [
            f"FPS: {display_fps:.1f} | Frame: {frame_num} | Res: {w_frame}x{h_frame}",
            f"Persons: {len(yolo_result.persons)} | Aids: {len(aid_dets)}",
        ]

        # 보행도구 바운딩 박스
        for ad in aid_dets:
            ax1 = int(ad.bbox_xyxy[0])
            ay1 = int(ad.bbox_xyxy[1])
            ax2 = int(ad.bbox_xyxy[2])
            ay2 = int(ad.bbox_xyxy[3])
            cv2.rectangle(display, (ax1, ay1), (ax2, ay2), (0, 200, 255), 2)
            cv2.putText(display, f"{ad.class_name} {ad.confidence:.0%}",
                        (ax1, ay1 - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 200, 255), 1)

        # 각 인원별 처리
        person_infos = []
        for idx, person in enumerate(yolo_result.persons):
            person_id = f"person_{person.track_id}"

            # YOLO 바운딩 박스
            bx1 = int(person.bbox[0] * w_frame)
            by1 = int(person.bbox[1] * h_frame)
            bx2 = int(person.bbox[2] * w_frame)
            by2 = int(person.bbox[3] * h_frame)

            # MediaPipe ROI 분석
            landmarks_result = pose_service.process_roi_sync(frame, person.bbox, person_id)

            if landmarks_result is None:
                cv2.rectangle(display, (bx1, by1), (bx2, by2), (128, 128, 128), 2)
                cv2.putText(display, f"ID:{person.track_id} NO POSE",
                            (bx1, by1 - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (128, 128, 128), 1)
                person_infos.append(f"ID:{person.track_id} — NO POSE")
                continue

            landmarks = landmarks_result.landmarks

            # 가시성 체크
            key_indices = [0, 11, 12, 23, 24]  # nose, shoulders, hips
            avg_vis = sum(landmarks[i].get("visibility", 0) for i in key_indices) / len(key_indices)

            ankle_indices = [27, 28]
            avg_ankle_vis = sum(landmarks[i].get("visibility", 0) for i in ankle_indices) / len(ankle_indices)

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

            # ML 버퍼 상태
            ml_buf = fall_classifier._get_buffer(person_id)
            ml_buf_len = len(ml_buf)
            ml_ready = ml_buf_len >= 30

            # 색상 결정 (전조 → 주의 → 낙상)
            if is_fallen:
                color = (0, 0, 255)  # 빨강 (낙상 확정)
            elif confidence >= 0.35:
                color = (0, 165, 255)  # 주황 (주의)
            elif confidence >= 0.2:
                color = (0, 255, 255)  # 노랑 (전조)
            else:
                color = (0, 255, 0)  # 초록 (정상)

            # 바운딩 박스
            cv2.rectangle(display, (bx1, by1), (bx2, by2), color, 2)

            # 랜드마크 그리기 (가시성에 따라 색상)
            for i, lm in enumerate(landmarks):
                lx = int(lm["x"] * w_frame)
                ly = int(lm["y"] * h_frame)
                vis = lm.get("visibility", 0)
                if vis > 0.5:
                    pt_color = (0, 255, 0)  # 잘 보임
                elif vis > 0.3:
                    pt_color = (0, 255, 255)  # 보통
                else:
                    pt_color = (0, 0, 255)  # 안 보임
                cv2.circle(display, (lx, ly), 3, pt_color, -1)

            # 인원 정보 텍스트 (바운딩 박스 아래)
            y_text = by2 + 15
            lines = [
                f"ID:{person.track_id} [{posture}] vis={avg_vis:.2f} ankle={avg_ankle_vis:.2f}",
                f"Score: {confidence:.2f} (rule={rule_score:.2f} ml={ml_score:.2f})",
                f"Conds: inv={'O' if conditions['head_hip_inverted'] else 'X'} "
                f"desc={'O' if conditions['rapid_descent'] else 'X'} "
                f"horiz={'O' if conditions['horizontal_body'] else 'X'}",
                f"ML: {'READY' if ml_ready else f'buf={ml_buf_len}/30'} "
                f"grace={state.frames_since_first_seen}/{settings.FALL_GRACE_FRAMES} "
                f"consec={state.consecutive_fall_frames}",
            ]
            if is_fallen:
                lines.append(f"*** FALL! type={fall_type} dur={fall_result['fall_duration']:.1f}s ***")
            elif state.is_fallen and posture == "lying":
                lines.append(f"*** FALLEN ON GROUND (maintained) ***")

            for li, line in enumerate(lines):
                cv2.putText(display, line, (bx1, y_text + li * 16),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.4, color, 1)

            # 인물 요약
            status = "FALL!" if is_fallen else "OK"
            person_infos.append(
                f"ID:{person.track_id} [{posture}] vis={avg_vis:.2f} "
                f"score={confidence:.2f}(R={rule_score:.2f}/ML={ml_score:.2f}) "
                f"buf={ml_buf_len}/30 {status}"
            )

        # 좌상단 정보 패널
        panel_lines = info_lines + ["---"] + person_infos
        for i, line in enumerate(panel_lines):
            cv2.putText(display, line, (10, 20 + i * 18),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1,
                        lineType=cv2.LINE_AA)

        # 표시
        if display.shape[1] > args.width:
            scale = args.width / display.shape[1]
            display = cv2.resize(display, (args.width, int(display.shape[0] * scale)))

        cv2.imshow("SENTIO Fall Detection Debug", display)

        key = cv2.waitKey(1) & 0xFF
        if key == ord('q'):
            break
        elif key == ord('r'):
            fall_detector.reset_all()
            fall_classifier.reset_all()
            posture_classifier.reset_all()
            print("[리셋] 모든 낙상 상태 초기화")
        elif key == ord('v'):
            old = settings.FALL_MIN_VISIBILITY
            settings.FALL_MIN_VISIBILITY = 0.3 if old >= 0.5 else 0.5
            print(f"[가시성] {old:.1f} → {settings.FALL_MIN_VISIBILITY:.1f}")

    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
