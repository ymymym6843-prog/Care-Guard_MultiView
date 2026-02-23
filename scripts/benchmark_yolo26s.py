"""
YOLO26s-pose 단독 벤치마크 (동일 222개 영상)

benchmark_model_comparison.py와 동일한 seed/영상으로
yolo26s-pose만 테스트합니다.
"""

import os
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

import cv2
import time
import random
import statistics
from pathlib import Path
from collections import defaultdict

MODEL_NAME = "yolo26s-pose.pt"
DEMO_DIR = Path("C:/Users/dbals/VibeCoding/Care-guard/demo_videos")
AIHUB_DIR = Path("D:/AIHub_Fall_Data/Validation/source/영상")
MODEL_DIR = Path("C:/Users/dbals/VibeCoding/Care-guard/backend/models")
NUM_PER_CATEGORY = 100


def collect_videos():
    videos = []
    if DEMO_DIR.exists():
        for f in sorted(DEMO_DIR.glob("*.mp4")):
            name = f.stem
            if name.startswith("BY"):
                cat = "BY"
            elif name.startswith("FY"):
                cat = "FY"
            elif name.startswith("SY"):
                cat = "SY"
            elif name.startswith("N"):
                cat = "N"
            else:
                continue
            is_fall = cat != "N"
            videos.append((f, cat, is_fall, "demo"))

    # AIHub 데이터셋 (세션 기반 샘플링 - comprehensive_benchmark와 동일)
    if AIHUB_DIR.exists():
        categories = {
            "BY": AIHUB_DIR / "Y" / "BY",
            "FY": AIHUB_DIR / "Y" / "FY",
            "SY": AIHUB_DIR / "Y" / "SY",
            "N": AIHUB_DIR / "N" / "N",
        }
        random.seed(42)  # 동일 seed
        for cat, path in categories.items():
            if path.exists():
                sessions = sorted([s for s in path.iterdir() if s.is_dir()])
                selected_sessions = random.sample(sessions, min(NUM_PER_CATEGORY, len(sessions)))
                is_fall = cat != "N"
                for session in selected_sessions:
                    mp4_files = list(session.glob("*.mp4"))
                    if mp4_files:
                        video = random.choice(mp4_files)
                        videos.append((video, cat, is_fall, "aihub"))
    return videos


def run_benchmark(model_name: str, videos: list) -> dict:
    import app.services.multi_person_detector as mpd
    mpd._YOLO_MODEL_NAME = model_name

    from app.services.multi_person_detector import multi_person_detector
    multi_person_detector._model = None
    multi_person_detector._initialized = False
    multi_person_detector._enabled = True

    from app.services.fall_detector import FallDetector
    from app.services.fall_classifier import fall_classifier

    multi_person_detector._ensure_model()
    fall_detector = FallDetector()

    results = {"TP": 0, "FP": 0, "FN": 0, "TN": 0, "times": [], "details": []}
    total = len(videos)

    for i, (video_path, cat, is_fall, source) in enumerate(videos):
        print(f"  [{i+1}/{total}] {video_path.name} ({cat}) ", end="", flush=True)

        cap = cv2.VideoCapture(str(video_path))
        if not cap.isOpened():
            print("SKIP (open failed)")
            continue

        fall_detector.reset_all()
        fall_classifier.reset_all()

        detected = False
        max_score = 0.0
        frame_times = []
        frame_count = 0
        sample_interval = 3

        while True:
            ret, frame = cap.read()
            if not ret:
                break
            frame_count += 1
            if frame_count % sample_interval != 0:
                continue

            frame = cv2.resize(frame, (640, 360))

            t0 = time.perf_counter()
            detection_result = multi_person_detector.detect(frame)
            t1 = time.perf_counter()
            frame_times.append((t1 - t0) * 1000)

            for person in detection_result.persons:
                person_id = person.track_id
                keypoints = person.keypoints
                if keypoints is None:
                    continue

                from app.services.keypoint_adapter import KeypointAdapter
                landmarks_33 = KeypointAdapter.coco_to_mediapipe_33(keypoints)

                result = fall_detector.detect(
                    landmarks_33,
                    person_id=f"person_{person_id}",
                )
                conf = result.get("confidence", 0)
                is_fallen = result.get("is_fallen", False)

                if conf > max_score:
                    max_score = conf
                if is_fallen:
                    detected = True

        cap.release()

        if is_fall and detected:
            results["TP"] += 1
            label = "TP"
        elif is_fall and not detected:
            results["FN"] += 1
            label = "FN"
        elif not is_fall and detected:
            results["FP"] += 1
            label = "FP"
        else:
            results["TN"] += 1
            label = "TN"

        avg_time = statistics.mean(frame_times) if frame_times else 0
        results["times"].extend(frame_times)
        results["details"].append({
            "name": video_path.name, "cat": cat, "source": source,
            "detected": detected, "max_score": max_score, "label": label,
            "avg_ms": avg_time,
        })

        print(f"-> {label} (score={max_score:.2f}, {avg_time:.0f}ms)")

    import torch
    del multi_person_detector._model
    multi_person_detector._model = None
    multi_person_detector._initialized = False
    torch.cuda.empty_cache()

    return results


def print_results(model_name: str, r: dict):
    tp, fp, fn, tn = r["TP"], r["FP"], r["FN"], r["TN"]
    total = tp + fp + fn + tn
    recall = tp / (tp + fn) * 100 if (tp + fn) > 0 else 0
    precision = tp / (tp + fp) * 100 if (tp + fp) > 0 else 0
    f1 = 2 * recall * precision / (recall + precision) if (recall + precision) > 0 else 0
    accuracy = (tp + tn) / total * 100 if total > 0 else 0
    avg_ms = statistics.mean(r["times"]) if r["times"] else 0

    print(f"\n{'='*60}")
    print(f"  {model_name}")
    print(f"{'='*60}")
    print(f"  Total: {total} | TP={tp} FP={fp} FN={fn} TN={tn}")
    print(f"  Recall:    {recall:.1f}%")
    print(f"  Precision: {precision:.1f}%")
    print(f"  F1 Score:  {f1:.1f}")
    print(f"  Accuracy:  {accuracy:.1f}%")
    print(f"  Avg Speed: {avg_ms:.1f}ms/frame")
    print(f"{'='*60}")

    cats = defaultdict(lambda: {"TP": 0, "FP": 0, "FN": 0, "TN": 0})
    for d in r["details"]:
        cats[d["cat"]][d["label"]] += 1

    for cat in ["BY", "FY", "SY", "N"]:
        if cat in cats:
            c = cats[cat]
            cat_total = sum(c.values())
            if cat == "N":
                correct = c["TN"]
                print(f"  {cat}: {correct}/{cat_total} correct ({c['FP']} FP)")
            else:
                correct = c["TP"]
                print(f"  {cat}: {correct}/{cat_total} detected ({c['FN']} FN)")


if __name__ == "__main__":
    print("=" * 60)
    print(f"  YOLO26s-pose 벤치마크 (동일 222개 영상)")
    print("=" * 60)

    model_path = MODEL_DIR / MODEL_NAME
    if not model_path.exists():
        print(f"모델 파일 없음: {model_path}")
        sys.exit(1)

    videos = collect_videos()
    print(f"\n총 영상: {len(videos)}개")
    print(f"  데모: {sum(1 for v in videos if v[3] == 'demo')}개")
    print(f"  AIHub: {sum(1 for v in videos if v[3] == 'aihub')}개")

    r = run_benchmark(MODEL_NAME, videos)
    print_results(MODEL_NAME, r)
