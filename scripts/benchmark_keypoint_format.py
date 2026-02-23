#!/usr/bin/env python3
"""
COCO 17점 vs MediaPipe 33점 키포인트 포맷 성능 비교 벤치마크

Phase 27: YOLO Pose 17점 전환 검증 (동적 시퀀스 확장)
- 처리 속도 비교 (ms, FPS)
- 정확도 비교 (21개 동적 시나리오)
- 메모리 사용량 비교

Usage:
    python scripts/benchmark_keypoint_format.py
    python scripts/benchmark_keypoint_format.py --frames 30 --output docs/keypoint_benchmark.md
    python scripts/benchmark_keypoint_format.py --dynamic-only  # 동적 시퀀스만 테스트
"""

import argparse
import gc
import math
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

# 프로젝트 루트를 PYTHONPATH에 추가
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "backend"))

import numpy as np

# psutil for memory monitoring (optional)
try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False
    print("Warning: psutil not installed, memory monitoring disabled")


@dataclass
class BenchmarkResult:
    """벤치마크 결과"""
    format_name: str
    mean_ms: float
    p50_ms: float
    p95_ms: float
    p99_ms: float
    fps: float
    accuracy: float
    recall: float
    precision: float
    f1_score: float
    memory_mb: float
    scenario_results: dict = field(default_factory=dict)


@dataclass
class ScenarioResult:
    """개별 시나리오 결과"""
    name: str
    expected: bool  # True = 낙상, False = 정상
    detected: bool
    confidence: float
    frames_to_detect: int  # 감지까지 프레임 수


# ============================================================================
# 동적 시퀀스 생성기
# ============================================================================

def interpolate_pose(start: list[dict], end: list[dict], t: float) -> list[dict]:
    """두 포즈 사이를 선형 보간 (t: 0.0 ~ 1.0)"""
    result = []
    for s, e in zip(start, end):
        result.append({
            "x": s["x"] + (e["x"] - s["x"]) * t,
            "y": s["y"] + (e["y"] - s["y"]) * t,
            "z": s.get("z", 0.0) + (e.get("z", 0.0) - s.get("z", 0.0)) * t,
            "visibility": s.get("visibility", 1.0),
        })
    return result


def apply_noise(landmarks: list[dict], noise_level: float = 0.005) -> list[dict]:
    """자연스러운 노이즈 추가"""
    return [
        {
            "x": lm["x"] + np.random.uniform(-noise_level, noise_level),
            "y": lm["y"] + np.random.uniform(-noise_level, noise_level),
            "z": lm.get("z", 0.0),
            "visibility": lm.get("visibility", 1.0),
        }
        for lm in landmarks
    ]


def ease_in_quad(t: float) -> float:
    """가속 easing (낙상 시 중력 가속)"""
    return t * t


def ease_out_quad(t: float) -> float:
    """감속 easing"""
    return 1 - (1 - t) * (1 - t)


# ── 기본 포즈 정의 (COCO 17점) ──

def pose_standing() -> list[dict]:
    """서있는 자세"""
    return [
        {"x": 0.50, "y": 0.15, "z": 0.0, "visibility": 0.95},  # 0: nose
        {"x": 0.48, "y": 0.13, "z": 0.0, "visibility": 0.90},  # 1: left_eye
        {"x": 0.52, "y": 0.13, "z": 0.0, "visibility": 0.90},  # 2: right_eye
        {"x": 0.46, "y": 0.15, "z": 0.0, "visibility": 0.85},  # 3: left_ear
        {"x": 0.54, "y": 0.15, "z": 0.0, "visibility": 0.85},  # 4: right_ear
        {"x": 0.45, "y": 0.25, "z": 0.0, "visibility": 0.95},  # 5: left_shoulder
        {"x": 0.55, "y": 0.25, "z": 0.0, "visibility": 0.95},  # 6: right_shoulder
        {"x": 0.43, "y": 0.38, "z": 0.0, "visibility": 0.90},  # 7: left_elbow
        {"x": 0.57, "y": 0.38, "z": 0.0, "visibility": 0.90},  # 8: right_elbow
        {"x": 0.42, "y": 0.48, "z": 0.0, "visibility": 0.85},  # 9: left_wrist
        {"x": 0.58, "y": 0.48, "z": 0.0, "visibility": 0.85},  # 10: right_wrist
        {"x": 0.47, "y": 0.50, "z": 0.0, "visibility": 0.95},  # 11: left_hip
        {"x": 0.53, "y": 0.50, "z": 0.0, "visibility": 0.95},  # 12: right_hip
        {"x": 0.46, "y": 0.72, "z": 0.0, "visibility": 0.90},  # 13: left_knee
        {"x": 0.54, "y": 0.72, "z": 0.0, "visibility": 0.90},  # 14: right_knee
        {"x": 0.45, "y": 0.95, "z": 0.0, "visibility": 0.85},  # 15: left_ankle
        {"x": 0.55, "y": 0.95, "z": 0.0, "visibility": 0.85},  # 16: right_ankle
    ]


def pose_fallen_forward() -> list[dict]:
    """전방 낙상 최종 자세 (엎드림)"""
    return [
        {"x": 0.30, "y": 0.85, "z": 0.0, "visibility": 0.70},  # nose (바닥)
        {"x": 0.28, "y": 0.83, "z": 0.0, "visibility": 0.60},
        {"x": 0.32, "y": 0.83, "z": 0.0, "visibility": 0.60},
        {"x": 0.26, "y": 0.85, "z": 0.0, "visibility": 0.50},
        {"x": 0.34, "y": 0.85, "z": 0.0, "visibility": 0.50},
        {"x": 0.40, "y": 0.80, "z": 0.0, "visibility": 0.85},  # shoulders
        {"x": 0.50, "y": 0.80, "z": 0.0, "visibility": 0.85},
        {"x": 0.25, "y": 0.85, "z": 0.0, "visibility": 0.75},  # elbows (펼침)
        {"x": 0.55, "y": 0.85, "z": 0.0, "visibility": 0.75},
        {"x": 0.20, "y": 0.90, "z": 0.0, "visibility": 0.70},  # wrists
        {"x": 0.60, "y": 0.90, "z": 0.0, "visibility": 0.70},
        {"x": 0.55, "y": 0.75, "z": 0.0, "visibility": 0.90},  # hips
        {"x": 0.65, "y": 0.75, "z": 0.0, "visibility": 0.90},
        {"x": 0.60, "y": 0.85, "z": 0.0, "visibility": 0.85},  # knees
        {"x": 0.70, "y": 0.85, "z": 0.0, "visibility": 0.85},
        {"x": 0.65, "y": 0.95, "z": 0.0, "visibility": 0.80},  # ankles
        {"x": 0.75, "y": 0.95, "z": 0.0, "visibility": 0.80},
    ]


