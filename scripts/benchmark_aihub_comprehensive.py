"""
AIHub 낙상 데이터셋 종합 벤치마크 스크립트

목적:
- 대규모 표본 (200+ 영상)으로 신뢰도 있는 정확도 측정
- A/B 비교: 규칙 4조건 vs 규칙 10조건 vs ML 앙상블
- 발표자료용 개발 과정 및 선택 근거 데이터 생성
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
from collections import defaultdict
from dataclasses import dataclass, asdict
from datetime import datetime


@dataclass
class VideoResult:
    """영상별 결과"""
    video_name: str
    category: str  # BY, FY, SY, N
    camera: str  # C1~C8
    total_frames: int
    processed_frames: int
    fall_detected_frames: int
    max_confidence: float
    avg_confidence: float
    ground_truth_fall: bool
    predicted_fall: bool
    correct: bool
    processing_time_ms: float
    config_name: str  # 설정 이름


@dataclass
class BenchmarkConfig:
    """벤치마크 설정"""
    name: str
    description: str
    rule_weight: float
    ml_weight: float
    enhanced_rules: bool


# A/B 비교 설정들 - 최적 조합 탐색용
BENCHMARK_CONFIGS = [
    # 규칙 단독
    BenchmarkConfig(
        name="rule_only",
        description="규칙 100% (ML 없음)",
        rule_weight=1.0,
        ml_weight=0.0,
        enhanced_rules=False,
    ),
    # ML 단독
    BenchmarkConfig(
        name="ml_only",
        description="ML 100% (규칙 없음)",
        rule_weight=0.0,
        ml_weight=1.0,
        enhanced_rules=False,
    ),
    # 앙상블 조합들
    BenchmarkConfig(
        name="ensemble_80_20",
        description="규칙 80% + ML 20%",
        rule_weight=0.8,
        ml_weight=0.2,
        enhanced_rules=False,
    ),
    BenchmarkConfig(
        name="ensemble_70_30",
        description="규칙 70% + ML 30%",
        rule_weight=0.7,
        ml_weight=0.3,
        enhanced_rules=False,
    ),
    BenchmarkConfig(
        name="ensemble_60_40",
        description="규칙 60% + ML 40%",
        rule_weight=0.6,
        ml_weight=0.4,
        enhanced_rules=False,
    ),
    BenchmarkConfig(
        name="ensemble_50_50",
        description="규칙 50% + ML 50%",
        rule_weight=0.5,
        ml_weight=0.5,
        enhanced_rules=False,
    ),
    BenchmarkConfig(
        name="ensemble_40_60",
        description="규칙 40% + ML 60%",
        rule_weight=0.4,
        ml_weight=0.6,
        enhanced_rules=False,
    ),
    BenchmarkConfig(
        name="ensemble_30_70",
        description="규칙 30% + ML 70%",
        rule_weight=0.3,
        ml_weight=0.7,
        enhanced_rules=False,
    ),
    BenchmarkConfig(
        name="ensemble_20_80",
        description="규칙 20% + ML 80%",
        rule_weight=0.2,
        ml_weight=0.8,
        enhanced_rules=False,
    ),
]


def get_all_videos(base_path: Path) -> dict[str, list[Path]]:
    """모든 영상 경로를 카테고리별로 수집"""
    categories = {
        "BY": base_path / "Y" / "BY",
        "FY": base_path / "Y" / "FY",
        "SY": base_path / "Y" / "SY",
        "N": base_path / "N" / "N",
    }

    all_videos = {}

    for cat_name, cat_path in categories.items():
        if not cat_path.exists():
            print(f"[WARN] 카테고리 없음: {cat_path}")
            continue

        videos = []
        for session in cat_path.iterdir():
            if session.is_dir():
                videos.extend(list(session.glob("*.mp4")))

        all_videos[cat_name] = videos
        print(f"  {cat_name}: {len(videos)} 영상")

    return all_videos


def sample_videos(all_videos: dict[str, list[Path]], num_per_category: int = 50) -> list[Path]:
    """카테고리별 균등 샘플링"""
    sampled = []

    for cat_name, videos in all_videos.items():
        n = min(num_per_category, len(videos))
        sampled.extend(random.sample(videos, n))
        print(f"  {cat_name}: {n}개 샘플링")

    random.shuffle(sampled)
    return sampled


def apply_config(config: BenchmarkConfig):
    """설정 적용"""
    from app.services.fall_detector import fall_detector
    from app.config import settings

    # 가중치 설정
    fall_detector.rule_weight = config.rule_weight
    fall_detector.ml_weight = config.ml_weight

    # 확장 규칙 설정 (settings 직접 수정)
    settings.FALL_ENHANCED_RULES_ENABLED = config.enhanced_rules

    print(f"  설정 적용: {config.name}")
    print(f"    Rule: {config.rule_weight}, ML: {config.ml_weight}, Enhanced: {config.enhanced_rules}")


def benchmark_single_video(video_path: Path, config: BenchmarkConfig) -> VideoResult:
    """단일 영상 벤치마크"""
    from app.services.multi_person_detector import multi_person_detector
    from app.services.fall_detector import fall_detector

    # 파일명 파싱
    parts = video_path.stem.split("_")
    if len(parts) >= 5:
        category = parts[3]
        camera = parts[4]
    else:
        category = "unknown"
        camera = "unknown"

    ground_truth_fall = category in ["BY", "FY", "SY"]

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        return None

    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    frame_count = 0
    fall_detected_frames = 0
    confidences = []
    sample_interval = 5

    start_time = time.time()

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        frame_count += 1
        if frame_count % sample_interval != 0:
            continue

        try:
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

                person_id = f"bench_{video_path.stem}_{person.track_id}"
                fall_result = fall_detector.detect(
                    landmarks_list,
                    person_id,
                    keypoint_format="coco_17",
                )

                conf = fall_result["confidence"]
                confidences.append(conf)

                if fall_result["is_fallen"]:
                    fall_detected_frames += 1
        except Exception as e:
            pass

    cap.release()
    processing_time = (time.time() - start_time) * 1000

    processed_frames = frame_count // sample_interval
    # Recall 실험: 1프레임만 감지해도 낙상 판정 (기존: 5% 이상)
    predicted_fall = fall_detected_frames >= 1
    correct = (predicted_fall == ground_truth_fall)

    avg_conf = sum(confidences) / len(confidences) if confidences else 0.0
    max_conf = max(confidences) if confidences else 0.0

    return VideoResult(
        video_name=video_path.name,
        category=category,
        camera=camera,
        total_frames=total_frames,
        processed_frames=processed_frames,
        fall_detected_frames=fall_detected_frames,
        max_confidence=max_conf,
        avg_confidence=avg_conf,
        ground_truth_fall=ground_truth_fall,
        predicted_fall=predicted_fall,
        correct=correct,
        processing_time_ms=processing_time,
        config_name=config.name,
    )


def calculate_metrics(results: list[VideoResult]) -> dict:
    """성능 지표 계산"""
    if not results:
        return {}

    # Confusion matrix
    tp = sum(1 for r in results if r.ground_truth_fall and r.predicted_fall)
    fn = sum(1 for r in results if r.ground_truth_fall and not r.predicted_fall)
    fp = sum(1 for r in results if not r.ground_truth_fall and r.predicted_fall)
    tn = sum(1 for r in results if not r.ground_truth_fall and not r.predicted_fall)

    # Metrics
    accuracy = (tp + tn) / len(results) * 100 if results else 0
    recall = tp / (tp + fn) * 100 if (tp + fn) > 0 else 0
    precision = tp / (tp + fp) * 100 if (tp + fp) > 0 else 0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0
    fnr = fn / (tp + fn) * 100 if (tp + fn) > 0 else 0  # False Negative Rate (미탐률)
    fpr = fp / (fp + tn) * 100 if (fp + tn) > 0 else 0  # False Positive Rate (오탐률)

    # 카테고리별 Recall
    cat_recall = {}
    for cat in ["BY", "FY", "SY"]:
        cat_results = [r for r in results if r.category == cat]
        if cat_results:
            cat_tp = sum(1 for r in cat_results if r.predicted_fall)
            cat_recall[cat] = cat_tp / len(cat_results) * 100

    # 처리 시간
    avg_time = sum(r.processing_time_ms for r in results) / len(results)

    return {
        "total_videos": len(results),
        "tp": tp, "fn": fn, "fp": fp, "tn": tn,
        "accuracy": round(accuracy, 2),
        "recall": round(recall, 2),
        "precision": round(precision, 2),
        "f1_score": round(f1, 2),
        "fnr": round(fnr, 2),
        "fpr": round(fpr, 2),
        "category_recall": cat_recall,
        "avg_processing_time_ms": round(avg_time, 2),
    }


def run_benchmark(videos: list[Path], config: BenchmarkConfig) -> tuple[list[VideoResult], dict]:
    """특정 설정으로 벤치마크 실행"""
    print(f"\n{'='*60}")
    print(f"설정: {config.name}")
    print(f"설명: {config.description}")
    print(f"{'='*60}")

    apply_config(config)

    results = []
    for i, video_path in enumerate(videos, 1):
        print(f"\r[{i}/{len(videos)}] {video_path.name[:40]}...", end="", flush=True)
        result = benchmark_single_video(video_path, config)
        if result:
            results.append(result)

    print()
    metrics = calculate_metrics(results)

    print(f"\n결과 요약:")
    print(f"  정확도: {metrics.get('accuracy', 0):.1f}%")
    print(f"  Recall: {metrics.get('recall', 0):.1f}% (미탐률: {metrics.get('fnr', 0):.1f}%)")
    print(f"  Precision: {metrics.get('precision', 0):.1f}% (오탐률: {metrics.get('fpr', 0):.1f}%)")
    print(f"  F1 Score: {metrics.get('f1_score', 0):.2f}")
    print(f"  TP={metrics.get('tp',0)} FN={metrics.get('fn',0)} FP={metrics.get('fp',0)} TN={metrics.get('tn',0)}")

    return results, metrics


def generate_ab_comparison_report(all_results: dict[str, tuple[list, dict]], output_path: Path):
    """A/B 비교 리포트 생성"""
    report = {
        "generated_at": datetime.now().isoformat(),
        "benchmark_type": "AIHub Validation Dataset",
        "configs": {},
    }

    for config_name, (results, metrics) in all_results.items():
        report["configs"][config_name] = {
            "metrics": metrics,
            "description": next(c.description for c in BENCHMARK_CONFIGS if c.name == config_name),
            "sample_errors": [
                asdict(r) for r in results[:5] if not r.correct
            ],
        }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    print(f"\n리포트 저장: {output_path}")


def print_comparison_table(all_results: dict[str, tuple[list, dict]]):
    """A/B 비교 테이블 출력"""
    print(f"\n{'='*80}")
    print("A/B 비교 결과 요약")
    print(f"{'='*80}")
    print(f"{'설정':<25} {'Recall':>8} {'Precision':>10} {'F1':>8} {'FNR':>8} {'FPR':>8}")
    print("-" * 80)

    for config_name, (results, metrics) in all_results.items():
        print(f"{config_name:<25} {metrics.get('recall',0):>7.1f}% {metrics.get('precision',0):>9.1f}% "
              f"{metrics.get('f1_score',0):>7.2f} {metrics.get('fnr',0):>7.1f}% {metrics.get('fpr',0):>7.1f}%")

    print("-" * 80)

    # 최적 설정 추천
    best_recall = max(all_results.items(), key=lambda x: x[1][1].get('recall', 0))
    best_f1 = max(all_results.items(), key=lambda x: x[1][1].get('f1_score', 0))

    print(f"\n추천:")
    print(f"  - 최고 Recall (미탐 최소화): {best_recall[0]} ({best_recall[1][1].get('recall',0):.1f}%)")
    print(f"  - 최고 F1 Score (균형): {best_f1[0]} ({best_f1[1][1].get('f1_score',0):.2f})")


def main():
    import argparse

    parser = argparse.ArgumentParser(description="AIHub 종합 벤치마크")
    parser.add_argument("--samples", type=int, default=30, help="카테고리당 샘플 수 (기본: 30)")
    parser.add_argument("--configs", type=str, default="all", help="테스트할 설정 (all/rule_4_only/rule_10_enhanced/...)")
    parser.add_argument("--output", type=str, default="benchmark_ab_comparison.json", help="결과 파일")
    args = parser.parse_args()

    aihub_path = Path("D:/AIHub_Fall_Data/Validation/source/영상")

    if not aihub_path.exists():
        print(f"[ERROR] AIHub 데이터 없음: {aihub_path}")
        return

    print(f"{'='*60}")
    print("AIHub 낙상 데이터셋 종합 벤치마크")
    print(f"{'='*60}")
    print(f"데이터 경로: {aihub_path}")
    print(f"카테고리당 샘플: {args.samples}개")

    # 영상 수집
    print("\n[1] 영상 수집")
    all_videos = get_all_videos(aihub_path)
    total_videos = sum(len(v) for v in all_videos.values())
    print(f"  총 {total_videos}개 영상 발견")

    # 샘플링
    print("\n[2] 샘플링")
    random.seed(42)
    sampled = sample_videos(all_videos, args.samples)
    print(f"  총 {len(sampled)}개 샘플링 완료")

    # 설정 선택
    if args.configs == "all":
        configs = BENCHMARK_CONFIGS
    else:
        configs = [c for c in BENCHMARK_CONFIGS if c.name in args.configs.split(",")]

    # 벤치마크 실행
    print("\n[3] 벤치마크 실행")
    all_results = {}

    for config in configs:
        results, metrics = run_benchmark(sampled, config)
        all_results[config.name] = (results, metrics)

        # 상태 리셋 (다음 설정을 위해)
        from app.services.fall_detector import fall_detector
        fall_detector._person_states.clear()

    # 비교 테이블 출력
    print_comparison_table(all_results)

    # 리포트 저장
    output_path = Path(args.output)
    generate_ab_comparison_report(all_results, output_path)

    print(f"\n완료!")


if __name__ == "__main__":
    main()
