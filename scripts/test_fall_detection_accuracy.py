"""
낙상 감지 정확도 테스트 스크립트

데모 영상들에서 낙상 감지가 정확히 작동하는지 확인합니다.
"""

import os
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

import cv2
import numpy as np
from pathlib import Path
from collections import defaultdict


def test_fall_detection_on_videos():
    """데모 영상들에서 낙상 감지 정확도 테스트"""
    # Import after path setup
    from app.services.multi_person_detector import multi_person_detector
    from app.services.fall_detector import fall_detector

    # 데모 영상 목록
    demo_dir = Path(__file__).parent.parent / "demo_videos"

    video_files = list(demo_dir.glob("*.mp4"))
    if not video_files:
        print(f"[ERROR] 데모 영상 없음: {demo_dir}")
        return

    print(f"\n{'='*60}")
    print("낙상 감지 정확도 테스트")
    print(f"{'='*60}")
    print(f"YOLO 활성화: {multi_person_detector.enabled}")
    print(f"테스트 영상: {len(video_files)}개")
    print(f"{'='*60}\n")

    results = {}

    for video_path in video_files:
        print(f"\n[테스트] {video_path.name}")
        print("-" * 40)

        cap = cv2.VideoCapture(str(video_path))
        if not cap.isOpened():
            print(f"  [ERROR] 영상 열기 실패")
            continue

        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        fps = cap.get(cv2.CAP_PROP_FPS)
        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

        print(f"  해상도: {w}x{h}, FPS: {fps:.1f}, 총 프레임: {total_frames}")

        # 통계
        frame_count = 0
        fall_detected_frames = 0
        max_confidence = 0.0
        person_falls = defaultdict(int)
        person_max_conf = defaultdict(float)

        # 샘플링 (성능을 위해 3프레임마다 처리)
        sample_interval = 3

        while True:
            ret, frame = cap.read()
            if not ret:
                break

            frame_count += 1
            if frame_count % sample_interval != 0:
                continue

            # YOLO로 인원 감지
            yolo_result = multi_person_detector.detect(frame)

            if not yolo_result.persons:
                continue

            for person in yolo_result.persons:
                if person.keypoints is None or len(person.keypoints) < 17:
                    continue

                # 키포인트를 list[dict] 형식으로 변환 (정규화된 좌표)
                landmarks_list = []
                for kp_idx in range(17):
                    kpt = person.keypoints[kp_idx]
                    landmarks_list.append({
                        "x": float(kpt[0] / w),
                        "y": float(kpt[1] / h),
                        "z": 0.0,
                        "visibility": float(kpt[2]),
                    })

                # 낙상 감지
                person_id = f"person_{person.track_id}"
                fall_result = fall_detector.detect(
                    landmarks_list,
                    person_id,
                    keypoint_format="coco_17",
                )

                conf = fall_result["confidence"]
                is_fallen = fall_result["is_fallen"]

                if conf > max_confidence:
                    max_confidence = conf

                if conf > person_max_conf[person_id]:
                    person_max_conf[person_id] = conf

                if is_fallen:
                    fall_detected_frames += 1
                    person_falls[person_id] += 1

                    # 낙상 감지 시 상세 정보 출력
                    print(f"  [FALL] 프레임 {frame_count}: {person_id} "
                          f"conf={conf:.2f}, angle={fall_result['angle']:.1f}°, "
                          f"rule={fall_result['rule_score']:.2f}, ml={fall_result['ml_score']:.2f}")

        cap.release()

        # 결과 요약
        processed_frames = frame_count // sample_interval
        fall_rate = fall_detected_frames / max(processed_frames, 1) * 100

        results[video_path.name] = {
            "total_frames": total_frames,
            "processed_frames": processed_frames,
            "fall_frames": fall_detected_frames,
            "fall_rate": fall_rate,
            "max_confidence": max_confidence,
            "person_falls": dict(person_falls),
            "person_max_conf": dict(person_max_conf),
        }

        print(f"\n  [결과] 처리: {processed_frames}프레임, 낙상감지: {fall_detected_frames}프레임 ({fall_rate:.1f}%)")
        print(f"  [결과] 최대 confidence: {max_confidence:.3f}")

        if person_falls:
            for pid, count in person_falls.items():
                print(f"  [결과] {pid}: 낙상 {count}프레임, 최대conf {person_max_conf[pid]:.3f}")
        else:
            print(f"  [결과] 낙상 감지 없음")

    # 전체 요약
    print(f"\n{'='*60}")
    print("전체 결과 요약")
    print(f"{'='*60}")

    for video_name, stats in results.items():
        status = "OK" if stats["fall_frames"] > 0 else "NO_DETECTION"
        print(f"  {video_name:30s} | max_conf={stats['max_confidence']:.3f} | "
              f"falls={stats['fall_frames']:3d}프레임 | {status}")

    print(f"{'='*60}\n")


if __name__ == "__main__":
    test_fall_detection_on_videos()