def pose_fallen_backward() -> list[dict]:
    """후방 낙상 최종 자세 (누움)"""
    return [
        {"x": 0.70, "y": 0.80, "z": 0.0, "visibility": 0.85},  # nose
        {"x": 0.68, "y": 0.78, "z": 0.0, "visibility": 0.80},
        {"x": 0.72, "y": 0.78, "z": 0.0, "visibility": 0.80},
        {"x": 0.66, "y": 0.80, "z": 0.0, "visibility": 0.75},
        {"x": 0.74, "y": 0.80, "z": 0.0, "visibility": 0.75},
        {"x": 0.60, "y": 0.82, "z": 0.0, "visibility": 0.90},  # shoulders
        {"x": 0.55, "y": 0.82, "z": 0.0, "visibility": 0.90},
        {"x": 0.65, "y": 0.88, "z": 0.0, "visibility": 0.80},  # elbows
        {"x": 0.50, "y": 0.88, "z": 0.0, "visibility": 0.80},
        {"x": 0.70, "y": 0.92, "z": 0.0, "visibility": 0.75},  # wrists
        {"x": 0.45, "y": 0.92, "z": 0.0, "visibility": 0.75},
        {"x": 0.50, "y": 0.80, "z": 0.0, "visibility": 0.90},  # hips
        {"x": 0.45, "y": 0.80, "z": 0.0, "visibility": 0.90},
        {"x": 0.40, "y": 0.85, "z": 0.0, "visibility": 0.85},  # knees
        {"x": 0.35, "y": 0.85, "z": 0.0, "visibility": 0.85},
        {"x": 0.30, "y": 0.90, "z": 0.0, "visibility": 0.80},  # ankles
        {"x": 0.25, "y": 0.90, "z": 0.0, "visibility": 0.80},
    ]


def pose_fallen_side() -> list[dict]:
    """측면 낙상 최종 자세"""
    return [
        {"x": 0.35, "y": 0.75, "z": 0.0, "visibility": 0.85},  # nose
        {"x": 0.33, "y": 0.73, "z": 0.0, "visibility": 0.80},
        {"x": 0.37, "y": 0.73, "z": 0.0, "visibility": 0.80},
        {"x": 0.31, "y": 0.75, "z": 0.0, "visibility": 0.70},
        {"x": 0.39, "y": 0.75, "z": 0.0, "visibility": 0.85},
        {"x": 0.40, "y": 0.78, "z": 0.0, "visibility": 0.90},  # shoulders (측면)
        {"x": 0.42, "y": 0.82, "z": 0.0, "visibility": 0.85},
        {"x": 0.45, "y": 0.85, "z": 0.0, "visibility": 0.80},  # elbows
        {"x": 0.38, "y": 0.88, "z": 0.0, "visibility": 0.75},
        {"x": 0.50, "y": 0.90, "z": 0.0, "visibility": 0.70},  # wrists
        {"x": 0.35, "y": 0.92, "z": 0.0, "visibility": 0.70},
        {"x": 0.55, "y": 0.80, "z": 0.0, "visibility": 0.90},  # hips
        {"x": 0.58, "y": 0.83, "z": 0.0, "visibility": 0.85},
        {"x": 0.62, "y": 0.85, "z": 0.0, "visibility": 0.85},  # knees
        {"x": 0.65, "y": 0.88, "z": 0.0, "visibility": 0.80},
        {"x": 0.70, "y": 0.90, "z": 0.0, "visibility": 0.80},  # ankles
        {"x": 0.73, "y": 0.92, "z": 0.0, "visibility": 0.75},
    ]


def pose_sitting() -> list[dict]:
    """앉은 자세"""
    return [
        {"x": 0.50, "y": 0.35, "z": 0.0, "visibility": 0.95},  # nose
        {"x": 0.48, "y": 0.33, "z": 0.0, "visibility": 0.90},
        {"x": 0.52, "y": 0.33, "z": 0.0, "visibility": 0.90},
        {"x": 0.46, "y": 0.35, "z": 0.0, "visibility": 0.85},
        {"x": 0.54, "y": 0.35, "z": 0.0, "visibility": 0.85},
        {"x": 0.45, "y": 0.45, "z": 0.0, "visibility": 0.95},  # shoulders
        {"x": 0.55, "y": 0.45, "z": 0.0, "visibility": 0.95},
        {"x": 0.43, "y": 0.55, "z": 0.0, "visibility": 0.90},  # elbows
        {"x": 0.57, "y": 0.55, "z": 0.0, "visibility": 0.90},
        {"x": 0.42, "y": 0.60, "z": 0.0, "visibility": 0.85},  # wrists
        {"x": 0.58, "y": 0.60, "z": 0.0, "visibility": 0.85},
        {"x": 0.47, "y": 0.62, "z": 0.0, "visibility": 0.95},  # hips (굽힘)
        {"x": 0.53, "y": 0.62, "z": 0.0, "visibility": 0.95},
        {"x": 0.40, "y": 0.68, "z": 0.0, "visibility": 0.90},  # knees (앞으로)
        {"x": 0.60, "y": 0.68, "z": 0.0, "visibility": 0.90},
        {"x": 0.42, "y": 0.85, "z": 0.0, "visibility": 0.85},  # ankles
        {"x": 0.58, "y": 0.85, "z": 0.0, "visibility": 0.85},
    ]


