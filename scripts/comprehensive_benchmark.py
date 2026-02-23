"""
종합 낙상 감지 벤치마크 스크립트

데모 영상(24개) + AIHub 데이터셋을 모두 테스트하여
미탐률(FNR), 오탐률(FPR), Recall, Precision, F1, Accuracy를 측정합니다.
"""

import os
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

import cv2
import json
import random
import time
from pathlib import Path
from datetime import datetime
from collections import defaultdict
from dataclasses import dataclass, asdict


@dataclass
class VideoResult:
    """영상별 결과"""
    video_name: str
    source: str  # "demo" or "aihub"
    category: str  # BY, FY, SY, N, tool
    total_frames: int
    processed_frames: int
    fall_detected_frames: int
    max_confidence: float
    max_rule_score: float
    max_ml_score: float
    ground_truth_fall: bool
    detected_as_fall: bool
    correct: bool
    fall_frame_details: list  # 낙상 감지된 프레임 상세 정보


def process_video(video_path: Path, multi_person_detector, fall_detector, sample_interval=3) -> dict:
    """단일 영상 처리"""
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        return None

    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = cap.get(cv2.CAP_PROP_FPS)
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    frame_count = 0
    fall_detected_frames = 0
    max_confidence = 0.0
    max_rule_score = 0.0
    max_ml_score = 0.0
    fall_frame_details = []

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

            # 키포인트를 list[dict] 형식으로 변환
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
            rule_s = fall_result["rule_score"]
            ml_s = fall_result["ml_score"]

            if conf > max_confidence:
                max_confidence = conf
            if rule_s > max_rule_score:
                max_rule_score = rule_s
            if ml_s > max_ml_score:
                max_ml_score = ml_s

            if is_fallen:
                fall_detected_frames += 1
                if len(fall_frame_details) < 10:  # 최대 10개만 기록
                    fall_frame_details.append({
                        "frame": frame_count,
                        "person_id": person_id,
                        "confidence": conf,
                        "rule_score": rule_s,
                        "ml_score": ml_s,
                        "angle": fall_result["angle"],
                        "posture": fall_result.get("posture", "unknown"),
                    })

    cap.release()

    processed_frames = frame_count // sample_interval
    return {
        "total_frames": total_frames,
        "fps": fps,
        "resolution": f"{w}x{h}",
        "processed_frames": processed_frames,
        "fall_detected_frames": fall_detected_frames,
        "max_confidence": max_confidence,
        "max_rule_score": max_rule_score,
        "max_ml_score": max_ml_score,
        "fall_frame_details": fall_frame_details,
    }


def get_demo_ground_truth(filename: str) -> tuple[str, bool]:
    """데모 영상의 Ground Truth 판정"""
    name = filename.upper()
    if name.startswith("BY_") or name.startswith("BY"):
        return "BY", True
    elif name.startswith("FY_") or name.startswith("FY"):
        return "FY", True
    elif name.startswith("SY_") or name.startswith("SY"):
        return "SY", True
    elif name.startswith("N_") or name.startswith("N"):
        return "N", False
    elif "CRUTCH" in name or "WHEELCHAIR" in name:
        return "tool", False
    return "unknown", False


def get_aihub_ground_truth(video_path: Path) -> tuple[str, str]:
    """AIHub 영상의 카테고리와 카메라 추출"""
    parts = video_path.stem.split("_")
    if len(parts) >= 5:
        category = parts[3]
        camera = parts[4]
    else:
        category = "unknown"
        camera = "unknown"
    return category, camera


