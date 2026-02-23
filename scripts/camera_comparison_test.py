"""
카메라 개수별 성능 비교 분석 스크립트

Docker 백엔드 로그를 파싱하여:
- 카메라별 YOLO 처리 시간
- 낙상 감지 이벤트
- 플레이리스트 진행 상태
- FPS 계산
을 수집하고 분석합니다.

사용법:
  python scripts/camera_comparison_test.py <로그파일경로> [--label "3-camera"]
"""
import re
import sys
import json
from datetime import datetime
from collections import defaultdict
from pathlib import Path


def parse_log_file(log_path: str) -> dict:
    """Docker 로그 파일을 파싱하여 메트릭 추출"""

    metrics = {
        "yolo_times": defaultdict(list),       # cam_id -> [ms, ms, ...]
        "pipeline_times": defaultdict(list),   # cam_id -> [ms, ms, ...]
        "fall_detections": [],                 # [{cam, person, score, type, time}, ...]
        "danger_alerts": [],                   # [{cam, person, conf, time}, ...]
        "playlist_transitions": defaultdict(list),  # cam_id -> [(video_idx, total, name, time), ...]
        "person_counts": defaultdict(list),    # cam_id -> [count, ...]
        "timestamps": [],
        "walking_aid_times": [],
    }

    # 정규식 패턴
    pat_pipeline = re.compile(
        r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}).*\[(\w+)\] 파이프라인 처리 지연: (\d+)ms \(YOLO=(\d+)ms.*인원=(\d+)"
    )
    pat_fall = re.compile(
        r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}).*낙상 감지!.*person=(\S+).*score=([0-9.]+).*type=(\w+)"
    )
    pat_danger = re.compile(
        r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}).*WARNING→DANGER.*person=(\S+).*max_conf=([0-9.]+)"
    )
    pat_playlist = re.compile(
        r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}).*\[(\w+)\] 플레이리스트 전환 \[(\d+)/(\d+)\]: (.+)"
    )
    pat_walking_aid = re.compile(
        r"보행도구=검사.*?(\d+)ms"
    )

    with open(log_path, "r", encoding="utf-8") as f:
        for line in f:
            # Pipeline processing times
            m = pat_pipeline.search(line)
            if m:
                ts, cam_id, pipeline_ms, yolo_ms, person_count = m.groups()
                metrics["yolo_times"][cam_id].append(int(yolo_ms))
                metrics["pipeline_times"][cam_id].append(int(pipeline_ms))
                metrics["person_counts"][cam_id].append(int(person_count))
                metrics["timestamps"].append(ts)
                continue

            # Fall detection
            m = pat_fall.search(line)
            if m:
                ts, person_id, score, fall_type = m.groups()
                cam_id = person_id.split("_person")[0]
                metrics["fall_detections"].append({
                    "time": ts,
                    "camera": cam_id,
                    "person": person_id,
                    "score": float(score),
                    "type": fall_type,
                })
                continue

            # Danger alerts
            m = pat_danger.search(line)
            if m:
                ts, person_id, conf = m.groups()
                cam_id = person_id.split("_person")[0]
                metrics["danger_alerts"].append({
                    "time": ts,
                    "camera": cam_id,
                    "person": person_id,
                    "confidence": float(conf),
                })
                continue

            # Playlist transitions
            m = pat_playlist.search(line)
            if m:
                ts, cam_id, idx, total, video_name = m.groups()
                metrics["playlist_transitions"][cam_id].append({
                    "time": ts,
                    "index": int(idx),
                    "total": int(total),
                    "video": video_name.strip(),
                })
                continue

    return metrics