def pose_bending() -> list[dict]:
    """구부린 자세 (줍기)"""
    return [
        {"x": 0.50, "y": 0.55, "z": 0.0, "visibility": 0.90},  # nose (아래로)
        {"x": 0.48, "y": 0.53, "z": 0.0, "visibility": 0.85},
        {"x": 0.52, "y": 0.53, "z": 0.0, "visibility": 0.85},
        {"x": 0.46, "y": 0.55, "z": 0.0, "visibility": 0.80},
        {"x": 0.54, "y": 0.55, "z": 0.0, "visibility": 0.80},
        {"x": 0.45, "y": 0.50, "z": 0.0, "visibility": 0.90},  # shoulders
        {"x": 0.55, "y": 0.50, "z": 0.0, "visibility": 0.90},
        {"x": 0.43, "y": 0.60, "z": 0.0, "visibility": 0.85},  # elbows
        {"x": 0.57, "y": 0.60, "z": 0.0, "visibility": 0.85},
        {"x": 0.45, "y": 0.75, "z": 0.0, "visibility": 0.80},  # wrists (바닥 근처)
        {"x": 0.55, "y": 0.75, "z": 0.0, "visibility": 0.80},
        {"x": 0.47, "y": 0.55, "z": 0.0, "visibility": 0.95},  # hips
        {"x": 0.53, "y": 0.55, "z": 0.0, "visibility": 0.95},
        {"x": 0.46, "y": 0.75, "z": 0.0, "visibility": 0.90},  # knees
        {"x": 0.54, "y": 0.75, "z": 0.0, "visibility": 0.90},
        {"x": 0.45, "y": 0.95, "z": 0.0, "visibility": 0.85},  # ankles
        {"x": 0.55, "y": 0.95, "z": 0.0, "visibility": 0.85},
    ]


def pose_lying_bed() -> list[dict]:
    """침대에 누운 자세 (정상) - 머리가 베개 위 (엉덩이보다 위)"""
    return [
        {"x": 0.15, "y": 0.38, "z": 0.0, "visibility": 0.90},  # nose (베개 위, hip보다 위)
        {"x": 0.13, "y": 0.36, "z": 0.0, "visibility": 0.85},
        {"x": 0.17, "y": 0.36, "z": 0.0, "visibility": 0.85},
        {"x": 0.11, "y": 0.38, "z": 0.0, "visibility": 0.80},
        {"x": 0.19, "y": 0.38, "z": 0.0, "visibility": 0.80},
        {"x": 0.28, "y": 0.42, "z": 0.0, "visibility": 0.90},  # shoulders
        {"x": 0.30, "y": 0.38, "z": 0.0, "visibility": 0.90},
        {"x": 0.40, "y": 0.45, "z": 0.0, "visibility": 0.85},  # elbows
        {"x": 0.42, "y": 0.35, "z": 0.0, "visibility": 0.85},
        {"x": 0.48, "y": 0.48, "z": 0.0, "visibility": 0.80},  # wrists
        {"x": 0.50, "y": 0.32, "z": 0.0, "visibility": 0.80},
        {"x": 0.55, "y": 0.47, "z": 0.0, "visibility": 0.90},  # hips (nose보다 아래)
        {"x": 0.57, "y": 0.43, "z": 0.0, "visibility": 0.90},
        {"x": 0.70, "y": 0.48, "z": 0.0, "visibility": 0.85},  # knees
        {"x": 0.72, "y": 0.42, "z": 0.0, "visibility": 0.85},
        {"x": 0.85, "y": 0.48, "z": 0.0, "visibility": 0.80},  # ankles
        {"x": 0.87, "y": 0.42, "z": 0.0, "visibility": 0.80},
    ]


def pose_stumble() -> list[dict]:
    """비틀거리는 자세 (전조)"""
    return [
        {"x": 0.48, "y": 0.20, "z": 0.0, "visibility": 0.90},  # nose (기울어짐)
        {"x": 0.46, "y": 0.18, "z": 0.0, "visibility": 0.85},
        {"x": 0.50, "y": 0.18, "z": 0.0, "visibility": 0.85},
        {"x": 0.44, "y": 0.20, "z": 0.0, "visibility": 0.80},
        {"x": 0.52, "y": 0.20, "z": 0.0, "visibility": 0.80},
        {"x": 0.42, "y": 0.30, "z": 0.0, "visibility": 0.90},  # shoulders (기울어짐)
        {"x": 0.56, "y": 0.28, "z": 0.0, "visibility": 0.90},
        {"x": 0.38, "y": 0.42, "z": 0.0, "visibility": 0.85},  # elbows (팔 벌림)
        {"x": 0.62, "y": 0.40, "z": 0.0, "visibility": 0.85},
        {"x": 0.32, "y": 0.48, "z": 0.0, "visibility": 0.80},  # wrists
        {"x": 0.68, "y": 0.45, "z": 0.0, "visibility": 0.80},
        {"x": 0.45, "y": 0.52, "z": 0.0, "visibility": 0.95},  # hips
        {"x": 0.55, "y": 0.52, "z": 0.0, "visibility": 0.95},
        {"x": 0.44, "y": 0.73, "z": 0.0, "visibility": 0.90},  # knees
        {"x": 0.56, "y": 0.73, "z": 0.0, "visibility": 0.90},
        {"x": 0.43, "y": 0.95, "z": 0.0, "visibility": 0.85},  # ankles
        {"x": 0.57, "y": 0.95, "z": 0.0, "visibility": 0.85},
    ]


# ============================================================================
# 동적 시퀀스 생성 함수
# ============================================================================

def generate_fall_sequence_forward(frames: int = 30) -> list[list[dict]]:
    """전방 낙상 시퀀스: 서있음 → 앞으로 쓰러짐"""
    sequence = []
    start = pose_standing()
    end = pose_fallen_forward()

    for i in range(frames):
        t = i / (frames - 1)
        # 낙상은 가속 (중력 효과)
        t_eased = ease_in_quad(t)
        pose = interpolate_pose(start, end, t_eased)
        sequence.append(apply_noise(pose))

    return sequence


def generate_fall_sequence_backward(frames: int = 30) -> list[list[dict]]:
    """후방 낙상 시퀀스: 서있음 → 뒤로 쓰러짐"""
    sequence = []
    start = pose_standing()
    end = pose_fallen_backward()

    for i in range(frames):
        t = i / (frames - 1)
        t_eased = ease_in_quad(t)
        pose = interpolate_pose(start, end, t_eased)
        sequence.append(apply_noise(pose))

    return sequence