def run_benchmark():
    from app.services.multi_person_detector import multi_person_detector
    from app.services.fall_detector import fall_detector
    from app.services.posture_classifier import posture_classifier

    print("=" * 70)
    print("SENTIO 종합 낙상 감지 벤치마크")
    print("=" * 70)
    print(f"YOLO 모델 활성화: {multi_person_detector.enabled}")
    print(f"ML 모델 활성화: {fall_detector._ml_weight > 0}")
    print(f"앙상블 가중치: rule={fall_detector._rule_weight:.2f}, ml={fall_detector._ml_weight:.2f}")
    print(f"확장 규칙(N1-N6): {fall_detector._enhanced_rules}")
    print(f"복합 임계값: {fall_detector._composite_threshold}")
    print("=" * 70)

    all_results = []

    # ═══════════════════════════════════════════════════════
    # PART 1: 데모 영상 테스트 (24개)
    # ═══════════════════════════════════════════════════════
    demo_dir = Path(__file__).parent.parent / "demo_videos"
    demo_videos = sorted(demo_dir.glob("*.mp4"))

    print(f"\n{'─'*70}")
    print(f"[PART 1] 데모 영상 테스트 ({len(demo_videos)}개)")
    print(f"{'─'*70}")

    for i, video_path in enumerate(demo_videos):
        category, ground_truth_fall = get_demo_ground_truth(video_path.name)

        # 각 영상마다 상태 초기화 (영상 간 간섭 방지)
        fall_detector.reset_all()
        posture_classifier._person_states.clear()

        print(f"\n  [{i+1}/{len(demo_videos)}] {video_path.name} (GT: {'낙상' if ground_truth_fall else '정상'})")

        result_data = process_video(video_path, multi_person_detector, fall_detector)
        if result_data is None:
            print(f"    [ERROR] 영상 열기 실패")
            continue

        # 낙상 판정: 1프레임이라도 낙상 감지되면 낙상으로 판정
        detected_as_fall = result_data["fall_detected_frames"] >= 1
        correct = (detected_as_fall == ground_truth_fall)

        video_result = VideoResult(
            video_name=video_path.name,
            source="demo",
            category=category,
            total_frames=result_data["total_frames"],
            processed_frames=result_data["processed_frames"],
            fall_detected_frames=result_data["fall_detected_frames"],
            max_confidence=result_data["max_confidence"],
            max_rule_score=result_data["max_rule_score"],
            max_ml_score=result_data["max_ml_score"],
            ground_truth_fall=ground_truth_fall,
            detected_as_fall=detected_as_fall,
            correct=correct,
            fall_frame_details=result_data["fall_frame_details"],
        )
        all_results.append(video_result)

        status = "OK" if correct else ("MISS" if ground_truth_fall else "FALSE_ALARM")
        emoji = "  " if correct else ">>"
        print(f"  {emoji} 결과: {status} | 낙상프레임={result_data['fall_detected_frames']}/{result_data['processed_frames']} | "
              f"max_conf={result_data['max_confidence']:.3f} rule={result_data['max_rule_score']:.3f} ml={result_data['max_ml_score']:.3f}")

        if not correct:
            for detail in result_data["fall_frame_details"][:3]:
                print(f"     -> 프레임{detail['frame']}: {detail['person_id']} conf={detail['confidence']:.3f} "
                      f"rule={detail['rule_score']:.3f} ml={detail['ml_score']:.3f} "
                      f"angle={detail['angle']:.1f}° posture={detail['posture']}")

    # ═══════════════════════════════════════════════════════
    # PART 2: AIHub 데이터셋 테스트
    # ═══════════════════════════════════════════════════════
    aihub_path = Path("D:/AIHub_Fall_Data/Validation/source/영상")

    if aihub_path.exists():
        # 카테고리별 샘플 수 (CLI 인자 또는 기본 50개)
        random.seed(42)
        import builtins
        num_per_category = getattr(builtins, '_BENCHMARK_NUM_PER_CATEGORY', 50)

        categories = {
            "BY": aihub_path / "Y" / "BY",
            "FY": aihub_path / "Y" / "FY",
            "SY": aihub_path / "Y" / "SY",
            "N": aihub_path / "N" / "N",
        }

        aihub_videos = []
        for cat_name, cat_path in categories.items():
            if not cat_path.exists():
                continue
            sessions = [s for s in cat_path.iterdir() if s.is_dir()]
            if num_per_category == 0 or num_per_category >= len(sessions):
                selected = sessions  # 전체 사용
            else:
                selected = random.sample(sessions, num_per_category)
            for session in selected:
                mp4_files = list(session.glob("*.mp4"))
                if mp4_files:
                    aihub_videos.append((cat_name, random.choice(mp4_files)))

        print(f"\n{'─'*70}")
        print(f"[PART 2] AIHub 데이터셋 테스트 ({len(aihub_videos)}개, 카테고리별 {num_per_category}개)")
        print(f"{'─'*70}")

        for i, (cat_name, video_path) in enumerate(aihub_videos):
            ground_truth_fall = cat_name in ["BY", "FY", "SY"]
            _, camera = get_aihub_ground_truth(video_path)

            # 상태 초기화
            fall_detector.reset_all()
            posture_classifier._person_states.clear()

            print(f"\n  [{i+1}/{len(aihub_videos)}] {video_path.name} ({cat_name}/{camera}) "
                  f"(GT: {'낙상' if ground_truth_fall else '정상'})")

            # AIHub은 5프레임 간격 (성능 이유)
            result_data = process_video(video_path, multi_person_detector, fall_detector, sample_interval=5)
            if result_data is None:
                print(f"    [ERROR] 영상 열기 실패")
                continue

            # AIHub 판정: 1프레임이라도 낙상 감지되면 낙상으로 판정 (실제 운영과 동일)
            fall_pct = result_data["fall_detected_frames"] / max(result_data["processed_frames"], 1) * 100
            detected_as_fall = result_data["fall_detected_frames"] >= 1
            correct = (detected_as_fall == ground_truth_fall)

            video_result = VideoResult(
                video_name=video_path.name,
                source="aihub",
                category=cat_name,
                total_frames=result_data["total_frames"],
                processed_frames=result_data["processed_frames"],
                fall_detected_frames=result_data["fall_detected_frames"],
                max_confidence=result_data["max_confidence"],
                max_rule_score=result_data["max_rule_score"],
                max_ml_score=result_data["max_ml_score"],
                ground_truth_fall=ground_truth_fall,
                detected_as_fall=detected_as_fall,
                correct=correct,
                fall_frame_details=result_data["fall_frame_details"],
            )
            all_results.append(video_result)

            status = "OK" if correct else ("MISS" if ground_truth_fall else "FALSE_ALARM")
            emoji = "  " if correct else ">>"
            print(f"  {emoji} 결과: {status} | 낙상프레임={result_data['fall_detected_frames']}/{result_data['processed_frames']} ({fall_pct:.1f}%) | "
                  f"max_conf={result_data['max_confidence']:.3f} rule={result_data['max_rule_score']:.3f} ml={result_data['max_ml_score']:.3f}")

            if not correct:
                for detail in result_data["fall_frame_details"][:3]:
                    print(f"     -> 프레임{detail['frame']}: {detail['person_id']} conf={detail['confidence']:.3f} "
                          f"rule={detail['rule_score']:.3f} ml={detail['ml_score']:.3f} "
                          f"angle={detail['angle']:.1f}° posture={detail['posture']}")
    else:
        print(f"\n[WARN] AIHub 데이터 경로 없음: {aihub_path}")

    # ═══════════════════════════════════════════════════════
    # 종합 결과 출력 + JSON 저장
    # ═══════════════════════════════════════════════════════
    print_comprehensive_results(all_results)
    save_results_json(all_results)