def analyze_metrics(metrics: dict, label: str) -> dict:
    """수집된 메트릭을 분석하여 요약 생성"""

    result = {"label": label, "cameras": {}, "summary": {}}

    all_yolo = []
    all_pipeline = []
    total_falls = len(metrics["fall_detections"])
    total_dangers = len(metrics["danger_alerts"])

    active_cameras = sorted(metrics["yolo_times"].keys())

    for cam_id in active_cameras:
        yolo_times = metrics["yolo_times"][cam_id]
        pipeline_times = metrics["pipeline_times"][cam_id]
        person_counts = metrics["person_counts"][cam_id]
        transitions = metrics["playlist_transitions"].get(cam_id, [])

        cam_falls = [f for f in metrics["fall_detections"] if f["camera"] == cam_id]
        cam_dangers = [d for d in metrics["danger_alerts"] if d["camera"] == cam_id]

        all_yolo.extend(yolo_times)
        all_pipeline.extend(pipeline_times)

        # 플레이리스트 루프 수 계산
        loop_starts = [t for t in transitions if t["index"] == 1]
        loops_completed = max(0, len(loop_starts) - 1)  # 첫 번째는 초기 시작

        # FPS 추정 (프레임 수 / 시간)
        cam_timestamps = []
        for ts_str in metrics["timestamps"]:
            try:
                cam_timestamps.append(datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S"))
            except ValueError:
                pass

        if len(cam_timestamps) >= 2:
            duration_sec = (cam_timestamps[-1] - cam_timestamps[0]).total_seconds()
        else:
            duration_sec = 0

        cam_data = {
            "frames_processed": len(yolo_times),
            "yolo_avg_ms": sum(yolo_times) / len(yolo_times) if yolo_times else 0,
            "yolo_p50_ms": sorted(yolo_times)[len(yolo_times) // 2] if yolo_times else 0,
            "yolo_p95_ms": sorted(yolo_times)[int(len(yolo_times) * 0.95)] if yolo_times else 0,
            "yolo_max_ms": max(yolo_times) if yolo_times else 0,
            "pipeline_avg_ms": sum(pipeline_times) / len(pipeline_times) if pipeline_times else 0,
            "avg_persons": sum(person_counts) / len(person_counts) if person_counts else 0,
            "fall_detections": len(cam_falls),
            "danger_alerts": len(cam_dangers),
            "playlist_transitions": len(transitions),
            "loops_completed": loops_completed,
            "fall_details": cam_falls,
        }
        result["cameras"][cam_id] = cam_data

    # 전체 요약
    if metrics["timestamps"]:
        try:
            first_ts = datetime.strptime(metrics["timestamps"][0], "%Y-%m-%d %H:%M:%S")
            last_ts = datetime.strptime(metrics["timestamps"][-1], "%Y-%m-%d %H:%M:%S")
            total_duration = (last_ts - first_ts).total_seconds()
        except ValueError:
            total_duration = 0
    else:
        total_duration = 0

    total_frames = sum(len(v) for v in metrics["yolo_times"].values())

    # 각 카메라별 평균 FPS
    cam_fps = {}
    if total_duration > 0:
        for cam_id in active_cameras:
            cam_fps[cam_id] = len(metrics["yolo_times"][cam_id]) / total_duration

    result["summary"] = {
        "active_cameras": len(active_cameras),
        "camera_ids": active_cameras,
        "total_duration_sec": total_duration,
        "total_frames": total_frames,
        "overall_fps": total_frames / total_duration if total_duration > 0 else 0,
        "per_camera_fps": cam_fps,
        "avg_fps_per_camera": (total_frames / len(active_cameras) / total_duration) if (total_duration > 0 and active_cameras) else 0,
        "yolo_global_avg_ms": sum(all_yolo) / len(all_yolo) if all_yolo else 0,
        "yolo_global_p95_ms": sorted(all_yolo)[int(len(all_yolo) * 0.95)] if all_yolo else 0,
        "total_fall_detections": total_falls,
        "total_danger_alerts": total_dangers,
    }

    # 낙상 영상별 감지 분석
    fall_videos = analyze_fall_by_video(metrics)
    result["fall_video_analysis"] = fall_videos

    return result


def analyze_fall_by_video(metrics: dict) -> dict:
    """플레이리스트 전환 시점과 낙상 감지를 매칭하여 영상별 감지 여부 분석"""

    # 낙상 영상 식별 (파일명에 BY, FY, SY 포함)
    fall_pattern = re.compile(r"(BY|FY|SY)")

    video_results = {}

    for cam_id, transitions in metrics["playlist_transitions"].items():
        for i, trans in enumerate(transitions):
            video_name = trans["video"]
            start_time = datetime.strptime(trans["time"], "%Y-%m-%d %H:%M:%S")

            # 다음 전환 시점 (없으면 마지막 타임스탬프)
            if i + 1 < len(transitions):
                end_time = datetime.strptime(transitions[i + 1]["time"], "%Y-%m-%d %H:%M:%S")
            elif metrics["timestamps"]:
                end_time = datetime.strptime(metrics["timestamps"][-1], "%Y-%m-%d %H:%M:%S")
            else:
                continue

            is_fall_video = bool(fall_pattern.search(video_name))

            # 해당 시간 구간에서 이 카메라의 낙상 감지 확인
            falls_in_window = [
                f for f in metrics["fall_detections"]
                if f["camera"] == cam_id
                and start_time <= datetime.strptime(f["time"], "%Y-%m-%d %H:%M:%S") <= end_time
            ]
            dangers_in_window = [
                d for d in metrics["danger_alerts"]
                if d["camera"] == cam_id
                and start_time <= datetime.strptime(d["time"], "%Y-%m-%d %H:%M:%S") <= end_time
            ]

            key = f"{cam_id}/{video_name}"
            video_results[key] = {
                "camera": cam_id,
                "video": video_name,
                "is_fall_video": is_fall_video,
                "fall_type": fall_pattern.search(video_name).group(1) if is_fall_video else "N",
                "detected": len(falls_in_window) > 0 or len(dangers_in_window) > 0,
                "fall_count": len(falls_in_window),
                "danger_count": len(dangers_in_window),
                "max_score": max((f["score"] for f in falls_in_window), default=0),
            }

    return video_results


def print_report(analysis: dict):
    """분석 결과를 보기 좋게 출력"""

    label = analysis["label"]
    summary = analysis["summary"]

    print(f"\n{'='*70}")
    print(f"  카메라 비교 분석 결과: {label}")
    print(f"{'='*70}")

    print(f"\n[전체 요약]")
    print(f"  활성 카메라: {summary['active_cameras']}대 ({', '.join(summary['camera_ids'])})")
    print(f"  총 테스트 시간: {summary['total_duration_sec']:.0f}초 ({summary['total_duration_sec']/60:.1f}분)")
    print(f"  총 처리 프레임: {summary['total_frames']:,}")
    print(f"  전체 FPS: {summary['overall_fps']:.1f}")
    print(f"  카메라당 평균 FPS: {summary['avg_fps_per_camera']:.1f}")
    print(f"  YOLO 평균 지연: {summary['yolo_global_avg_ms']:.0f}ms")
    print(f"  YOLO P95 지연: {summary['yolo_global_p95_ms']:.0f}ms")
    print(f"  총 낙상 감지: {summary['total_fall_detections']}건")
    print(f"  총 DANGER 알림: {summary['total_danger_alerts']}건")

    print(f"\n[카메라별 상세]")
    for cam_id, cam_data in sorted(analysis["cameras"].items()):
        fps = summary["per_camera_fps"].get(cam_id, 0)
        print(f"\n  {cam_id}:")
        print(f"    프레임 수: {cam_data['frames_processed']:,}")
        print(f"    FPS: {fps:.1f}")
        print(f"    YOLO 평균/P50/P95/최대: {cam_data['yolo_avg_ms']:.0f}/{cam_data['yolo_p50_ms']}/{cam_data['yolo_p95_ms']}/{cam_data['yolo_max_ms']}ms")
        print(f"    평균 인원: {cam_data['avg_persons']:.1f}명")
        print(f"    낙상 감지/DANGER: {cam_data['fall_detections']}/{cam_data['danger_alerts']}건")
        print(f"    플레이리스트 전환: {cam_data['playlist_transitions']}회")

    # 낙상 영상별 분석
    video_analysis = analysis.get("fall_video_analysis", {})
    if video_analysis:
        print(f"\n[영상별 낙상 감지 분석]")

        # 낙상 영상만 필터
        fall_videos = {k: v for k, v in video_analysis.items() if v["is_fall_video"]}
        normal_videos = {k: v for k, v in video_analysis.items() if not v["is_fall_video"]}

        if fall_videos:
            detected = sum(1 for v in fall_videos.values() if v["detected"])
            total = len(fall_videos)
            print(f"\n  낙상 영상 감지율: {detected}/{total} ({detected/total*100:.1f}%)")
            for key, v in sorted(fall_videos.items()):
                status = "O 감지" if v["detected"] else "X 미감지"
                score_str = f" (최고점수: {v['max_score']:.2f})" if v["max_score"] > 0 else ""
                print(f"    [{status}] {v['camera']}/{v['video']} ({v['fall_type']}){score_str}")

        if normal_videos:
            false_positives = sum(1 for v in normal_videos.values() if v["detected"])
            total_n = len(normal_videos)
            print(f"\n  정상 영상 오탐율: {false_positives}/{total_n} ({false_positives/total_n*100:.1f}%)")
            for key, v in sorted(normal_videos.items()):
                if v["detected"]:
                    print(f"    [FP] {v['camera']}/{v['video']} (감지 {v['fall_count']}건)")

    print(f"\n{'='*70}\n")


def main():
    if len(sys.argv) < 2:
        print("사용법: python scripts/camera_comparison_test.py <로그파일> [--label '라벨']")
        sys.exit(1)

    log_path = sys.argv[1]
    label = "분석"

    if "--label" in sys.argv:
        idx = sys.argv.index("--label")
        if idx + 1 < len(sys.argv):
            label = sys.argv[idx + 1]

    if not Path(log_path).exists():
        print(f"파일을 찾을 수 없습니다: {log_path}")
        sys.exit(1)

    print(f"로그 파일 파싱 중: {log_path}")
    metrics = parse_log_file(log_path)

    print(f"분석 중...")
    analysis = analyze_metrics(metrics, label)

    print_report(analysis)

    # JSON으로도 저장
    json_path = Path(log_path).with_suffix(".json")
    with open(json_path, "w", encoding="utf-8") as f:
        # fall_details에서 datetime 객체 제거
        json.dump(analysis, f, ensure_ascii=False, indent=2, default=str)
    print(f"상세 결과 저장: {json_path}")


if __name__ == "__main__":
    main()