def generate_fall_sequence_side(frames: int = 30) -> list[list[dict]]:
    """측면 낙상 시퀀스"""
    sequence = []
    start = pose_standing()
    end = pose_fallen_side()

    for i in range(frames):
        t = i / (frames - 1)
        t_eased = ease_in_quad(t)
        pose = interpolate_pose(start, end, t_eased)
        sequence.append(apply_noise(pose))

    return sequence


def generate_fall_sequence_trip(frames: int = 35) -> list[list[dict]]:
    """걸려 넘어짐 시퀀스: 걷기 → 발 걸림 → 전방 낙상"""
    sequence = []
    standing = pose_standing()

    # Phase 1: 걷기 (0-10 frames)
    for i in range(10):
        t = i / 10
        pose = standing.copy()
        # 걷기 모션 (발 교차)
        pose = [p.copy() for p in pose]
        pose[15]["x"] += 0.02 * math.sin(t * math.pi * 2)  # left ankle
        pose[16]["x"] -= 0.02 * math.sin(t * math.pi * 2)  # right ankle
        sequence.append(apply_noise(pose))

    # Phase 2: 비틀거림 (10-20 frames)
    stumble = pose_stumble()
    for i in range(10):
        t = i / 10
        pose = interpolate_pose(standing, stumble, t)
        sequence.append(apply_noise(pose))

    # Phase 3: 낙상 (20-35 frames)
    fallen = pose_fallen_forward()
    for i in range(15):
        t = i / 15
        t_eased = ease_in_quad(t)
        pose = interpolate_pose(stumble, fallen, t_eased)
        sequence.append(apply_noise(pose))

    return sequence


def generate_fall_sequence_slow(frames: int = 45) -> list[list[dict]]:
    """느린 쓰러짐 시퀀스 (무릎부터 천천히)"""
    sequence = []
    standing = pose_standing()

    # Phase 1: 무릎 굽힘 (0-20 frames)
    knee_bent = [p.copy() for p in standing]
    knee_bent[0]["y"] = 0.35  # nose down
    knee_bent[5]["y"] = 0.40  # shoulders down
    knee_bent[6]["y"] = 0.40
    knee_bent[11]["y"] = 0.60  # hips down
    knee_bent[12]["y"] = 0.60
    knee_bent[13]["y"] = 0.75  # knees bent
    knee_bent[14]["y"] = 0.75

    for i in range(20):
        t = i / 20
        pose = interpolate_pose(standing, knee_bent, ease_out_quad(t))
        sequence.append(apply_noise(pose))

    # Phase 2: 옆으로 쓰러짐 (20-45 frames)
    fallen = pose_fallen_side()
    for i in range(25):
        t = i / 25
        t_eased = ease_in_quad(t)
        pose = interpolate_pose(knee_bent, fallen, t_eased)
        sequence.append(apply_noise(pose))

    return sequence


def generate_fall_sequence_slip(frames: int = 25) -> list[list[dict]]:
    """미끄러짐 낙상 시퀀스 (빠른 후방 낙상)"""
    sequence = []
    standing = pose_standing()
    fallen = pose_fallen_backward()

    # 미끄러짐은 매우 빠름
    for i in range(frames):
        t = i / (frames - 1)
        # 더 급격한 가속
        t_eased = t * t * t
        pose = interpolate_pose(standing, fallen, t_eased)
        sequence.append(apply_noise(pose, noise_level=0.008))

    return sequence


def generate_fall_sequence_knee_buckle(frames: int = 35) -> list[list[dict]]:
    """무릎 좌굴 후 낙상 시퀀스"""
    sequence = []
    standing = pose_standing()

    # Phase 1: 무릎 갑자기 꺾임 (0-10 frames)
    knee_buckle = [p.copy() for p in standing]
    knee_buckle[13]["y"] = 0.82  # left knee drops
    knee_buckle[13]["x"] = 0.44
    knee_buckle[0]["y"] = 0.30  # head drops
    knee_buckle[5]["y"] = 0.38
    knee_buckle[6]["y"] = 0.38
    knee_buckle[11]["y"] = 0.58
    knee_buckle[12]["y"] = 0.58

    for i in range(10):
        t = i / 10
        pose = interpolate_pose(standing, knee_buckle, ease_in_quad(t))
        sequence.append(apply_noise(pose))

    # Phase 2: 낙상 (10-35 frames)
    fallen = pose_fallen_forward()
    for i in range(25):
        t = i / 25
        pose = interpolate_pose(knee_buckle, fallen, ease_in_quad(t))
        sequence.append(apply_noise(pose))

    return sequence


def generate_fall_sequence_bed(frames: int = 30) -> list[list[dict]]:
    """침대 낙상 시퀀스"""
    sequence = []

    # 침대 높이에서 시작
    bed_sitting = pose_sitting()
    for p in bed_sitting:
        p["y"] -= 0.15  # 침대 높이

    # 옆으로 떨어짐
    fallen = pose_fallen_side()

    for i in range(frames):
        t = i / (frames - 1)
        t_eased = ease_in_quad(t)
        pose = interpolate_pose(bed_sitting, fallen, t_eased)
        sequence.append(apply_noise(pose))

    return sequence


# ── 정상 활동 시퀀스 ──

def generate_normal_walking(frames: int = 30) -> list[list[dict]]:
    """정상 보행 시퀀스"""
    sequence = []
    standing = pose_standing()

    for i in range(frames):
        t = i / frames
        pose = [p.copy() for p in standing]

        # 걷기 모션
        phase = t * math.pi * 4  # 2 걸음

        # 발 교차
        pose[15]["x"] += 0.03 * math.sin(phase)
        pose[16]["x"] -= 0.03 * math.sin(phase)

        # 팔 흔들기
        pose[9]["y"] += 0.02 * math.sin(phase + math.pi)
        pose[10]["y"] += 0.02 * math.sin(phase)

        # 약간의 상하 움직임
        for j in range(len(pose)):
            pose[j]["y"] += 0.005 * abs(math.sin(phase * 2))

        sequence.append(apply_noise(pose))

    return sequence


