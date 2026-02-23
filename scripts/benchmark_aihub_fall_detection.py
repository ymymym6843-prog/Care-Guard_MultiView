"""
AIHub 낙상 데이터셋으로 낙상 감지 정확도 벤치마크

다양한 환경(각도, 조명, 사람)에서 낙상 감지 성능을 측정합니다.
"""

import os
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

import cv2
import random
from pathlib import Path
from collections import defaultdict
from dataclasses import dataclass


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
    ground_truth_fall: bool
    correct: bool  # 정답 여부


def sample_videos_from_aihub(base_path: Path, num_per_category: int = 3) -> list[Path]:
    """AIHub 데이터셋에서 각 카테고리별로 랜덤 샘플링"""
    categories = {
        "BY": base_path / "Y" / "BY",  # 후방 낙상
        "FY": base_path / "Y" / "FY",  # 전방 낙상
        "SY": base_path / "Y" / "SY",  # 측면 낙상
        "N": base_path / "N" / "N",    # 정상
    }

    sampled_videos = []

    for cat_name, cat_path in categories.items():
        if not cat_path.exists():
            print(f"[WARN] 카테고리 없음: {cat_path}")
            continue

        # 폴더 목록 (각 세션)
        sessions = list(cat_path.iterdir())
        if not sessions:
            continue

        # 랜덤 세션 선택
        selected_sessions = random.sample(sessions, min(num_per_category, len(sessions)))

        for session in selected_sessions:
            # 각 세션에서 랜덤 카메라 각도 선택
            mp4_files = list(session.glob("*.mp4"))
            if mp4_files:
                sampled_videos.append(random.choice(mp4_files))

    return sampled_videos


def benchmark_fall_detection(video_paths: list[Path]) -> list[VideoResult]:
    """영상들에서 낙상 감지 성능 측정"""
    from app.services.multi_person_detector import multi_person_detector
    from app.services.fall_detector import fall_detector

    results = []

    for video_path in video_paths:
        print(f"\n[테스트] {video_path.name}")

        # 파일명에서 카테고리와 카메라 추출
        # 예: 00074_H_A_BY_C1.mp4
        parts = video_path.stem.split("_")
        if len(parts) >= 5:
            category = parts[3]  # BY, FY, SY, N
            camera = parts[4]    # C1~C8
        else:
            category = "unknown"
            camera = "unknown"

        ground_truth_fall = category in ["BY", "FY", "SY"]

        cap = cv2.VideoCapture(str(video_path))
        if not cap.isOpened():
            print(f"  [ERROR] 영상 열기 실패")
            continue

        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

        # 통계
        frame_count = 0
        fall_detected_frames = 0
        max_confidence = 0.0

        # 샘플링 (5프레임마다)
        sample_interval = 5

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

                if conf > max_confidence:
                    max_confidence = conf

                if is_fallen:
                    fall_detected_frames += 1

        cap.release()

        processed_frames = frame_count // sample_interval

        # 낙상 감지 여부 결정 (프레임의 1% 이상에서 감지되면 낙상으로 판정)
        # 벤치마크 결과: 5%→1% 변경으로 Recall 66.7%→82.2% 개선 (Precision 유지)
        detected_as_fall = fall_detected_frames >= max(processed_frames * 0.01, 1)

        # 정답 체크
        correct = (detected_as_fall == ground_truth_fall)

        result = VideoResult(
            video_name=video_path.name,
            category=category,
            camera=camera,
            total_frames=total_frames,
            processed_frames=processed_frames,
            fall_detected_frames=fall_detected_frames,
            max_confidence=max_confidence,
            ground_truth_fall=ground_truth_fall,
            correct=correct,
        )
        results.append(result)

        status = "OK" if correct else "WRONG"
        print(f"  카테고리: {category}, 카메라: {camera}")
        print(f"  낙상감지: {fall_detected_frames}/{processed_frames}프레임, max_conf={max_confidence:.3f}")
        print(f"  GT={ground_truth_fall}, Detected={detected_as_fall} -> {status}")

    return results


