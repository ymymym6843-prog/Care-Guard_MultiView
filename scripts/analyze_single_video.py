"""
단일 영상 상세 분석
"""

import os
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

import cv2
from pathlib import Path


def analyze_video(video_path: str, max_frames: int = 600):
    from app.services.multi_person_detector import multi_person_detector
    from app.services.fall_detector import fall_detector
    from app.services.posture_classifier import posture_classifier

    # 상태 초기화
    fall_detector._person_states.clear()
    posture_classifier._person_states.clear()

    cap = cv2.VideoCapture(video_path)
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    print(f"\n{'='*60}")
    print(f"영상: {Path(video_path).name}")
    print(f"해상도: {w}x{h}, 총 프레임: {total}")
    print(f"{'='*60}")

    frame_count = 0
    sample_interval = 3
    max_conf = 0.0
    fall_frames = 0

    while frame_count < max_frames:
        ret, frame = cap.read()
        if not ret:
            break

        frame_count += 1
        if frame_count % sample_interval != 0:
            continue

        yolo_result = multi_person_detector.detect(frame)
        if not yolo_result.persons:
            continue

        for person in yolo_result.persons:
            if person.keypoints is None or len(person.keypoints) < 17:
                continue

            landmarks_list = []
            for kp_idx in range(17):
                kpt = person.keypoints[kp_idx]
                landmarks_list.append({
                    "x": float(kpt[0] / w),
                    "y": float(kpt[1] / h),
                    "z": 0.0,
                    "visibility": float(kpt[2]),
                })

            person_id = f"person_{person.track_id}"
            fall_result = fall_detector.detect(
                landmarks_list,
                person_id,
                keypoint_format="coco_17",
            )

            conf = fall_result["confidence"]
            is_fallen = fall_result["is_fallen"]
            posture = fall_result.get("posture", "unknown")

            if conf > max_conf:
                max_conf = conf

            # 중요 프레임 출력 (conf >= 0.4 또는 is_fallen)
            if conf >= 0.4 or is_fallen:
                status = "FALL!" if is_fallen else ""
                print(f"  프레임 {frame_count:4d}: {person_id:12s} | "
                      f"posture={posture:8s} | conf={conf:.3f} | "
                      f"rule={fall_result['rule_score']:.3f} | angle={fall_result['angle']:.1f}° {status}")

            if is_fallen:
                fall_frames += 1

    cap.release()

    print(f"\n{'='*60}")
    print(f"결과: max_conf={max_conf:.3f}, fall_frames={fall_frames}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    video = sys.argv[1] if len(sys.argv) > 1 else "demo_videos/BY_hospital_back_C5.mp4"
    analyze_video(video)