def generate_normal_sitting(frames: int = 30) -> list[list[dict]]:
    """정상 앉기 시퀀스"""
    sequence = []
    standing = pose_standing()
    sitting = pose_sitting()

    for i in range(frames):
        t = i / (frames - 1)
        # 천천히 앉기
        t_eased = ease_out_quad(t)
        pose = interpolate_pose(standing, sitting, t_eased)
        sequence.append(apply_noise(pose))

    return sequence


def generate_normal_bending(frames: int = 30) -> list[list[dict]]:
    """정상 구부리기 (줍기) 시퀀스"""
    sequence = []
    standing = pose_standing()
    bending = pose_bending()

    # 구부리기 (0-15 frames)
    for i in range(15):
        t = i / 15
        pose = interpolate_pose(standing, bending, ease_out_quad(t))
        sequence.append(apply_noise(pose))

    # 일어서기 (15-30 frames)
    for i in range(15):
        t = i / 15
        pose = interpolate_pose(bending, standing, ease_out_quad(t))
        sequence.append(apply_noise(pose))

    return sequence


def generate_normal_stretching(frames: int = 30) -> list[list[dict]]:
    """스트레칭 시퀀스"""
    sequence = []
    standing = pose_standing()

    # 팔 위로 스트레칭
    stretch = [p.copy() for p in standing]
    stretch[7]["y"] = 0.12  # elbows up
    stretch[8]["y"] = 0.12
    stretch[9]["y"] = 0.05  # wrists up
    stretch[10]["y"] = 0.05

    for i in range(15):
        t = i / 15
        pose = interpolate_pose(standing, stretch, t)
        sequence.append(apply_noise(pose))

    for i in range(15):
        t = i / 15
        pose = interpolate_pose(stretch, standing, t)
        sequence.append(apply_noise(pose))

    return sequence


def generate_normal_lying_bed(frames: int = 30) -> list[list[dict]]:
    """침대에 눕기 시퀀스 (정상)"""
    sequence = []
    sitting = pose_sitting()
    lying = pose_lying_bed()

    for i in range(frames):
        t = i / (frames - 1)
        pose = interpolate_pose(sitting, lying, ease_out_quad(t))
        sequence.append(apply_noise(pose))

    return sequence


def generate_normal_wheelchair(frames: int = 30) -> list[list[dict]]:
    """휠체어 이동 시퀀스"""
    sequence = []
    sitting = pose_sitting()

    for i in range(frames):
        pose = [p.copy() for p in sitting]
        # 휠체어 팔걸이 잡기
        pose[9]["x"] = 0.35
        pose[10]["x"] = 0.65
        pose[9]["y"] = 0.58
        pose[10]["y"] = 0.58

        # 약간의 좌우 흔들림
        t = i / frames
        for j in range(len(pose)):
            pose[j]["x"] += 0.002 * math.sin(t * math.pi * 4)

        sequence.append(apply_noise(pose))

    return sequence


def generate_normal_quick_sit(frames: int = 20) -> list[list[dict]]:
    """빠른 앉기 시퀀스 (낙상과 구별 필요)"""
    sequence = []
    standing = pose_standing()
    sitting = pose_sitting()

    for i in range(frames):
        t = i / (frames - 1)
        # 빠르지만 제어된 앉기
        t_eased = ease_out_quad(t)
        pose = interpolate_pose(standing, sitting, t_eased)
        sequence.append(apply_noise(pose, noise_level=0.003))

    return sequence


def generate_normal_fast_walking(frames: int = 30) -> list[list[dict]]:
    """빠른 걷기 시퀀스"""
    sequence = []
    standing = pose_standing()

    for i in range(frames):
        t = i / frames
        pose = [p.copy() for p in standing]

        # 빠른 걷기 모션
        phase = t * math.pi * 6  # 3 걸음 (빠름)

        pose[15]["x"] += 0.04 * math.sin(phase)
        pose[16]["x"] -= 0.04 * math.sin(phase)
        pose[9]["y"] += 0.03 * math.sin(phase + math.pi)
        pose[10]["y"] += 0.03 * math.sin(phase)

        for j in range(len(pose)):
            pose[j]["y"] += 0.008 * abs(math.sin(phase * 2))

        sequence.append(apply_noise(pose, noise_level=0.006))

    return sequence