def print_summary(results: list[VideoResult]):
    """결과 요약 출력"""
    print(f"\n{'='*70}")
    print("AIHub 낙상 감지 벤치마크 결과")
    print(f"{'='*70}")

    # 카테고리별 통계
    category_stats = defaultdict(lambda: {"total": 0, "correct": 0})

    for r in results:
        category_stats[r.category]["total"] += 1
        if r.correct:
            category_stats[r.category]["correct"] += 1

    print("\n[카테고리별 정확도]")
    total_correct = 0
    total_count = 0

    for cat in ["BY", "FY", "SY", "N"]:
        stats = category_stats.get(cat, {"total": 0, "correct": 0})
        if stats["total"] > 0:
            acc = stats["correct"] / stats["total"] * 100
            print(f"  {cat:3s}: {stats['correct']}/{stats['total']} ({acc:.1f}%)")
            total_correct += stats["correct"]
            total_count += stats["total"]

    if total_count > 0:
        overall_acc = total_correct / total_count * 100
        print(f"\n  전체: {total_correct}/{total_count} ({overall_acc:.1f}%)")

    # 오류 케이스 상세
    print("\n[오류 케이스 상세]")
    errors = [r for r in results if not r.correct]
    if errors:
        for r in errors:
            if r.ground_truth_fall and r.fall_detected_frames == 0:
                error_type = "미탐(FN)"
            elif not r.ground_truth_fall and r.fall_detected_frames > 0:
                error_type = "오탐(FP)"
            else:
                error_type = "판정오류"
            print(f"  - {r.video_name}: {error_type}, GT={r.ground_truth_fall}, "
                  f"감지={r.fall_detected_frames}프레임, max_conf={r.max_confidence:.3f}")
    else:
        print("  (없음)")

    # TP/TN/FP/FN 계산
    pct = 0.01  # 1% 임계값 (벤치마크 최적 설정)
    tp = sum(1 for r in results if r.ground_truth_fall and r.fall_detected_frames >= max(r.processed_frames * pct, 1))
    fn = sum(1 for r in results if r.ground_truth_fall and r.fall_detected_frames < max(r.processed_frames * pct, 1))
    fp = sum(1 for r in results if not r.ground_truth_fall and r.fall_detected_frames >= max(r.processed_frames * pct, 1))
    tn = sum(1 for r in results if not r.ground_truth_fall and r.fall_detected_frames < max(r.processed_frames * pct, 1))

    print("\n[혼동 행렬]")
    print(f"  TP (실제 낙상, 감지 O): {tp}")
    print(f"  FN (실제 낙상, 감지 X): {fn}  <- 치명적 (환자 놓침)")
    print(f"  FP (정상, 감지 O):      {fp}  <- 오탐 (알림 피로)")
    print(f"  TN (정상, 감지 X):      {tn}")

    if tp + fn > 0:
        recall = tp / (tp + fn) * 100
        print(f"\n  Recall(재현율): {recall:.1f}% (낙상 중 감지한 비율)")
    if tp + fp > 0:
        precision = tp / (tp + fp) * 100
        print(f"  Precision(정밀도): {precision:.1f}% (감지 중 실제 낙상 비율)")

    print(f"{'='*70}\n")


def main():
    import sys
    # 기본값: Validation, 인자로 Training 가능
    dataset_type = sys.argv[1] if len(sys.argv) > 1 else "Validation"
    aihub_path = Path(f"D:/AIHub_Fall_Data/{dataset_type}/source/영상")

    if not aihub_path.exists():
        print(f"[ERROR] AIHub 데이터 경로 없음: {aihub_path}")
        return

    print(f"{'='*70}")
    print(f"AIHub 낙상 데이터셋 벤치마크 ({dataset_type})")
    print(f"{'='*70}")
    print(f"데이터 경로: {aihub_path}")

    # 각 카테고리에서 5개씩 랜덤 샘플링
    random.seed(42)  # 재현 가능성
    sampled_videos = sample_videos_from_aihub(aihub_path, num_per_category=5)

    print(f"샘플 영상: {len(sampled_videos)}개")
    print(f"{'='*70}")

    # 벤치마크 실행
    results = benchmark_fall_detection(sampled_videos)

    # 결과 요약
    print_summary(results)


if __name__ == "__main__":
    main()
