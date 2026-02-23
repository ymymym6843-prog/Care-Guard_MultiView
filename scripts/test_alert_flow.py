"""
낙상 감지 + 알림 흐름 종합 테스트

데모 영상에서 fall_detector + alert_manager 전체 파이프라인을 테스트합니다.
WARNING/DANGER 전환 시간, 확률 기반 분리 등을 검증합니다.
"""

import os
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

import cv2
import time
from pathlib import Path
from collections import defaultdict


def test_alert_flow():
    """데모 영상에서 fall_detector + alert_manager 흐름 테스트"""
    from app.services.multi_person_detector import multi_person_detector
    from app.services.fall_detector import fall_detector
    from app.services.alert_manager import AlertManager, AlertState

    demo_dir = Path(__file__).parent.parent / "demo_videos"
    video_files = sorted(demo_dir.glob("*.mp4"))

    if not video_files:
        print(f"[ERROR] 데모 영상 없음: {demo_dir}")
        return

    print(f"\n{'='*70}")
    print("낙상 감지 + 알림 흐름 종합 테스트")
    print(f"{'='*70}")
    print(f"테스트 영상: {len(video_files)}개")
    print(f"DANGER 확신도 임계값: 0.70")
    print(f"{'='*70}\n")

    results = []

    for video_path in video_files:
        name = video_path.name
        is_fall_video = name.startswith(("BY_", "FY_", "SY_"))
        is_normal_video = name.startswith("N_")
        category = "FALL" if is_fall_video else "NORMAL" if is_normal_video else "OTHER"

        print(f"[{category}] {name}")

        # 매 영상마다 상태 초기화
        fall_detector.reset_all()
        am = AlertManager()

        cap = cv2.VideoCapture(str(video_path))
        if not cap.isOpened():
            print(f"  [ERROR] 영상 열기 실패\n")
            continue

        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        fps = cap.get(cv2.CAP_PROP_FPS)
        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        frame_duration = 1.0 / fps if fps > 0 else 0.033

        # 상태 순서 매핑 (문자열 비교 불가하므로 숫자로)
        STATE_ORDER = {
            AlertState.NORMAL: 0,
            AlertState.MONITORING: 1,
            AlertState.WARNING: 2,
            AlertState.DANGER: 3,
            AlertState.ACKNOWLEDGED: 4,
        }

        # 통계
        frame_count = 0
        sample_interval = 3
        max_confidence = 0.0
        max_state = AlertState.NORMAL
        max_state_order = 0
        warning_time = None
        danger_time = None
        first_fall_frame = None
        warning_to_danger_seconds = None

        while True:
            ret, frame = cap.read()
            if not ret:
                break

            frame_count += 1
            if frame_count % sample_interval != 0:
                continue

            # YOLO 감지
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
                    landmarks_list, person_id, keypoint_format="coco_17",
                )

                conf = fall_result["confidence"]
                is_fallen = fall_result["is_fallen"]
                fall_type = fall_result.get("fall_type", "unknown")
                fall_dur = fall_result.get("fall_duration", 0.0)

                if conf > max_confidence:
                    max_confidence = conf

                if is_fallen and first_fall_frame is None:
                    first_fall_frame = frame_count

                # alert_manager 업데이트
                alert_result = am.update(
                    person_id=person_id,
                    is_fallen=is_fallen,
                    confidence=conf,
                    fall_duration=fall_dur,
                    fall_type=fall_type,
                )

                cur_state = AlertState(alert_result["state"])

                if cur_state == AlertState.WARNING and warning_time is None:
                    warning_time = frame_count * frame_duration / sample_interval
                    # 실제 시간으로도 기록
                    warning_time = time.time()

                if cur_state == AlertState.DANGER and danger_time is None:
                    danger_time = time.time()

                cur_order = STATE_ORDER.get(cur_state, 0)
                if cur_order > max_state_order:
                    max_state_order = cur_order
                    max_state = cur_state

        cap.release()

        # 결과 계산
        w2d = None
        if warning_time and danger_time:
            w2d = danger_time - warning_time
            warning_to_danger_seconds = w2d

        expected_fall = is_fall_video
        detected = max_state in (AlertState.WARNING, AlertState.DANGER)
        reached_danger = max_state == AlertState.DANGER

        if expected_fall:
            if reached_danger:
                status = "OK (DANGER)"
            elif detected:
                status = "PARTIAL (WARNING only)"
            else:
                status = "MISS"
        else:
            if detected:
                status = "FP (False Positive)"
            else:
                status = "OK (No alert)"

        result = {
            "name": name,
            "category": category,
            "max_conf": max_confidence,
            "max_state": max_state.value,
            "first_fall_frame": first_fall_frame,
            "w2d": w2d,
            "status": status,
            "expected_fall": expected_fall,
            "detected": detected,
            "reached_danger": reached_danger,
        }
        results.append(result)

        w2d_str = f"{w2d:.2f}s" if w2d is not None else "-"
        print(f"  max_conf={max_confidence:.3f} | state={max_state.value:12s} | W→D={w2d_str:>6s} | {status}")

    # === 전체 요약 ===
    print(f"\n{'='*70}")
    print("전체 결과 요약")
    print(f"{'='*70}")

    fall_videos = [r for r in results if r["expected_fall"]]
    normal_videos = [r for r in results if r["category"] == "NORMAL"]
    other_videos = [r for r in results if r["category"] == "OTHER"]

    fall_detected = sum(1 for r in fall_videos if r["detected"])
    fall_danger = sum(1 for r in fall_videos if r["reached_danger"])
    normal_fp = sum(1 for r in normal_videos if r["detected"])

    print(f"\n[낙상 영상] {len(fall_videos)}개")
    print(f"  감지 (WARNING+): {fall_detected}/{len(fall_videos)} ({fall_detected/max(len(fall_videos),1)*100:.0f}%)")
    print(f"  DANGER 도달:     {fall_danger}/{len(fall_videos)} ({fall_danger/max(len(fall_videos),1)*100:.0f}%)")

    w2d_times = [r["w2d"] for r in fall_videos if r["w2d"] is not None]
    if w2d_times:
        print(f"  WARNING→DANGER 평균: {sum(w2d_times)/len(w2d_times):.2f}s (min={min(w2d_times):.2f}s, max={max(w2d_times):.2f}s)")

    print(f"\n[정상 영상] {len(normal_videos)}개")
    print(f"  오탐 (FP): {normal_fp}/{len(normal_videos)} ({normal_fp/max(len(normal_videos),1)*100:.0f}%)")

    if other_videos:
        other_fp = sum(1 for r in other_videos if r["detected"])
        print(f"\n[기타 영상] {len(other_videos)}개")
        print(f"  감지: {other_fp}/{len(other_videos)}")

    print(f"\n{'='*70}")
    print("상세 결과")
    print(f"{'='*70}")
    print(f"{'영상':<32s} | {'max_conf':>8s} | {'상태':>10s} | {'W→D':>6s} | 결과")
    print("-" * 80)
    for r in results:
        w2d_str = f"{r['w2d']:.2f}s" if r["w2d"] is not None else "-"
        print(f"  {r['name']:<30s} | {r['max_conf']:>8.3f} | {r['max_state']:>10s} | {w2d_str:>6s} | {r['status']}")
    print(f"{'='*70}\n")


if __name__ == "__main__":
    test_alert_flow()