def generate_normal_stairs(frames: int = 30) -> list[list[dict]]:
    """계단 오르기 시퀀스"""
    sequence = []
    standing = pose_standing()

    for i in range(frames):
        t = i / frames
        pose = [p.copy() for p in standing]

        phase = t * math.pi * 3
        step_height = 0.02 * (i // 10)  # 점점 올라감

        # 발 들어올리기
        if i % 10 < 5:
            pose[15]["y"] -= 0.03
        else:
            pose[16]["y"] -= 0.03

        # 전체 높이 상승
        for j in range(len(pose)):
            pose[j]["y"] -= step_height

        sequence.append(apply_noise(pose))

    return sequence


def generate_normal_phone(frames: int = 30) -> list[list[dict]]:
    """전화 사용 시퀀스 (서서)"""
    sequence = []
    standing = pose_standing()

    # 전화 드는 자세
    phone = [p.copy() for p in standing]
    phone[8]["y"] = 0.20  # right elbow up
    phone[10]["x"] = 0.52  # right wrist to ear
    phone[10]["y"] = 0.15

    for i in range(10):
        t = i / 10
        pose = interpolate_pose(standing, phone, t)
        sequence.append(apply_noise(pose))

    # 통화 중 (약간의 움직임)
    for i in range(20):
        pose = [p.copy() for p in phone]
        pose[0]["y"] += 0.005 * math.sin(i * 0.5)  # 고개 끄덕임
        sequence.append(apply_noise(pose))

    return sequence


# ── 전조/회복 시퀀스 ──

def generate_prefall_stumble_recovery(frames: int = 30) -> list[list[dict]]:
    """비틀거림 후 회복 시퀀스"""
    sequence = []
    standing = pose_standing()
    stumble = pose_stumble()

    # 비틀거림 (0-15 frames)
    for i in range(15):
        t = i / 15
        pose = interpolate_pose(standing, stumble, t)
        sequence.append(apply_noise(pose, noise_level=0.008))

    # 회복 (15-30 frames)
    for i in range(15):
        t = i / 15
        pose = interpolate_pose(stumble, standing, ease_out_quad(t))
        sequence.append(apply_noise(pose))

    return sequence


def generate_prefall_balance_recovery(frames: int = 25) -> list[list[dict]]:
    """균형 잃었다 회복 시퀀스"""
    sequence = []
    standing = pose_standing()

    # 균형 잃음
    off_balance = [p.copy() for p in standing]
    off_balance[0]["x"] = 0.55  # head tilted
    off_balance[0]["y"] = 0.18
    off_balance[5]["x"] = 0.48
    off_balance[6]["x"] = 0.58
    off_balance[11]["x"] = 0.50
    off_balance[12]["x"] = 0.56

    for i in range(12):
        t = i / 12
        pose = interpolate_pose(standing, off_balance, t)
        sequence.append(apply_noise(pose, noise_level=0.007))

    for i in range(13):
        t = i / 13
        pose = interpolate_pose(off_balance, standing, ease_out_quad(t))
        sequence.append(apply_noise(pose))

    return sequence


def generate_prefall_knee_slight_bend(frames: int = 25) -> list[list[dict]]:
    """무릎 살짝 꺾였다 회복"""
    sequence = []
    standing = pose_standing()

    # 무릎 살짝 꺾임
    knee_bent = [p.copy() for p in standing]
    knee_bent[13]["y"] = 0.78
    knee_bent[0]["y"] = 0.22
    knee_bent[11]["y"] = 0.55
    knee_bent[12]["y"] = 0.55

    for i in range(12):
        t = i / 12
        pose = interpolate_pose(standing, knee_bent, t)
        sequence.append(apply_noise(pose))

    for i in range(13):
        t = i / 13
        pose = interpolate_pose(knee_bent, standing, ease_out_quad(t))
        sequence.append(apply_noise(pose))

    return sequence


# ============================================================================
# 시나리오 정의
# ============================================================================

DYNAMIC_SCENARIOS = {
    # 낙상 시나리오 (expected_fall=True)
    "fall_forward": {
        "generator": generate_fall_sequence_forward,
        "expected_fall": True,
        "description": "전방 낙상",
        "frames": 30,
    },
    "fall_backward": {
        "generator": generate_fall_sequence_backward,
        "expected_fall": True,
        "description": "후방 낙상",
        "frames": 30,
    },
    "fall_side": {
        "generator": generate_fall_sequence_side,
        "expected_fall": True,
        "description": "측면 낙상",
        "frames": 30,
    },
    "fall_trip": {
        "generator": generate_fall_sequence_trip,
        "expected_fall": True,
        "description": "걸려 넘어짐",
        "frames": 35,
    },
    "fall_slow": {
        "generator": generate_fall_sequence_slow,
        "expected_fall": True,
        "description": "느린 쓰러짐",
        "frames": 45,
    },
    "fall_slip": {
        "generator": generate_fall_sequence_slip,
        "expected_fall": True,
        "description": "미끄러짐",
        "frames": 25,
    },
    "fall_knee_buckle": {
        "generator": generate_fall_sequence_knee_buckle,
        "expected_fall": True,
        "description": "무릎 좌굴 낙상",
        "frames": 35,
    },
    "fall_bed": {
        "generator": generate_fall_sequence_bed,
        "expected_fall": True,
        "description": "침대 낙상",
        "frames": 30,
    },

    # 정상 활동 시나리오 (expected_fall=False)
    "normal_walking": {
        "generator": generate_normal_walking,
        "expected_fall": False,
        "description": "정상 보행",
        "frames": 30,
    },
    "normal_sitting": {
        "generator": generate_normal_sitting,
        "expected_fall": False,
        "description": "정상 앉기",
        "frames": 30,
    },
    "normal_bending": {
        "generator": generate_normal_bending,
        "expected_fall": False,
        "description": "구부리기/줍기",
        "frames": 30,
    },
    "normal_stretching": {
        "generator": generate_normal_stretching,
        "expected_fall": False,
        "description": "스트레칭",
        "frames": 30,
    },
    "normal_lying_bed": {
        "generator": generate_normal_lying_bed,
        "expected_fall": False,
        "description": "침대 눕기",
        "frames": 30,
    },
    "normal_wheelchair": {
        "generator": generate_normal_wheelchair,
        "expected_fall": False,
        "description": "휠체어 이동",
        "frames": 30,
    },
    "normal_quick_sit": {
        "generator": generate_normal_quick_sit,
        "expected_fall": False,
        "description": "빠른 앉기",
        "frames": 20,
    },
    "normal_fast_walking": {
        "generator": generate_normal_fast_walking,
        "expected_fall": False,
        "description": "빠른 걷기",
        "frames": 30,
    },
    "normal_stairs": {
        "generator": generate_normal_stairs,
        "expected_fall": False,
        "description": "계단 오르기",
        "frames": 30,
    },
    "normal_phone": {
        "generator": generate_normal_phone,
        "expected_fall": False,
        "description": "전화 사용",
        "frames": 30,
    },

    # 전조/회복 시나리오 (expected_fall=False, 하지만 pre-impact 감지 가능)
    "prefall_stumble": {
        "generator": generate_prefall_stumble_recovery,
        "expected_fall": False,
        "description": "비틀거림 회복",
        "frames": 30,
    },
    "prefall_balance": {
        "generator": generate_prefall_balance_recovery,
        "expected_fall": False,
        "description": "균형 회복",
        "frames": 25,
    },
    "prefall_knee_bend": {
        "generator": generate_prefall_knee_slight_bend,
        "expected_fall": False,
        "description": "무릎 살짝 꺾임",
        "frames": 25,
    },
}


def get_memory_usage() -> float:
    """현재 메모리 사용량 (MB)"""
    if HAS_PSUTIL:
        process = psutil.Process(os.getpid())
        return process.memory_info().rss / 1024 / 1024
    return 0.0


def convert_to_mediapipe33(coco17_landmarks: list[dict]) -> list[dict]:
    """COCO 17점을 MediaPipe 33점으로 변환"""
    from app.services.keypoint_adapter import KeypointAdapter
    return KeypointAdapter.coco_to_mediapipe_33(coco17_landmarks, interpolate_missing=True)


def benchmark_dynamic_format(
    detector,
    format_name: str,
    keypoint_format: str,
    use_mediapipe: bool = False,
) -> BenchmarkResult:
    """동적 시퀀스로 벤치마크 실행"""
    from app.services.fall_detector import KeypointFormat

    times = []
    scenario_results = {}

    # 통계용
    tp, fp, tn, fn = 0, 0, 0, 0

    gc.collect()
    mem_before = get_memory_usage()

    for scenario_name, config in DYNAMIC_SCENARIOS.items():
        # 시퀀스 생성
        frames = config["frames"]
        sequence = config["generator"](frames)
        expected_fall = config["expected_fall"]

        # MediaPipe 33점 변환 (필요시)
        if use_mediapipe:
            sequence = [convert_to_mediapipe33(frame) for frame in sequence]

        # 새 person_id로 상태 초기화
        person_id = f"{format_name}_{scenario_name}"

        detected = False
        max_confidence = 0.0
        frames_to_detect = -1

        for frame_idx, landmarks in enumerate(sequence):
            start = time.perf_counter()
            result = detector.detect(
                landmarks,
                person_id=person_id,
                keypoint_format=keypoint_format,
            )
            elapsed = (time.perf_counter() - start) * 1000
            times.append(elapsed)

            conf = result.get("confidence", 0.0)
            if conf > max_confidence:
                max_confidence = conf

            if result.get("is_fallen") or conf >= 0.5:
                if not detected:
                    detected = True
                    frames_to_detect = frame_idx + 1

        # 결과 기록
        scenario_results[scenario_name] = ScenarioResult(
            name=config["description"],
            expected=expected_fall,
            detected=detected,
            confidence=max_confidence,
            frames_to_detect=frames_to_detect,
        )

        # 통계 업데이트
        if expected_fall and detected:
            tp += 1
        elif expected_fall and not detected:
            fn += 1
        elif not expected_fall and detected:
            fp += 1
        else:
            tn += 1

    mem_after = get_memory_usage()

    # 메트릭 계산
    times_np = np.array(times)
    mean_ms = float(np.mean(times_np))
    fps = 1000.0 / mean_ms if mean_ms > 0 else 0

    total = tp + fp + tn + fn
    accuracy = (tp + tn) / total if total > 0 else 0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0

    return BenchmarkResult(
        format_name=format_name,
        mean_ms=mean_ms,
        p50_ms=float(np.percentile(times_np, 50)),
        p95_ms=float(np.percentile(times_np, 95)),
        p99_ms=float(np.percentile(times_np, 99)),
        fps=fps,
        accuracy=accuracy,
        recall=recall,
        precision=precision,
        f1_score=f1,
        memory_mb=mem_after - mem_before,
        scenario_results=scenario_results,
    )


def run_dynamic_benchmark() -> tuple[BenchmarkResult, BenchmarkResult]:
    """동적 시퀀스 벤치마크 실행"""
    from app.services.fall_detector import FallDetector, KeypointFormat

    print("=" * 70)
    print("COCO 17pt vs MediaPipe 33pt 동적 시퀀스 벤치마크")
    print("=" * 70)
    print(f"시나리오: {len(DYNAMIC_SCENARIOS)}개")
    print(f"  - 낙상: {sum(1 for s in DYNAMIC_SCENARIOS.values() if s['expected_fall'])}개")
    print(f"  - 정상: {sum(1 for s in DYNAMIC_SCENARIOS.values() if not s['expected_fall'])}개")
    print()

    detector = FallDetector()

    # COCO 17 벤치마크
    print("Running COCO 17pt benchmark (dynamic sequences)...")
    coco17_result = benchmark_dynamic_format(
        detector,
        "COCO_17",
        KeypointFormat.COCO_17,
        use_mediapipe=False,
    )
    print(f"  Mean: {coco17_result.mean_ms:.3f}ms, FPS: {coco17_result.fps:.0f}")
    print(f"  Recall: {coco17_result.recall*100:.1f}%, Precision: {coco17_result.precision*100:.1f}%")

    # 새 detector 인스턴스 (상태 초기화)
    detector = FallDetector()

    # MediaPipe 33 벤치마크
    print("Running MediaPipe 33pt benchmark (dynamic sequences)...")
    mp33_result = benchmark_dynamic_format(
        detector,
        "MediaPipe_33",
        KeypointFormat.MEDIAPIPE_33,
        use_mediapipe=True,
    )
    print(f"  Mean: {mp33_result.mean_ms:.3f}ms, FPS: {mp33_result.fps:.0f}")
    print(f"  Recall: {mp33_result.recall*100:.1f}%, Precision: {mp33_result.precision*100:.1f}%")

    return coco17_result, mp33_result


def generate_dynamic_report(
    coco17: BenchmarkResult,
    mp33: BenchmarkResult,
    output_path: str | None = None,
) -> str:
    """동적 시퀀스 벤치마크 리포트 생성"""
    from datetime import datetime

    report = f"""# COCO 17pt vs MediaPipe 33pt 동적 시퀀스 벤치마크 리포트

Generated: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
Phase 27: YOLO Pose 17점 전환 검증 (동적 시퀀스)

## 테스트 시나리오

| 분류 | 시나리오 수 | 설명 |
|------|-----------|------|
| 낙상 | 8개 | 전방/후방/측면/걸림/느림/미끄러짐/무릎좌굴/침대 |
| 정상 | 10개 | 보행/앉기/줍기/스트레칭/침대눕기/휠체어/빠른앉기/빠른걷기/계단/전화 |
| 전조 | 3개 | 비틀거림/균형회복/무릎꺾임 (회복) |
| **총합** | **21개** | 동적 시퀀스 (각 25-45 프레임) |

## 성능 비교 요약

| 지표 | COCO 17pt | MediaPipe 33pt | 차이 |
|------|-----------|----------------|------|
| Mean (ms) | {coco17.mean_ms:.3f} | {mp33.mean_ms:.3f} | {coco17.mean_ms - mp33.mean_ms:+.3f} |
| P50 (ms) | {coco17.p50_ms:.3f} | {mp33.p50_ms:.3f} | {coco17.p50_ms - mp33.p50_ms:+.3f} |
| P95 (ms) | {coco17.p95_ms:.3f} | {mp33.p95_ms:.3f} | {coco17.p95_ms - mp33.p95_ms:+.3f} |
| P99 (ms) | {coco17.p99_ms:.3f} | {mp33.p99_ms:.3f} | {coco17.p99_ms - mp33.p99_ms:+.3f} |
| **FPS** | **{coco17.fps:.0f}** | **{mp33.fps:.0f}** | {coco17.fps - mp33.fps:+.0f} |

## 정확도 비교

| 지표 | COCO 17pt | MediaPipe 33pt | 차이 |
|------|-----------|----------------|------|
| **Accuracy** | **{coco17.accuracy*100:.1f}%** | **{mp33.accuracy*100:.1f}%** | {(coco17.accuracy - mp33.accuracy)*100:+.1f}% |
| **Recall (민감도)** | **{coco17.recall*100:.1f}%** | **{mp33.recall*100:.1f}%** | {(coco17.recall - mp33.recall)*100:+.1f}% |
| **Precision (정밀도)** | **{coco17.precision*100:.1f}%** | **{mp33.precision*100:.1f}%** | {(coco17.precision - mp33.precision)*100:+.1f}% |
| **F1 Score** | **{coco17.f1_score*100:.1f}%** | **{mp33.f1_score*100:.1f}%** | {(coco17.f1_score - mp33.f1_score)*100:+.1f}% |
| Memory (MB) | {coco17.memory_mb:.1f} | {mp33.memory_mb:.1f} | {coco17.memory_mb - mp33.memory_mb:+.1f} |

## 시나리오별 결과

### COCO 17pt 결과

| 시나리오 | 기대 | 감지 | 신뢰도 | 감지 프레임 | 결과 |
|---------|------|------|--------|-----------|------|
"""

    for name, result in coco17.scenario_results.items():
        expected = "낙상" if result.expected else "정상"
        detected = "감지" if result.detected else "미감지"
        frames_str = str(result.frames_to_detect) if result.frames_to_detect > 0 else "-"
        correct = "✅" if result.expected == result.detected else "❌"
        report += f"| {result.name} | {expected} | {detected} | {result.confidence:.2f} | {frames_str} | {correct} |\n"

    report += """
### MediaPipe 33pt 결과

| 시나리오 | 기대 | 감지 | 신뢰도 | 감지 프레임 | 결과 |
|---------|------|------|--------|-----------|------|
"""

    for name, result in mp33.scenario_results.items():
        expected = "낙상" if result.expected else "정상"
        detected = "감지" if result.detected else "미감지"
        frames_str = str(result.frames_to_detect) if result.frames_to_detect > 0 else "-"
        correct = "✅" if result.expected == result.detected else "❌"
        report += f"| {result.name} | {expected} | {detected} | {result.confidence:.2f} | {frames_str} | {correct} |\n"

    # 분석 섹션
    report += f"""
## 분석

### 속도 분석
"""

    if coco17.mean_ms < mp33.mean_ms:
        speed_diff = (mp33.mean_ms / coco17.mean_ms - 1) * 100
        report += f"- **COCO 17pt가 {speed_diff:.1f}% 더 빠름**\n"
    else:
        speed_diff = (coco17.mean_ms / mp33.mean_ms - 1) * 100
        report += f"- MediaPipe 33pt가 {speed_diff:.1f}% 더 빠름 (변환 없음)\n"

    report += f"""
### 정확도 분석

- **COCO 17pt Recall**: {coco17.recall*100:.1f}% (8개 낙상 중 {int(coco17.recall * 8)}개 감지)
- **MediaPipe 33pt Recall**: {mp33.recall*100:.1f}% (8개 낙상 중 {int(mp33.recall * 8)}개 감지)
"""

    # FNR (미탐률) 계산
    fnr_coco = (1 - coco17.recall) * 100
    fnr_mp = (1 - mp33.recall) * 100

    report += f"""
- **COCO 17pt FNR (미탐률)**: {fnr_coco:.1f}%
- **MediaPipe 33pt FNR (미탐률)**: {fnr_mp:.1f}%

### 결론

"""

    # 결론 로직
    if coco17.recall >= 0.875 and coco17.precision >= 0.7:
        report += f"""**COCO 17점 포맷 사용 가능**

- Recall {coco17.recall*100:.1f}% 달성 (목표: ≥87.5%)
- Precision {coco17.precision*100:.1f}% (오탐 허용 범위)
- YOLO Pose 17점만으로 낙상 감지 가능
- MediaPipe ROI 처리 생략 시 추가 성능 향상 기대
"""
    elif coco17.recall >= mp33.recall * 0.95:
        report += f"""**COCO 17점과 MediaPipe 33점 동등 수준**

- 두 포맷 모두 유사한 정확도 ({coco17.recall*100:.1f}% vs {mp33.recall*100:.1f}%)
- YOLO Pose 17점 직접 사용 시 MediaPipe 의존성 제거 가능
- 하이브리드 구조 유지도 유효
"""
    else:
        report += f"""**MediaPipe 33점 유지 권장**

- MediaPipe 33점 Recall이 더 높음 ({mp33.recall*100:.1f}% vs {coco17.recall*100:.1f}%)
- 현재 YOLO → MediaPipe ROI 하이브리드 구조 유지 권장
- 추후 규칙 튜닝으로 COCO 17점 성능 개선 가능
"""

    if output_path:
        Path(output_path).write_text(report, encoding="utf-8")
        print(f"\n리포트 저장: {output_path}")

    return report


def main():
    parser = argparse.ArgumentParser(
        description="COCO 17pt vs MediaPipe 33pt 동적 시퀀스 벤치마크"
    )
    parser.add_argument(
        "--output", type=str, default=None,
        help="리포트 저장 경로 (default: docs/keypoint_benchmark.md)"
    )
    parser.add_argument(
        "--dynamic-only", action="store_true",
        help="동적 시퀀스만 테스트 (기본값)"
    )
    args = parser.parse_args()

    output_path = args.output or str(project_root / "docs" / "keypoint_benchmark.md")

    coco17, mp33 = run_dynamic_benchmark()
    report = generate_dynamic_report(coco17, mp33, output_path=output_path)

    print()
    print(report)


if __name__ == "__main__":
    main()