def print_comprehensive_results(results: list[VideoResult]):
    """종합 결과 출력"""
    print(f"\n{'='*70}")
    print("종합 벤치마크 결과")
    print(f"{'='*70}")

    # ── 소스별 분리 ──
    for source_name, source_label in [("demo", "데모 영상"), ("aihub", "AIHub 데이터셋")]:
        source_results = [r for r in results if r.source == source_name]
        if not source_results:
            continue

        print(f"\n{'─'*70}")
        print(f"  [{source_label}] ({len(source_results)}개 영상)")
        print(f"{'─'*70}")

        # 카테고리별 통계
        cat_stats = defaultdict(lambda: {"total": 0, "correct": 0, "tp": 0, "fp": 0, "fn": 0, "tn": 0})

        for r in source_results:
            cat = r.category
            cat_stats[cat]["total"] += 1
            if r.correct:
                cat_stats[cat]["correct"] += 1
            if r.ground_truth_fall and r.detected_as_fall:
                cat_stats[cat]["tp"] += 1
            elif r.ground_truth_fall and not r.detected_as_fall:
                cat_stats[cat]["fn"] += 1
            elif not r.ground_truth_fall and r.detected_as_fall:
                cat_stats[cat]["fp"] += 1
            else:
                cat_stats[cat]["tn"] += 1

        print("\n  [카테고리별 정확도]")
        for cat in ["BY", "FY", "SY", "N", "tool"]:
            s = cat_stats.get(cat)
            if s and s["total"] > 0:
                acc = s["correct"] / s["total"] * 100
                print(f"    {cat:5s}: {s['correct']:2d}/{s['total']:2d} ({acc:5.1f}%) "
                      f"| TP={s['tp']} FP={s['fp']} FN={s['fn']} TN={s['tn']}")

        # 전체 TP/FP/FN/TN
        tp = sum(s["tp"] for s in cat_stats.values())
        fp = sum(s["fp"] for s in cat_stats.values())
        fn = sum(s["fn"] for s in cat_stats.values())
        tn = sum(s["tn"] for s in cat_stats.values())

        total = tp + fp + fn + tn
        if total > 0:
            accuracy = (tp + tn) / total * 100
            recall = tp / (tp + fn) * 100 if (tp + fn) > 0 else 0
            precision = tp / (tp + fp) * 100 if (tp + fp) > 0 else 0
            f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0
            fnr = fn / (tp + fn) * 100 if (tp + fn) > 0 else 0  # 미탐률
            fpr = fp / (fp + tn) * 100 if (fp + tn) > 0 else 0  # 오탐률

            print(f"\n  [혼동 행렬]")
            print(f"    TP (실제 낙상 + 감지 O): {tp:3d}")
            print(f"    FN (실제 낙상 + 감지 X): {fn:3d}  <- 미탐 (환자 놓침)")
            print(f"    FP (정상 + 감지 O):      {fp:3d}  <- 오탐 (오경보)")
            print(f"    TN (정상 + 감지 X):      {tn:3d}")

            print(f"\n  [성능 지표]")
            print(f"    Accuracy (정확도):   {accuracy:6.1f}%")
            print(f"    Recall (재현율):     {recall:6.1f}%  (낙상 중 감지 비율)")
            print(f"    Precision (정밀도):  {precision:6.1f}%  (감지 중 실제 낙상 비율)")
            print(f"    F1 Score:            {f1:6.1f}")
            print(f"    FNR (미탐률):        {fnr:6.1f}%  (놓친 낙상 비율)")
            print(f"    FPR (오탐률):        {fpr:6.1f}%  (잘못된 경보 비율)")

    # ── 전체 통합 결과 ──
    print(f"\n{'='*70}")
    print("  [전체 통합 결과]")
    print(f"{'='*70}")

    tp = sum(1 for r in results if r.ground_truth_fall and r.detected_as_fall)
    fn = sum(1 for r in results if r.ground_truth_fall and not r.detected_as_fall)
    fp = sum(1 for r in results if not r.ground_truth_fall and r.detected_as_fall)
    tn = sum(1 for r in results if not r.ground_truth_fall and not r.detected_as_fall)

    total = tp + fp + fn + tn
    if total > 0:
        accuracy = (tp + tn) / total * 100
        recall = tp / (tp + fn) * 100 if (tp + fn) > 0 else 0
        precision = tp / (tp + fp) * 100 if (tp + fp) > 0 else 0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0
        fnr = fn / (tp + fn) * 100 if (tp + fn) > 0 else 0
        fpr = fp / (fp + tn) * 100 if (fp + tn) > 0 else 0

        print(f"\n  총 영상: {total}개 (낙상: {tp+fn}개, 정상: {fp+tn}개)")
        print(f"\n  TP={tp}, FP={fp}, FN={fn}, TN={tn}")
        print(f"\n  Accuracy:   {accuracy:6.1f}%")
        print(f"  Recall:     {recall:6.1f}%")
        print(f"  Precision:  {precision:6.1f}%")
        print(f"  F1 Score:   {f1:6.1f}")
        print(f"  FNR (미탐): {fnr:6.1f}%")
        print(f"  FPR (오탐): {fpr:6.1f}%")

    # ── 오류 케이스 상세 ──
    errors = [r for r in results if not r.correct]
    if errors:
        print(f"\n{'─'*70}")
        print(f"  [오류 케이스 상세] ({len(errors)}개)")
        print(f"{'─'*70}")

        fp_errors = [r for r in errors if not r.ground_truth_fall and r.detected_as_fall]
        fn_errors = [r for r in errors if r.ground_truth_fall and not r.detected_as_fall]

        if fp_errors:
            print(f"\n  ** 오탐 (False Positive) - 정상인데 낙상으로 감지 ({len(fp_errors)}개) **")
            for r in fp_errors:
                print(f"    - [{r.source}] {r.video_name} ({r.category})")
                print(f"      낙상프레임={r.fall_detected_frames}/{r.processed_frames} "
                      f"max_conf={r.max_confidence:.3f} rule={r.max_rule_score:.3f} ml={r.max_ml_score:.3f}")
                for detail in r.fall_frame_details[:3]:
                    print(f"        frame={detail['frame']}: conf={detail['confidence']:.3f} "
                          f"rule={detail['rule_score']:.3f} ml={detail['ml_score']:.3f} "
                          f"angle={detail['angle']:.1f}° posture={detail['posture']}")

        if fn_errors:
            print(f"\n  ** 미탐 (False Negative) - 낙상인데 감지 못함 ({len(fn_errors)}개) **")
            for r in fn_errors:
                print(f"    - [{r.source}] {r.video_name} ({r.category})")
                print(f"      max_conf={r.max_confidence:.3f} rule={r.max_rule_score:.3f} ml={r.max_ml_score:.3f}")
    else:
        print(f"\n  오류 케이스 없음!")

    print(f"\n{'='*70}")


