"""
오탐 케이스 상세 분석 스크립트

낙상으로 오인되는 정상 영상의 프레임을 상세 분석합니다.
- 어떤 조건(C1, C2, C3, N1-N6)이 활성화되는지
- 자세 분류 상태
- 억제 로직 작동 여부
"""

import os
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

import cv2
from pathlib import Path
from collections import defaultdict


def analyze_video_detailed(video_path: Path, max_frames: int = 300):
    """영상의 낙상 감지 상세 분석"""
    from app.services.multi_person_detector import multi_person_detector
    from app.services.fall_detector import fall_detector
    from app.services.posture_classifier import posture_classifier

    print(f"\n{'='*70}")
    print(f"상세 분석: {video_path.name}")
    print(f"{'='*70}")

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        print(f"[ERROR] 영상 열기 실패")
        return

    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS)

    print(f"해상도: {w}x{h}, FPS: {fps:.1f}, 총 프레임: {total_frames}")
    print("-" * 70)

    # 통계
    frame_count = 0
    fall_detections = []
    condition_stats = defaultdict(int)
    posture_stats = defaultdict(int)

    # fall_detector 상태 초기화
    fall_detector._person_states.clear()
    posture_classifier._person_states.clear()

    sample_interval = 3

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

            # 낙상 감지
            fall_result = fall_detector.detect(
                landmarks_list,
                person_id,
                keypoint_format="coco_17",
            )

            # 자세 통계
            posture = fall_result.get("posture", "unknown")
            posture_stats[posture] += 1

            # 낙상 감지 시 상세 정보 수집
            if fall_result["is_fallen"]:
                conditions = fall_result.get("conditions", {})
                detection_info = {
                    "frame": frame_count,
                    "person_id": person_id,
                    "confidence": fall_result["confidence"],
                    "rule_score": fall_result["rule_score"],
                    "ml_score": fall_result["ml_score"],
                    "angle": fall_result["angle"],
                    "head_y": fall_result["head_y"],
                    "hip_y": fall_result["hip_y"],
                    "posture": posture,
                    "conditions": conditions,
                }
                fall_detections.append(detection_info)

                # 조건별 통계
                for cond, active in conditions.items():
                    if active:
                        condition_stats[cond] += 1

                print(f"  프레임 {frame_count:4d}: {person_id:12s} | "
                      f"posture={posture:8s} | conf={fall_result['confidence']:.2f} | "
                      f"rule={fall_result['rule_score']:.2f} | angle={fall_result['angle']:.1f}°")

    cap.release()

    # 결과 요약
    print("\n" + "=" * 70)
    print("분석 결과 요약")
    print("=" * 70)

    print(f"\n총 처리 프레임: {frame_count // sample_interval}")
    print(f"낙상 감지 프레임: {len(fall_detections)}")

    print(f"\n[자세 분포]")
    for posture, count in sorted(posture_stats.items(), key=lambda x: -x[1]):
        pct = count / sum(posture_stats.values()) * 100
        print(f"  {posture:10s}: {count:4d} ({pct:.1f}%)")

    if fall_detections:
        print(f"\n[활성화된 조건 통계]")
        for cond, count in sorted(condition_stats.items(), key=lambda x: -x[1]):
            print(f"  {cond:20s}: {count:4d}회")

        print(f"\n[낙상 감지 시 평균 점수]")
        avg_conf = sum(d["confidence"] for d in fall_detections) / len(fall_detections)
        avg_rule = sum(d["rule_score"] for d in fall_detections) / len(fall_detections)
        avg_angle = sum(d["angle"] for d in fall_detections) / len(fall_detections)
        print(f"  평균 confidence: {avg_conf:.3f}")
        print(f"  평균 rule_score: {avg_rule:.3f}")
        print(f"  평균 angle: {avg_angle:.1f}°")

    return fall_detections


def main():
    # 오탐이 발생하는 정상 영상들
    demo_dir = Path("C:/Users/dbals/VibeCoding/Care-guard/demo_videos")

    problematic_videos = [
        "N_hospital_normal_C5.mp4",  # 43프레임 오탐
        "N_normal_standing_03.mp4",  # 79프레임 오탐 (심각)
        "N_normal_sideview_01.mp4",  # 2프레임 오탐 (경미)
    ]

    # 미탐 케이스도 분석
    missed_videos = [
        "FY_front_fall_trip.mp4",  # 1프레임만 감지
    ]

    print("\n" + "=" * 70)
    print("오탐 케이스 상세 분석")
    print("=" * 70)

    for video_name in problematic_videos:
        video_path = demo_dir / video_name
        if video_path.exists():
            analyze_video_detailed(video_path)
        else:
            print(f"[SKIP] {video_name} 없음")

    print("\n" + "=" * 70)
    print("미탐 케이스 상세 분석")
    print("=" * 70)

    for video_name in missed_videos:
        video_path = demo_dir / video_name
        if video_path.exists():
            analyze_video_detailed(video_path)
        else:
            print(f"[SKIP] {video_name} 없음")


if __name__ == "__main__":
    main()