def save_results_json(results: list[VideoResult]):
    """벤치마크 결과를 JSON 파일로 저장"""
    results_dir = Path(__file__).parent / "benchmark_results"
    results_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filepath = results_dir / f"benchmark_{timestamp}.json"

    # 통계 계산
    tp = sum(1 for r in results if r.ground_truth_fall and r.detected_as_fall)
    fn = sum(1 for r in results if r.ground_truth_fall and not r.detected_as_fall)
    fp = sum(1 for r in results if not r.ground_truth_fall and r.detected_as_fall)
    tn = sum(1 for r in results if not r.ground_truth_fall and not r.detected_as_fall)
    total = tp + fp + fn + tn
    recall = tp / (tp + fn) * 100 if (tp + fn) > 0 else 0
    precision = tp / (tp + fp) * 100 if (tp + fp) > 0 else 0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0

    # FN/FP 상세 분류
    fn_list = [asdict(r) for r in results if r.ground_truth_fall and not r.detected_as_fall]
    fp_list = [asdict(r) for r in results if not r.ground_truth_fall and r.detected_as_fall]

    save_data = {
        "timestamp": timestamp,
        "total_videos": total,
        "stats": {
            "tp": tp, "fp": fp, "fn": fn, "tn": tn,
            "recall": round(recall, 1),
            "precision": round(precision, 1),
            "f1": round(f1, 1),
        },
        "fn_details": fn_list,
        "fp_details": fp_list,
        "all_results": [asdict(r) for r in results],
    }

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(save_data, f, ensure_ascii=False, indent=2)

    print(f"\n  결과 저장: {filepath}")
    print(f"  FN {len(fn_list)}개, FP {len(fp_list)}개 상세 포함")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="SENTIO 종합 벤치마크")
    parser.add_argument("--num-per-category", "-n", type=int, default=100,
                        help="AIHub 카테고리별 샘플 수 (기본 100, 0=전체)")
    args = parser.parse_args()

    # 런타임에 샘플 수 오버라이드
    import builtins
    builtins._BENCHMARK_NUM_PER_CATEGORY = args.num_per_category

    start_time = time.time()
    run_benchmark()
    elapsed = time.time() - start_time
    print(f"\n총 소요 시간: {elapsed:.1f}초 ({elapsed/60:.1f}분)")
