#!/usr/bin/env python3
"""
SENTIO Pipeline Benchmark
==============================

Multi-person fall detection pipeline performance measurement tool.

Pipeline stages:
  1. YOLO11n-pose detection (MultiPersonDetector)
  2. MediaPipe ROI extraction (PoseService per-person)
  3. FallDetector rule-based + ML ensemble (per-person)
  4. PostureClassifier (per-person, called within FallDetector)
  5. AlertManager state machine (per-person)

Usage:
  python scripts/benchmark_pipeline.py --synthetic
  python scripts/benchmark_pipeline.py --frames 200
  python scripts/benchmark_pipeline.py --video demo_videos/FY_front_fall_trip.mp4
  python scripts/benchmark_pipeline.py --full --frames 50
  python scripts/benchmark_pipeline.py --ensemble --frames 60
  python scripts/benchmark_pipeline.py --ensemble --combos A,F --frames 30
"""

import argparse
import math
import os
import random
import statistics
import sys
import time
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _SCRIPT_DIR.parent
_BACKEND_DIR = _PROJECT_ROOT / "backend"

sys.path.insert(0, str(_BACKEND_DIR))

os.environ.setdefault("LOG_LEVEL", "WARNING")


# ---------------------------------------------------------------------------
# Statistics helpers
# ---------------------------------------------------------------------------

def percentile(data, pct):
    """Calculate the p-th percentile of a list of values."""
    if not data:
        return 0.0
    sorted_data = sorted(data)
    k = (len(sorted_data) - 1) * (pct / 100.0)
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return sorted_data[int(k)]
    d0 = sorted_data[f] * (c - k)
    d1 = sorted_data[c] * (k - f)
    return d0 + d1


def format_ms(value):
    """Format a millisecond value to a fixed-width string."""
    return f"{value:8.2f}"


def print_header(title):
    print()
    print("=" * 60)
    print(f"  {title}")
    print("=" * 60)


def print_section(title):
    print()
    print(f"--- {title} ---")


def print_stats_table(rows, label_key="label", show_fps=True):
    """Print a formatted statistics table."""
    h = [
        f"{'Label':<16}",
        f"{'Mean (ms)':>10}",
        f"{'P50 (ms)':>10}",
        f"{'P95 (ms)':>10}",
        f"{'P99 (ms)':>10}",
        f"{'Max (ms)':>10}",
    ]
    if show_fps:
        h.append(f"{'FPS':>8}")
    header = " | ".join(h)
    separator = "-" * len(header)
    print(header)
    print(separator)
    for row in rows:
        parts = [
            f"{row[label_key]:<16}",
            format_ms(row["mean"]),
            format_ms(row["p50"]),
            format_ms(row["p95"]),
            format_ms(row["p99"]),
            format_ms(row["max"]),
        ]
        if show_fps:
            fps_val = row.get("fps", 0)
            parts.append(f"{fps_val:>8.1f}" if fps_val > 0 else f"{'N/A':>8}")
        print("   ".join(parts))


def compute_stats(timings):
    """Compute mean, p50, p95, p99, max, fps from a list of ms timings."""
    if not timings:
        return {"mean": 0, "p50": 0, "p95": 0, "p99": 0, "max": 0, "fps": 0}
    mean_val = statistics.mean(timings)
    return {
        "mean": mean_val,
        "p50": percentile(timings, 50),
        "p95": percentile(timings, 95),
        "p99": percentile(timings, 99),
        "max": max(timings),
        "fps": 1000.0 / mean_val if mean_val > 0 else 0,
    }


# ---------------------------------------------------------------------------
# Landmark generators
# ---------------------------------------------------------------------------

_STANDING_Y_VALUES = [
    0.10, 0.09, 0.09, 0.09, 0.09, 0.09, 0.09, 0.11, 0.11, 0.13, 0.13,
    0.20, 0.20, 0.30, 0.30, 0.40, 0.40, 0.42, 0.42, 0.41, 0.41, 0.43,
    0.43, 0.45, 0.45, 0.65, 0.65, 0.85, 0.85, 0.87, 0.87, 0.89, 0.89,
]
_LEFT_INDICES = frozenset({1, 2, 3, 7, 9, 11, 13, 15, 17, 19, 21, 23, 25, 27, 29, 31})
_RIGHT_INDICES = frozenset({4, 5, 6, 8, 10, 12, 14, 16, 18, 20, 22, 24, 26, 28, 30, 32})


def generate_standing_landmarks():
    """Generate mock MediaPipe 33-point landmarks for a standing person."""
    landmarks = []
    for i, y in enumerate(_STANDING_Y_VALUES):
        if i in _LEFT_INDICES:
            x_base = 0.45
        elif i in _RIGHT_INDICES:
            x_base = 0.55
        else:
            x_base = 0.50
        landmarks.append({"x": x_base, "y": y, "z": 0.0, "visibility": 0.95})
    return landmarks


def generate_falling_landmarks(progress=1.0):
    """Generate landmarks for a person mid-fall (0=standing, 1=fallen)."""
    standing = generate_standing_landmarks()
    fallen = []
    for lm in standing:
        new_y = lm["y"] + progress * (0.6 - lm["y"]) * 0.5
        new_x = lm["x"] + progress * (lm["y"] - 0.5) * 0.4
        fallen.append({
            "x": max(0.0, min(1.0, new_x)),
            "y": max(0.0, min(1.0, new_y)),
            "z": lm["z"],
            "visibility": lm["visibility"],
        })
    return fallen


def add_noise(landmarks, noise_level=0.005):
    """Add small random noise to landmarks to simulate detection jitter."""
    noisy = []
    for lm in landmarks:
        noisy.append({
            "x": lm["x"] + random.gauss(0, noise_level),
            "y": lm["y"] + random.gauss(0, noise_level),
            "z": lm["z"] + random.gauss(0, noise_level * 0.5),
            "visibility": max(0.0, min(1.0, lm["visibility"] + random.gauss(0, 0.02))),
        })
    return noisy


# ---------------------------------------------------------------------------
# Ensemble scenario landmark generators (21 scenarios)
# ---------------------------------------------------------------------------

def _lerp_landmarks(lm_a, lm_b, t):
    """Linearly interpolate between two landmark sets (t=0 -> lm_a, t=1 -> lm_b)."""
    result = []
    for a, b in zip(lm_a, lm_b):
        result.append({
            "x": a["x"] + (b["x"] - a["x"]) * t,
            "y": a["y"] + (b["y"] - a["y"]) * t,
            "z": a["z"] + (b["z"] - a["z"]) * t,
            "visibility": a["visibility"],
        })
    return result


def _generate_sitting_landmarks():
    """Generate landmarks for a person sitting in a chair."""
    lm = generate_standing_landmarks()
    # Head stays roughly same, hips come up (knees bend at ~90 degrees)
    # Sitting: head ~0.15, shoulders ~0.25, hips ~0.45, knees ~0.60, ankles ~0.85
    adjustments = {
        0: 0.15,   # nose
        11: 0.25, 12: 0.25,  # shoulders
        23: 0.45, 24: 0.45,  # hips
        25: 0.60, 26: 0.60,  # knees
        27: 0.85, 28: 0.85,  # ankles
    }
    for idx, new_y in adjustments.items():
        lm[idx]["y"] = new_y
    return lm


def _generate_bending_landmarks():
    """Generate landmarks for a person bending forward (picking something up)."""
    lm = generate_standing_landmarks()
    # Head drops forward and down, shoulders follow
    lm[0]["y"] = 0.50   # nose drops
    lm[0]["x"] = 0.55   # forward
    lm[11]["y"] = 0.40
    lm[12]["y"] = 0.40
    lm[11]["x"] = 0.48
    lm[12]["x"] = 0.58
    # Hips stay roughly same
    lm[23]["y"] = 0.42
    lm[24]["y"] = 0.42
    return lm


def _generate_stretching_landmarks():
    """Generate landmarks for a person stretching arms above head."""
    lm = generate_standing_landmarks()
    # Arms go up: wrists above head
    lm[15]["y"] = 0.05  # left wrist
    lm[16]["y"] = 0.05  # right wrist
    lm[15]["x"] = 0.40
    lm[16]["x"] = 0.60
    return lm


def _generate_bed_lying_landmarks():
    """Generate landmarks for a person lying in bed (stable, not fallen)."""
    lm = generate_standing_landmarks()
    # Everything at roughly the same Y (horizontal), spread in X
    base_y = 0.50
    for i in range(33):
        lm[i]["y"] = base_y + random.uniform(-0.03, 0.03)
        lm[i]["x"] = 0.2 + (i / 32.0) * 0.6
    return lm


def _generate_wheelchair_landmarks():
    """Generate landmarks for a person in a wheelchair (sitting, slightly reclined)."""
    lm = _generate_sitting_landmarks()
    # Slight recline
    lm[0]["y"] = 0.18
    lm[11]["y"] = 0.28
    lm[12]["y"] = 0.28
    return lm


def _generate_fast_walk_landmarks(phase):
    """Generate landmarks for fast walking (larger arm swing, stride)."""
    lm = generate_standing_landmarks()
    swing = math.sin(phase * math.pi * 2) * 0.08
    lm[15]["y"] = 0.40 + swing  # left wrist
    lm[16]["y"] = 0.40 - swing  # right wrist
    lm[27]["x"] = 0.45 + swing * 0.5  # left ankle
    lm[28]["x"] = 0.55 - swing * 0.5  # right ankle
    # Slight vertical bob
    for i in range(33):
        lm[i]["y"] += abs(math.sin(phase * math.pi * 4)) * 0.01
    return lm


def _generate_stairs_landmarks(phase):
    """Generate landmarks for climbing stairs."""
    lm = generate_standing_landmarks()
    step = math.sin(phase * math.pi * 2) * 0.05
    # One knee lifts higher
    lm[25]["y"] = 0.65 - abs(step) * 2  # left knee lifts
    lm[27]["y"] = 0.85 - abs(step) * 2  # left ankle lifts
    # Body tilts slightly
    for i in range(33):
        lm[i]["y"] -= phase * 0.002  # gradually ascending
    return lm


def _generate_phone_call_landmarks():
    """Generate landmarks for a person standing and talking on the phone."""
    lm = generate_standing_landmarks()
    # One hand raised to ear
    lm[16]["y"] = 0.10  # right wrist near head
    lm[16]["x"] = 0.52
    return lm


def _generate_forward_fall_landmarks(progress):
    """Forward fall: head drops forward and down rapidly."""
    lm = generate_standing_landmarks()
    t = min(progress, 1.0)
    # Head plunges forward and down
    lm[0]["y"] = 0.10 + t * 0.70  # nose goes from 0.10 to 0.80
    lm[0]["x"] = 0.50 + t * 0.15  # forward shift
    # Shoulders follow
    lm[11]["y"] = 0.20 + t * 0.50
    lm[12]["y"] = 0.20 + t * 0.50
    lm[11]["x"] = 0.45 + t * 0.10
    lm[12]["x"] = 0.55 + t * 0.10
    # Hips rise slightly then flatten
    lm[23]["y"] = 0.42 + t * 0.30
    lm[24]["y"] = 0.42 + t * 0.30
    # Knees buckle
    lm[25]["y"] = 0.65 + t * 0.15
    lm[26]["y"] = 0.65 + t * 0.15
    return lm


def _generate_backward_fall_landmarks(progress):
    """Backward fall: person tips backward."""
    lm = generate_standing_landmarks()
    t = min(progress, 1.0)
    # Head goes backward
    lm[0]["y"] = 0.10 + t * 0.55
    lm[0]["x"] = 0.50 - t * 0.20
    # Shoulders
    lm[11]["y"] = 0.20 + t * 0.45
    lm[12]["y"] = 0.20 + t * 0.45
    # Hips
    lm[23]["y"] = 0.42 + t * 0.30
    lm[24]["y"] = 0.42 + t * 0.30
    # Feet come up
    lm[27]["y"] = 0.85 - t * 0.20
    lm[28]["y"] = 0.85 - t * 0.20
    return lm


def _generate_side_fall_landmarks(progress):
    """Side fall: person tips to the side."""
    lm = generate_standing_landmarks()
    t = min(progress, 1.0)
    # Lateral shift
    lateral = t * 0.35
    for i in range(33):
        lm[i]["x"] += lateral
    # Head drops
    lm[0]["y"] = 0.10 + t * 0.55
    # Shoulders tilt dramatically
    lm[11]["y"] = 0.20 + t * 0.50
    lm[12]["y"] = 0.20 + t * 0.10
    # Hips follow
    lm[23]["y"] = 0.42 + t * 0.30
    lm[24]["y"] = 0.42 + t * 0.10
    return lm


def _generate_trip_fall_landmarks(progress):
    """Trip and fall: stumble then fall forward."""
    lm = generate_standing_landmarks()
    t = min(progress, 1.0)
    if t < 0.3:
        # Stumble phase: slight forward lean
        s = t / 0.3
        lm[0]["y"] = 0.10 + s * 0.10
        lm[0]["x"] = 0.50 + s * 0.05
    else:
        # Fall phase: rapid descent
        s = (t - 0.3) / 0.7
        lm[0]["y"] = 0.20 + s * 0.60
        lm[0]["x"] = 0.55 + s * 0.10
        lm[11]["y"] = 0.20 + s * 0.50
        lm[12]["y"] = 0.20 + s * 0.50
        lm[23]["y"] = 0.42 + s * 0.30
        lm[24]["y"] = 0.42 + s * 0.30
        # Ankle catches
        lm[27]["y"] = 0.85 + s * 0.05
        lm[28]["y"] = 0.85 - s * 0.10
    return lm


def _generate_slow_fall_landmarks(progress):
    """Slow collapse: gradual sinking (e.g., fainting)."""
    lm = generate_standing_landmarks()
    t = min(progress, 1.0)
    # Everything sinks slowly and uniformly
    for i in range(33):
        lm[i]["y"] = lm[i]["y"] + t * (0.65 - lm[i]["y"]) * 0.7
    return lm


def _generate_bed_fall_landmarks(progress):
    """Fall from bed: start lying, then roll off edge."""
    lm = _generate_bed_lying_landmarks()
    t = min(progress, 1.0)
    if t < 0.4:
        # Rolling toward edge
        s = t / 0.4
        for i in range(33):
            lm[i]["x"] += s * 0.15
    else:
        # Falling off
        s = (t - 0.4) / 0.6
        for i in range(33):
            lm[i]["x"] += 0.15
            lm[i]["y"] = lm[i]["y"] + s * 0.30
        # Head drops more
        lm[0]["y"] += s * 0.20
    return lm


def _generate_knee_buckle_fall_landmarks(progress):
    """Knee buckle fall: knees give out, person collapses downward."""
    lm = generate_standing_landmarks()
    t = min(progress, 1.0)
    # Knees bend rapidly
    knee_bend = t * 0.35
    lm[25]["y"] = 0.65 + knee_bend
    lm[26]["y"] = 0.65 + knee_bend
    # Body drops
    drop = t * 0.50
    lm[0]["y"] = 0.10 + drop
    lm[11]["y"] = 0.20 + drop * 0.8
    lm[12]["y"] = 0.20 + drop * 0.8
    lm[23]["y"] = 0.42 + drop * 0.6
    lm[24]["y"] = 0.42 + drop * 0.6
    return lm


def _generate_slip_fall_landmarks(progress):
    """Slip and fall: feet shoot forward, person falls backward."""
    lm = generate_standing_landmarks()
    t = min(progress, 1.0)
    # Feet slide forward
    lm[27]["x"] = 0.45 + t * 0.20
    lm[28]["x"] = 0.55 + t * 0.20
    lm[27]["y"] = 0.85 - t * 0.10
    lm[28]["y"] = 0.85 - t * 0.10
    # Head/body goes backward and down
    lm[0]["y"] = 0.10 + t * 0.55
    lm[0]["x"] = 0.50 - t * 0.15
    lm[11]["y"] = 0.20 + t * 0.40
    lm[12]["y"] = 0.20 + t * 0.40
    lm[23]["y"] = 0.42 + t * 0.25
    lm[24]["y"] = 0.42 + t * 0.25
    return lm


def _generate_stumble_landmarks(progress):
    """Stumble: momentary loss of balance, but recovers."""
    lm = generate_standing_landmarks()
    t = min(progress, 1.0)
    if t < 0.5:
        # Forward lurch
        s = t / 0.5
        lm[0]["y"] = 0.10 + s * 0.15
        lm[0]["x"] = 0.50 + s * 0.08
        lm[11]["y"] = 0.20 + s * 0.08
        lm[12]["y"] = 0.20 + s * 0.08
    else:
        # Recovery
        s = (t - 0.5) / 0.5
        lm[0]["y"] = 0.25 - s * 0.15
        lm[0]["x"] = 0.58 - s * 0.08
        lm[11]["y"] = 0.28 - s * 0.08
        lm[12]["y"] = 0.28 - s * 0.08
    return lm


def _generate_balance_recovery_landmarks(progress):
    """Balance recovery: sway to one side then correct."""
    lm = generate_standing_landmarks()
    t = min(progress, 1.0)
    # Sway and recover
    sway = math.sin(t * math.pi) * 0.12
    lm[0]["x"] = 0.50 + sway
    lm[11]["x"] = 0.45 + sway * 0.8
    lm[12]["x"] = 0.55 + sway * 0.8
    # Slight head drop during sway
    lm[0]["y"] = 0.10 + abs(sway) * 0.8
    lm[11]["y"] = 0.20 + abs(sway) * 0.4
    lm[12]["y"] = 0.20 + abs(sway) * 0.4
    return lm


def _generate_knee_slight_bend_landmarks(progress):
    """Slight knee bend: knees start to buckle but person catches self."""
    lm = generate_standing_landmarks()
    t = min(progress, 1.0)
    if t < 0.6:
        # Knees bend
        s = t / 0.6
        bend = s * 0.15
        lm[25]["y"] = 0.65 + bend
        lm[26]["y"] = 0.65 + bend
        lm[0]["y"] = 0.10 + s * 0.12
        lm[23]["y"] = 0.42 + s * 0.08
        lm[24]["y"] = 0.42 + s * 0.08
    else:
        # Recover
        s = (t - 0.6) / 0.4
        bend = 0.15 * (1 - s)
        lm[25]["y"] = 0.65 + bend
        lm[26]["y"] = 0.65 + bend
        lm[0]["y"] = 0.10 + 0.12 * (1 - s)
        lm[23]["y"] = 0.42 + 0.08 * (1 - s)
        lm[24]["y"] = 0.42 + 0.08 * (1 - s)
    return lm


# ---------------------------------------------------------------------------
# Ensemble scenario definitions
# ---------------------------------------------------------------------------

ENSEMBLE_COMBOS = {
    "A": {"rule_weight": 1.0, "ml_weight": 0.0, "enhanced": False,
           "desc": "Rule 4 conditions only (max speed)"},
    "B": {"rule_weight": 0.7, "ml_weight": 0.3, "enhanced": False,
           "desc": "Rule-focused"},
    "C": {"rule_weight": 0.5, "ml_weight": 0.5, "enhanced": False,
           "desc": "Current setting (baseline)"},
    "D": {"rule_weight": 0.3, "ml_weight": 0.7, "enhanced": False,
           "desc": "ML-focused"},
    "E": {"rule_weight": 0.0, "ml_weight": 1.0, "enhanced": False,
           "desc": "ML only"},
    "F": {"rule_weight": 1.0, "ml_weight": 0.0, "enhanced": True,
           "desc": "Rule-enhanced 10 conditions"},
}

# Scenarios grouped by expected outcome
FALL_SCENARIOS = [
    "forward_fall", "backward_fall", "side_fall", "trip",
    "slow_fall", "bed_fall", "knee_buckle_fall", "slip",
]
NORMAL_SCENARIOS = [
    "walking", "sitting", "bending", "stretching", "bed_lying",
    "wheelchair", "fast_sit", "fast_walk", "stairs", "phone_call",
]
PRE_IMPACT_SCENARIOS = [
    "stumble", "balance_recovery", "knee_slight_bend",
]
ALL_SCENARIOS = FALL_SCENARIOS + NORMAL_SCENARIOS + PRE_IMPACT_SCENARIOS


def generate_scenario_landmarks(scenario, frame_idx, num_frames):
    """Generate landmarks for a given scenario at the given frame index.

    For fall scenarios, the first 30% of frames show standing, then a
    progressive fall develops over the remaining 70%.
    For normal scenarios, the full sequence shows the normal activity.
    For pre-impact scenarios, the sequence shows a near-fall with recovery.
    """
    t = frame_idx / max(num_frames - 1, 1)  # 0..1 over sequence

    # --- Fall scenarios ---
    if scenario == "forward_fall":
        if t < 0.3:
            return generate_standing_landmarks()
        prog = (t - 0.3) / 0.7
        return _generate_forward_fall_landmarks(prog)

    elif scenario == "backward_fall":
        if t < 0.3:
            return generate_standing_landmarks()
        prog = (t - 0.3) / 0.7
        return _generate_backward_fall_landmarks(prog)

    elif scenario == "side_fall":
        if t < 0.3:
            return generate_standing_landmarks()
        prog = (t - 0.3) / 0.7
        return _generate_side_fall_landmarks(prog)

    elif scenario == "trip":
        if t < 0.2:
            return generate_standing_landmarks()
        prog = (t - 0.2) / 0.8
        return _generate_trip_fall_landmarks(prog)

    elif scenario == "slow_fall":
        if t < 0.2:
            return generate_standing_landmarks()
        prog = (t - 0.2) / 0.8
        return _generate_slow_fall_landmarks(prog)

    elif scenario == "bed_fall":
        return _generate_bed_fall_landmarks(t)

    elif scenario == "knee_buckle_fall":
        if t < 0.3:
            return generate_standing_landmarks()
        prog = (t - 0.3) / 0.7
        return _generate_knee_buckle_fall_landmarks(prog)

    elif scenario == "slip":
        if t < 0.25:
            return generate_standing_landmarks()
        prog = (t - 0.25) / 0.75
        return _generate_slip_fall_landmarks(prog)

    # --- Normal scenarios ---
    elif scenario == "walking":
        lm = generate_standing_landmarks()
        swing = math.sin(t * math.pi * 4) * 0.03
        lm[15]["y"] = 0.40 + swing
        lm[16]["y"] = 0.40 - swing
        return lm

    elif scenario == "sitting":
        return _generate_sitting_landmarks()

    elif scenario == "bending":
        if t < 0.3:
            return generate_standing_landmarks()
        elif t < 0.7:
            prog = (t - 0.3) / 0.4
            return _lerp_landmarks(generate_standing_landmarks(),
                                   _generate_bending_landmarks(), prog)
        else:
            prog = (t - 0.7) / 0.3
            return _lerp_landmarks(_generate_bending_landmarks(),
                                   generate_standing_landmarks(), prog)

    elif scenario == "stretching":
        return _generate_stretching_landmarks()

    elif scenario == "bed_lying":
        return _generate_bed_lying_landmarks()

    elif scenario == "wheelchair":
        return _generate_wheelchair_landmarks()

    elif scenario == "fast_sit":
        # Quick transition from standing to sitting
        if t < 0.4:
            return generate_standing_landmarks()
        elif t < 0.7:
            prog = (t - 0.4) / 0.3
            return _lerp_landmarks(generate_standing_landmarks(),
                                   _generate_sitting_landmarks(), prog)
        else:
            return _generate_sitting_landmarks()

    elif scenario == "fast_walk":
        return _generate_fast_walk_landmarks(t)

    elif scenario == "stairs":
        return _generate_stairs_landmarks(t)

    elif scenario == "phone_call":
        return _generate_phone_call_landmarks()

    # --- Pre-impact scenarios ---
    elif scenario == "stumble":
        return _generate_stumble_landmarks(t)

    elif scenario == "balance_recovery":
        return _generate_balance_recovery_landmarks(t)

    elif scenario == "knee_slight_bend":
        return _generate_knee_slight_bend_landmarks(t)

    else:
        return generate_standing_landmarks()


# ---------------------------------------------------------------------------
# Benchmark: Synthetic mode
# ---------------------------------------------------------------------------

def benchmark_synthetic(num_frames):
    """Benchmark FallDetector + PostureClassifier with synthetic landmarks."""
    print_header("SENTIO Pipeline Benchmark")
    print(f"Mode: synthetic (N persons scaling)")
    print(f"Frames: {num_frames}")

    try:
        from app.services.fall_detector import FallDetector
        from app.services.posture_classifier import PostureClassifier
        from app.services.fall_classifier import FallClassifier
        from app.services.alert_manager import AlertManager
    except ImportError as e:
        print(f"\n[ERROR] Failed to import backend services: {e}")
        print("Make sure you run from project root with deps installed.")
        sys.exit(1)

    person_counts = [1, 2, 3, 5]

    # --- Fall Detector Scaling ---
    print_section("Fall Detector Scaling (rule-based + ML ensemble)")
    fd_rows = []
    for n_persons in person_counts:
        detector = FallDetector()
        timings = []
        for frame_idx in range(num_frames):
            plms = []
            for p in range(n_persons):
                if frame_idx > num_frames * 0.7 and p == 0:
                    prog = (frame_idx - num_frames * 0.7) / (num_frames * 0.3)
                    lm = generate_falling_landmarks(min(prog, 1.0))
                else:
                    lm = generate_standing_landmarks()
                plms.append(add_noise(lm))
            t0 = time.perf_counter()
            for p_idx, lm in enumerate(plms):
                detector.detect(lm, f"person_{p_idx}")
            timings.append((time.perf_counter() - t0) * 1000.0)
        stats = compute_stats(timings)
        stats["label"] = f"{n_persons} person(s)"
        fd_rows.append(stats)
    print_stats_table(fd_rows)

    # --- Alert Manager Scaling ---
    print_section("Alert Manager Scaling")
    am_rows = []
    for n_persons in person_counts:
        mgr = AlertManager()
        timings = []
        for frame_idx in range(num_frames):
            t0 = time.perf_counter()
            for p_idx in range(n_persons):
                pid = f"person_{p_idx}"
                fallen = frame_idx > num_frames * 0.7 and p_idx == 0
                conf = 0.85 if fallen else 0.1
                dur = (frame_idx - num_frames * 0.7) / 30.0 if fallen else 0.0
                ft = "front_fall" if fallen else "normal"
                mgr.update(person_id=pid, is_fallen=fallen, confidence=conf,
                           fall_duration=max(0, dur), fall_type=ft)
            timings.append((time.perf_counter() - t0) * 1000.0)
        stats = compute_stats(timings)
        stats["label"] = f"{n_persons} person(s)"
        am_rows.append(stats)
    print_stats_table(am_rows)

    # --- Posture Classifier Standalone ---
    print_section("Posture Classifier Standalone")
    pc_rows = []
    for n_persons in person_counts:
        clf = PostureClassifier()
        timings = []
        for _ in range(num_frames):
            plms = [add_noise(generate_standing_landmarks()) for _ in range(n_persons)]
            t0 = time.perf_counter()
            for p_idx, lm in enumerate(plms):
                clf.classify(lm, f"person_{p_idx}")
            timings.append((time.perf_counter() - t0) * 1000.0)
        stats = compute_stats(timings)
        stats["label"] = f"{n_persons} person(s)"
        pc_rows.append(stats)
    print_stats_table(pc_rows)

    # --- Combined Pipeline ---
    print_section("Combined Pipeline (FallDetect + AlertManager) per frame")
    combined_rows = []
    for n_persons in person_counts:
        det = FallDetector()
        mgr = AlertManager()
        timings = []
        for frame_idx in range(num_frames):
            plms = []
            for p in range(n_persons):
                if frame_idx > num_frames * 0.7 and p == 0:
                    prog = (frame_idx - num_frames * 0.7) / (num_frames * 0.3)
                    lm = generate_falling_landmarks(min(prog, 1.0))
                else:
                    lm = generate_standing_landmarks()
                plms.append(add_noise(lm))
            t0 = time.perf_counter()
            for p_idx, lm in enumerate(plms):
                pid = f"person_{p_idx}"
                res = det.detect(lm, pid)
                mgr.update(person_id=pid, is_fallen=res["is_fallen"],
                           confidence=res["confidence"],
                           fall_duration=res["fall_duration"],
                           fall_type=res["fall_type"])
            timings.append((time.perf_counter() - t0) * 1000.0)
        stats = compute_stats(timings)
        stats["label"] = f"{n_persons} person(s)"
        combined_rows.append(stats)
    print_stats_table(combined_rows)

    # --- Summary ---
    print_section("Summary")
    _m = "mean"
    _f = "fps"
    print(f"  Fall Detector (1 person):     {fd_rows[0][_m]:.2f} ms/frame  "
          f"({fd_rows[0][_f]:.0f} FPS)")
    print(f"  Fall Detector (5 persons):    {fd_rows[3][_m]:.2f} ms/frame  "
          f"({fd_rows[3][_f]:.0f} FPS)")
    print(f"  Alert Manager (1 person):     {am_rows[0][_m]:.2f} ms/frame  "
          f"({am_rows[0][_f]:.0f} FPS)")
    print(f"  Combined (5 persons):         {combined_rows[3][_m]:.2f} ms/frame  "
          f"({combined_rows[3][_f]:.0f} FPS)")
    print()
    budget_30fps = 1000.0 / 30.0
    combined_5p = combined_rows[3]["p95"]
    status = "PASS" if combined_5p < budget_30fps else "OVER BUDGET"
    print(f"  30 FPS budget: {budget_30fps:.1f} ms | "
          f"Combined P95 (5 persons): {combined_5p:.2f} ms  [{status}]")
    print()


# ---------------------------------------------------------------------------
# Benchmark: Full pipeline with video
# ---------------------------------------------------------------------------

def benchmark_full_pipeline(video_path, num_frames):
    """Benchmark full pipeline with YOLO + MediaPipe on a real video."""
    print_header("SENTIO Pipeline Benchmark")
    print(f"Mode: full pipeline (video)")
    print(f"Video: {video_path}")
    print(f"Frames: {num_frames}")

    if not Path(video_path).exists():
        print(f"\n[ERROR] Video file not found: {video_path}")
        sys.exit(1)

    try:
        import cv2
    except ImportError:
        print("\n[ERROR] opencv-python is required for video mode.")
        sys.exit(1)

    try:
        from app.services.fall_detector import FallDetector
        from app.services.alert_manager import AlertManager
    except ImportError as e:
        print(f"\n[ERROR] Failed to import backend services: {e}")
        sys.exit(1)

    # Check YOLO
    yolo_available = False
    mpd = None
    try:
        from app.services.multi_person_detector import MultiPersonDetector
        mpd = MultiPersonDetector()
        yolo_available = mpd.enabled
    except ImportError:
        pass
    if not yolo_available:
        print("\n[NOTE] ultralytics not installed. YOLO benchmark skipped.")
        print("       Install: pip install ultralytics")

    # Check MediaPipe
    mp_available = False
    pose_svc = None
    try:
        from app.services.pose_service import PoseService
        pose_svc = PoseService()
        mp_available = True
    except ImportError:
        print("\n[NOTE] mediapipe not installed. MediaPipe benchmark skipped.")

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print(f"\n[ERROR] Cannot open video: {video_path}")
        sys.exit(1)

    vfps = cap.get(cv2.CAP_PROP_FPS)
    vtotal = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    vw = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    vh = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    print(f"Video info: {vw}x{vh} @ {vfps:.1f} FPS, {vtotal} frames")

    fd = FallDetector()
    am = AlertManager()

    yolo_times, mp_times, fd_times, am_times, total_times = [], [], [], [], []
    persons_per_frame = []
    processed = 0
    print("\nProcessing frames...", end="", flush=True)

    while processed < num_frames:
        ret, frame = cap.read()
        if not ret:
            cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            ret, frame = cap.read()
            if not ret:
                break

        t_total = time.perf_counter()

        # Stage 1: YOLO
        det_persons = []
        if yolo_available and mpd is not None:
            t0 = time.perf_counter()
            yr = mpd.detect(frame)
            yolo_times.append((time.perf_counter() - t0) * 1000.0)
            det_persons = yr.persons
            persons_per_frame.append(len(det_persons))
        else:
            persons_per_frame.append(0)

        # Stage 2: MediaPipe
        lm_list = []
        if mp_available and pose_svc is not None:
            if yolo_available and det_persons:
                t0 = time.perf_counter()
                for person in det_persons:
                    plm = pose_svc.process_roi_sync(
                        frame, person.bbox, f"person_{person.track_id}")
                    if plm is not None:
                        lm_list.append((f"person_{person.track_id}", plm.landmarks))
                mp_times.append((time.perf_counter() - t0) * 1000.0)
            else:
                t0 = time.perf_counter()
                pr = pose_svc.process_frame_sync(frame)
                mp_times.append((time.perf_counter() - t0) * 1000.0)
                for plm in pr.poses:
                    lm_list.append((plm.person_id, plm.landmarks))
                if not yolo_available:
                    persons_per_frame[-1] = len(pr.poses)

        # Stage 3: Fall Detection
        fall_res = []
        t0 = time.perf_counter()
        for pid, lm in lm_list:
            res = fd.detect(lm, pid)
            fall_res.append((pid, res))
        fd_times.append((time.perf_counter() - t0) * 1000.0)

        # Stage 4: Alert Manager
        t0 = time.perf_counter()
        for pid, res in fall_res:
            am.update(person_id=pid, is_fallen=res["is_fallen"],
                      confidence=res["confidence"],
                      fall_duration=res["fall_duration"],
                      fall_type=res["fall_type"])
        am_times.append((time.perf_counter() - t0) * 1000.0)

        total_times.append((time.perf_counter() - t_total) * 1000.0)
        processed += 1
        if processed % 25 == 0:
            print(".", end="", flush=True)

    cap.release()
    if pose_svc is not None:
        pose_svc.close()
    if mpd is not None:
        mpd.close()

    print(f" done ({processed} frames)")

    # Results
    print_section("Per-Stage Latency")
    rows = []
    if yolo_times:
        s = compute_stats(yolo_times)
        s["label"] = "YOLO11n-pose"
        rows.append(s)
    else:
        rows.append({"label": "YOLO11n-pose", "mean": 0, "p50": 0,
                      "p95": 0, "p99": 0, "max": 0, "fps": 0})
        print("  (YOLO skipped - ultralytics not installed)")
    if mp_times:
        s = compute_stats(mp_times)
        s["label"] = "MediaPipe"
        rows.append(s)
    else:
        rows.append({"label": "MediaPipe", "mean": 0, "p50": 0,
                      "p95": 0, "p99": 0, "max": 0, "fps": 0})
        print("  (MediaPipe skipped - not installed)")
    if fd_times:
        s = compute_stats(fd_times)
        s["label"] = "FallDetector"
        rows.append(s)
    if am_times:
        s = compute_stats(am_times)
        s["label"] = "AlertManager"
        rows.append(s)
    if total_times:
        s = compute_stats(total_times)
        s["label"] = "TOTAL"
        rows.append(s)
    print_stats_table(rows)

    if persons_per_frame:
        valid = [c for c in persons_per_frame if c > 0]
        print_section("Persons Detected per Frame")
        if valid:
            print(f"  Min: {min(valid)}")
            print(f"  Avg: {statistics.mean(valid):.1f}")
            print(f"  Max: {max(valid)}")
        else:
            print("  No persons detected (YOLO/MediaPipe unavailable)")

    print_section("Frame Budget Analysis")
    if total_times:
        _ts = compute_stats(total_times)
        _m = "mean"
        _f = "fps"
        print(f"  Effective FPS:     {_ts[_f]:.1f}")
        print(f"  Mean frame time:   {_ts[_m]:.2f} ms")
        print(f"  P95 frame time:    {_ts['p95']:.2f} ms")
        print(f"  P99 frame time:    {_ts['p99']:.2f} ms")
        print()
        budget = 1000.0 / 30.0
        status = "PASS" if _ts["p95"] < budget else "OVER BUDGET"
        print(f"  30 FPS target: {budget:.1f} ms budget | "
              f"P95 actual: {_ts['p95']:.2f} ms  [{status}]")
    print()


# ---------------------------------------------------------------------------
# Benchmark: Ensemble mode
# ---------------------------------------------------------------------------

def benchmark_ensemble(num_frames, combo_filter=None):
    """Benchmark FallDetector across 6 weight combos x 21 scenarios.

    For each combo, configures rule_weight, ml_weight, and enhanced_rules
    on a fresh FallDetector instance. Runs all 21 scenarios and measures
    speed, accuracy, and pre-impact detection.

    Args:
        num_frames: Number of frames to process per scenario.
        combo_filter: Optional list of combo letters (e.g. ["A", "F"]).
                      If None, all 6 combos are tested.
    """
    print_header("SENTIO Ensemble Benchmark")
    print(f"Frames per scenario: {num_frames}")
    print(f"Scenarios: {len(ALL_SCENARIOS)} "
          f"(fall={len(FALL_SCENARIOS)}, normal={len(NORMAL_SCENARIOS)}, "
          f"pre-impact={len(PRE_IMPACT_SCENARIOS)})")

    # Determine which combos to run
    if combo_filter:
        combos_to_run = {k: v for k, v in ENSEMBLE_COMBOS.items()
                         if k in combo_filter}
        if not combos_to_run:
            print(f"\n[ERROR] No valid combos in filter: {combo_filter}")
            print(f"  Valid combos: {', '.join(ENSEMBLE_COMBOS.keys())}")
            sys.exit(1)
    else:
        combos_to_run = ENSEMBLE_COMBOS

    print(f"Combos: {', '.join(combos_to_run.keys())}")

    try:
        from app.services.fall_detector import FallDetector
    except ImportError as e:
        print(f"\n[ERROR] Failed to import FallDetector: {e}")
        print("Make sure you run from project root with deps installed.")
        sys.exit(1)

    # Collect system resource info
    cpu_start, mem_start = _get_system_resources()

    # Storage for results: combo -> scenario -> metrics
    all_results = {}

    for combo_id, combo_cfg in combos_to_run.items():
        print_section(f"Combo {combo_id}: {combo_cfg['desc']}")
        print(f"  rule_weight={combo_cfg['rule_weight']:.0%}, "
              f"ml_weight={combo_cfg['ml_weight']:.0%}, "
              f"enhanced={'ON' if combo_cfg['enhanced'] else 'OFF'}")

        combo_results = {}

        for scenario in ALL_SCENARIOS:
            # Create a fresh detector for each scenario to avoid state leakage
            detector = FallDetector()
            detector.rule_weight = combo_cfg["rule_weight"]
            # Note: setting rule_weight auto-sets ml_weight via the setter,
            # but we explicitly set ml_weight to match the combo definition
            detector._ml_weight = combo_cfg["ml_weight"]
            detector._rule_weight = combo_cfg["rule_weight"]
            detector.enhanced_rules = combo_cfg["enhanced"]

            timings = []
            fall_detected_any = False
            pre_impact_detected_any = False
            final_result = None

            person_id = f"bench_{combo_id}_{scenario}"

            for frame_idx in range(num_frames):
                lm = generate_scenario_landmarks(scenario, frame_idx, num_frames)
                lm = add_noise(lm, noise_level=0.003)

                t0 = time.perf_counter()
                result = detector.detect(lm, person_id)
                elapsed_ms = (time.perf_counter() - t0) * 1000.0
                timings.append(elapsed_ms)

                if result["is_fallen"]:
                    fall_detected_any = True
                if result.get("is_pre_impact", False):
                    pre_impact_detected_any = True
                final_result = result

            stats = compute_stats(timings)
            combo_results[scenario] = {
                "stats": stats,
                "fall_detected": fall_detected_any,
                "pre_impact_detected": pre_impact_detected_any,
                "final_confidence": final_result["confidence"] if final_result else 0.0,
                "final_rule_score": final_result["rule_score"] if final_result else 0.0,
                "final_ml_score": final_result["ml_score"] if final_result else 0.0,
            }

        all_results[combo_id] = combo_results

        # Print per-scenario summary for this combo
        _print_combo_scenario_summary(combo_id, combo_results)

    # System resources at end
    cpu_end, mem_end = _get_system_resources()

    # Print comparison tables
    _print_ensemble_comparison(all_results, combos_to_run)
    _print_accuracy_matrix(all_results, combos_to_run)
    _print_resource_usage(cpu_start, mem_start, cpu_end, mem_end)

    # Generate recommendation
    recommendation = _generate_recommendation(all_results, combos_to_run)
    print_section("Recommendation")
    print(f"  {recommendation}")
    print()

    # Generate markdown report
    report_path = _PROJECT_ROOT / "docs" / "benchmark_report.md"
    _generate_markdown_report(
        all_results, combos_to_run, num_frames,
        cpu_start, mem_start, cpu_end, mem_end,
        recommendation, report_path,
    )
    print(f"  Report saved to: {report_path}")
    print()


def _get_system_resources():
    """Get current CPU% and memory usage in MB. Returns (cpu_pct, mem_mb)."""
    try:
        import psutil
        process = psutil.Process(os.getpid())
        cpu_pct = process.cpu_percent(interval=0.1)
        mem_mb = process.memory_info().rss / (1024 * 1024)
        return cpu_pct, mem_mb
    except ImportError:
        return 0.0, 0.0


def _print_combo_scenario_summary(combo_id, combo_results):
    """Print a brief per-scenario result table for one combo."""
    print()
    header = (f"  {'Scenario':<22} {'Mean(ms)':>9} {'P95(ms)':>9} "
              f"{'FPS':>7} {'Fall?':>6} {'PreImp':>7} {'Conf':>6}")
    print(header)
    print("  " + "-" * (len(header) - 2))

    for scenario in ALL_SCENARIOS:
        r = combo_results[scenario]
        s = r["stats"]
        fall_mark = "YES" if r["fall_detected"] else "no"
        pre_mark = "YES" if r["pre_impact_detected"] else "no"
        fps_str = f"{s['fps']:.0f}" if s["fps"] > 0 else "N/A"
        print(f"  {scenario:<22} {s['mean']:>9.2f} {s['p95']:>9.2f} "
              f"{fps_str:>7} {fall_mark:>6} {pre_mark:>7} {r['final_confidence']:>6.2f}")


def _print_ensemble_comparison(all_results, combos):
    """Print the 6-combo comparison table (speed metrics)."""
    print_section("Ensemble Comparison (all scenarios aggregated)")

    header = (f"  {'Combo':<8} {'Description':<32} "
              f"{'Mean(ms)':>9} {'P50(ms)':>9} {'P95(ms)':>9} "
              f"{'P99(ms)':>9} {'FPS':>7}")
    print(header)
    print("  " + "-" * (len(header) - 2))

    for combo_id in sorted(combos.keys()):
        cfg = combos[combo_id]
        combo_results = all_results[combo_id]

        # Aggregate all scenario timings
        all_means = [combo_results[s]["stats"]["mean"] for s in ALL_SCENARIOS]
        all_p50 = [combo_results[s]["stats"]["p50"] for s in ALL_SCENARIOS]
        all_p95 = [combo_results[s]["stats"]["p95"] for s in ALL_SCENARIOS]
        all_p99 = [combo_results[s]["stats"]["p99"] for s in ALL_SCENARIOS]

        agg_mean = statistics.mean(all_means) if all_means else 0
        agg_p50 = statistics.mean(all_p50) if all_p50 else 0
        agg_p95 = statistics.mean(all_p95) if all_p95 else 0
        agg_p99 = statistics.mean(all_p99) if all_p99 else 0
        agg_fps = 1000.0 / agg_mean if agg_mean > 0 else 0

        desc = cfg["desc"][:30]
        print(f"  {combo_id:<8} {desc:<32} "
              f"{agg_mean:>9.2f} {agg_p50:>9.2f} {agg_p95:>9.2f} "
              f"{agg_p99:>9.2f} {agg_fps:>7.0f}")


def _print_accuracy_matrix(all_results, combos):
    """Print per-scenario accuracy matrix across combos."""
    print_section("Accuracy Matrix (Fall scenarios: detect=GOOD, Normal: no-detect=GOOD)")

    # Header
    combo_ids = sorted(combos.keys())
    header_parts = [f"{'Scenario':<22}", f"{'Expected':>9}"]
    for cid in combo_ids:
        header_parts.append(f"{cid:>6}")
    print("  " + " ".join(header_parts))
    print("  " + "-" * (22 + 9 + len(combo_ids) * 7 + 2))

    total_correct = {cid: 0 for cid in combo_ids}
    total_count = len(ALL_SCENARIOS)

    # Fall scenarios
    for scenario in FALL_SCENARIOS:
        parts = [f"{scenario:<22}", f"{'FALL':>9}"]
        for cid in combo_ids:
            detected = all_results[cid][scenario]["fall_detected"]
            mark = "OK" if detected else "MISS"
            if detected:
                total_correct[cid] += 1
            parts.append(f"{mark:>6}")
        print("  " + " ".join(parts))

    # Normal scenarios
    for scenario in NORMAL_SCENARIOS:
        parts = [f"{scenario:<22}", f"{'NORMAL':>9}"]
        for cid in combo_ids:
            detected = all_results[cid][scenario]["fall_detected"]
            mark = "OK" if not detected else "FP"
            if not detected:
                total_correct[cid] += 1
            parts.append(f"{mark:>6}")
        print("  " + " ".join(parts))

    # Pre-impact scenarios
    for scenario in PRE_IMPACT_SCENARIOS:
        parts = [f"{scenario:<22}", f"{'PRE':>9}"]
        for cid in combo_ids:
            pre_detected = all_results[cid][scenario]["pre_impact_detected"]
            fall_detected = all_results[cid][scenario]["fall_detected"]
            if fall_detected:
                mark = "FP"  # Should not be a full fall detection
            elif pre_detected:
                mark = "PRE"
                total_correct[cid] += 1
            else:
                mark = "MISS"
                # Pre-impact detection is desirable but not required for accuracy
                total_correct[cid] += 1  # No false positive is still acceptable
            parts.append(f"{mark:>6}")
        print("  " + " ".join(parts))

    # Summary row
    print()
    parts = [f"{'ACCURACY':<22}", f"{'':>9}"]
    for cid in combo_ids:
        acc = total_correct[cid] / total_count * 100 if total_count > 0 else 0
        parts.append(f"{acc:>5.1f}%")
    print("  " + " ".join(parts))

    # FNR and FPR
    parts_fnr = [f"{'FNR (fall miss)':<22}", f"{'':>9}"]
    parts_fpr = [f"{'FPR (false pos)':<22}", f"{'':>9}"]
    for cid in combo_ids:
        fn = sum(1 for s in FALL_SCENARIOS
                 if not all_results[cid][s]["fall_detected"])
        fnr = fn / len(FALL_SCENARIOS) * 100 if FALL_SCENARIOS else 0
        parts_fnr.append(f"{fnr:>5.1f}%")

        fp = sum(1 for s in NORMAL_SCENARIOS
                 if all_results[cid][s]["fall_detected"])
        fpr = fp / len(NORMAL_SCENARIOS) * 100 if NORMAL_SCENARIOS else 0
        parts_fpr.append(f"{fpr:>5.1f}%")

    print("  " + " ".join(parts_fnr))
    print("  " + " ".join(parts_fpr))

    # Pre-impact detection rate
    parts_pre = [f"{'Pre-impact rate':<22}", f"{'':>9}"]
    for cid in combo_ids:
        pre_count = sum(1 for s in PRE_IMPACT_SCENARIOS
                        if all_results[cid][s]["pre_impact_detected"])
        pre_rate = pre_count / len(PRE_IMPACT_SCENARIOS) * 100 if PRE_IMPACT_SCENARIOS else 0
        parts_pre.append(f"{pre_rate:>5.1f}%")
    print("  " + " ".join(parts_pre))


def _print_resource_usage(cpu_start, mem_start, cpu_end, mem_end):
    """Print resource usage summary."""
    print_section("Resource Usage")
    print(f"  CPU%  start={cpu_start:.1f}%  end={cpu_end:.1f}%")
    print(f"  Memory  start={mem_start:.1f} MB  end={mem_end:.1f} MB  "
          f"delta={mem_end - mem_start:+.1f} MB")


def _generate_recommendation(all_results, combos):
    """Generate a recommendation based on FNR, FPS, FPR criteria.

    Priority:
      1. FNR must be approximately 0 (no missed falls)
      2. FPS must be >= 10
      3. Among qualifying combos, pick lowest FPR
    """
    combo_ids = sorted(combos.keys())
    candidates = []

    for cid in combo_ids:
        # Calculate FNR
        fn = sum(1 for s in FALL_SCENARIOS
                 if not all_results[cid][s]["fall_detected"])
        fnr = fn / len(FALL_SCENARIOS) if FALL_SCENARIOS else 0

        # Calculate FPR
        fp = sum(1 for s in NORMAL_SCENARIOS
                 if all_results[cid][s]["fall_detected"])
        fpr = fp / len(NORMAL_SCENARIOS) if NORMAL_SCENARIOS else 0

        # Calculate mean FPS across scenarios
        all_means = [all_results[cid][s]["stats"]["mean"] for s in ALL_SCENARIOS]
        mean_ms = statistics.mean(all_means) if all_means else 999
        fps = 1000.0 / mean_ms if mean_ms > 0 else 0

        # Pre-impact detection rate
        pre_count = sum(1 for s in PRE_IMPACT_SCENARIOS
                        if all_results[cid][s]["pre_impact_detected"])
        pre_rate = pre_count / len(PRE_IMPACT_SCENARIOS) if PRE_IMPACT_SCENARIOS else 0

        candidates.append({
            "id": cid,
            "fnr": fnr,
            "fpr": fpr,
            "fps": fps,
            "pre_rate": pre_rate,
            "desc": combos[cid]["desc"],
        })

    # Filter: FNR ~= 0 (allow up to 12.5% = 1 miss out of 8)
    qualifying = [c for c in candidates if c["fnr"] <= 0.125]

    # Filter: FPS >= 10
    qualifying = [c for c in qualifying if c["fps"] >= 10]

    if not qualifying:
        # Relax FNR constraint
        qualifying = [c for c in candidates if c["fps"] >= 10]
        if not qualifying:
            qualifying = candidates  # Last resort: pick from all

    # Sort by: FNR ascending, then FPR ascending, then pre_rate descending
    qualifying.sort(key=lambda c: (c["fnr"], c["fpr"], -c["pre_rate"]))

    best = qualifying[0]
    return (
        f"Best combo: {best['id']} ({best['desc']}) -- "
        f"FNR={best['fnr']:.1%}, FPR={best['fpr']:.1%}, "
        f"FPS={best['fps']:.0f}, Pre-impact={best['pre_rate']:.0%}"
    )


def _generate_markdown_report(all_results, combos, num_frames,
                               cpu_start, mem_start, cpu_end, mem_end,
                               recommendation, report_path):
    """Generate a Markdown benchmark report at the given path."""
    combo_ids = sorted(combos.keys())
    lines = []

    lines.append("# SENTIO Ensemble Benchmark Report")
    lines.append("")
    lines.append(f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"Frames per scenario: {num_frames}")
    lines.append(f"Scenarios: {len(ALL_SCENARIOS)} "
                 f"(fall={len(FALL_SCENARIOS)}, normal={len(NORMAL_SCENARIOS)}, "
                 f"pre-impact={len(PRE_IMPACT_SCENARIOS)})")
    lines.append("")

    # --- Combo definitions ---
    lines.append("## Weight Combinations")
    lines.append("")
    lines.append("| Combo | Rule | ML | Enhanced | Description |")
    lines.append("|-------|------|----|----------|-------------|")
    for cid in combo_ids:
        cfg = combos[cid]
        lines.append(
            f"| {cid} | {cfg['rule_weight']:.0%} | {cfg['ml_weight']:.0%} | "
            f"{'ON' if cfg['enhanced'] else 'OFF'} | {cfg['desc']} |"
        )
    lines.append("")

    # --- Speed comparison ---
    lines.append("## Speed Comparison")
    lines.append("")
    header = "| Combo | Mean (ms) | P50 (ms) | P95 (ms) | P99 (ms) | FPS |"
    lines.append(header)
    lines.append("|-------|-----------|----------|----------|----------|-----|")
    for cid in combo_ids:
        combo_results = all_results[cid]
        all_means = [combo_results[s]["stats"]["mean"] for s in ALL_SCENARIOS]
        all_p50 = [combo_results[s]["stats"]["p50"] for s in ALL_SCENARIOS]
        all_p95 = [combo_results[s]["stats"]["p95"] for s in ALL_SCENARIOS]
        all_p99 = [combo_results[s]["stats"]["p99"] for s in ALL_SCENARIOS]

        agg_mean = statistics.mean(all_means) if all_means else 0
        agg_p50 = statistics.mean(all_p50) if all_p50 else 0
        agg_p95 = statistics.mean(all_p95) if all_p95 else 0
        agg_p99 = statistics.mean(all_p99) if all_p99 else 0
        agg_fps = 1000.0 / agg_mean if agg_mean > 0 else 0

        lines.append(
            f"| {cid} | {agg_mean:.2f} | {agg_p50:.2f} | "
            f"{agg_p95:.2f} | {agg_p99:.2f} | {agg_fps:.0f} |"
        )
    lines.append("")

    # --- Accuracy Matrix ---
    lines.append("## Accuracy Matrix")
    lines.append("")
    header_parts = ["| Scenario | Expected |"]
    for cid in combo_ids:
        header_parts.append(f" {cid} |")
    lines.append(" ".join(header_parts))
    sep_parts = ["|----------|----------|"]
    for _ in combo_ids:
        sep_parts.append("----|")
    lines.append(" ".join(sep_parts))

    for scenario in FALL_SCENARIOS:
        parts = [f"| {scenario} | FALL |"]
        for cid in combo_ids:
            detected = all_results[cid][scenario]["fall_detected"]
            mark = "OK" if detected else "MISS"
            parts.append(f" {mark} |")
        lines.append(" ".join(parts))

    for scenario in NORMAL_SCENARIOS:
        parts = [f"| {scenario} | NORMAL |"]
        for cid in combo_ids:
            detected = all_results[cid][scenario]["fall_detected"]
            mark = "OK" if not detected else "FP"
            parts.append(f" {mark} |")
        lines.append(" ".join(parts))

    for scenario in PRE_IMPACT_SCENARIOS:
        parts = [f"| {scenario} | PRE |"]
        for cid in combo_ids:
            pre_det = all_results[cid][scenario]["pre_impact_detected"]
            fall_det = all_results[cid][scenario]["fall_detected"]
            if fall_det:
                mark = "FP"
            elif pre_det:
                mark = "PRE"
            else:
                mark = "MISS"
            parts.append(f" {mark} |")
        lines.append(" ".join(parts))

    lines.append("")

    # --- Summary metrics ---
    lines.append("## Summary Metrics")
    lines.append("")
    header_parts = ["| Metric |"]
    for cid in combo_ids:
        header_parts.append(f" {cid} |")
    lines.append(" ".join(header_parts))
    sep_parts = ["|--------|"]
    for _ in combo_ids:
        sep_parts.append("----|")
    lines.append(" ".join(sep_parts))

    # FNR
    parts = ["| FNR |"]
    for cid in combo_ids:
        fn = sum(1 for s in FALL_SCENARIOS
                 if not all_results[cid][s]["fall_detected"])
        fnr = fn / len(FALL_SCENARIOS) * 100 if FALL_SCENARIOS else 0
        parts.append(f" {fnr:.1f}% |")
    lines.append(" ".join(parts))

    # FPR
    parts = ["| FPR |"]
    for cid in combo_ids:
        fp = sum(1 for s in NORMAL_SCENARIOS
                 if all_results[cid][s]["fall_detected"])
        fpr = fp / len(NORMAL_SCENARIOS) * 100 if NORMAL_SCENARIOS else 0
        parts.append(f" {fpr:.1f}% |")
    lines.append(" ".join(parts))

    # Pre-impact rate
    parts = ["| Pre-impact |"]
    for cid in combo_ids:
        pre = sum(1 for s in PRE_IMPACT_SCENARIOS
                  if all_results[cid][s]["pre_impact_detected"])
        rate = pre / len(PRE_IMPACT_SCENARIOS) * 100 if PRE_IMPACT_SCENARIOS else 0
        parts.append(f" {rate:.1f}% |")
    lines.append(" ".join(parts))

    # Accuracy
    parts = ["| Accuracy |"]
    for cid in combo_ids:
        correct = 0
        for s in FALL_SCENARIOS:
            if all_results[cid][s]["fall_detected"]:
                correct += 1
        for s in NORMAL_SCENARIOS:
            if not all_results[cid][s]["fall_detected"]:
                correct += 1
        for s in PRE_IMPACT_SCENARIOS:
            if not all_results[cid][s]["fall_detected"]:
                correct += 1
        acc = correct / len(ALL_SCENARIOS) * 100 if ALL_SCENARIOS else 0
        parts.append(f" {acc:.1f}% |")
    lines.append(" ".join(parts))

    lines.append("")

    # --- Resource usage ---
    lines.append("## Resource Usage")
    lines.append("")
    lines.append(f"- CPU: start={cpu_start:.1f}%, end={cpu_end:.1f}%")
    lines.append(f"- Memory: start={mem_start:.1f} MB, end={mem_end:.1f} MB, "
                 f"delta={mem_end - mem_start:+.1f} MB")
    lines.append("")

    # --- Recommendation ---
    lines.append("## Recommendation")
    lines.append("")
    lines.append(f"> {recommendation}")
    lines.append("")
    lines.append("### Selection criteria (priority order)")
    lines.append("1. **FNR ~ 0**: No missed falls (safety-critical)")
    lines.append("2. **FPS >= 10**: Real-time processing capability")
    lines.append("3. **FPR minimum**: Fewest false alarms among qualifying combos")
    lines.append("")

    # Write file
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(lines), encoding="utf-8")


# ---------------------------------------------------------------------------
# Video discovery
# ---------------------------------------------------------------------------

def find_default_video():
    """Find the first fall video in demo_videos/ directory."""
    demo_dir = _PROJECT_ROOT / "demo_videos"
    if not demo_dir.exists():
        return None
    for prefix in ["FY_", "BY_", "SY_"]:
        for f in sorted(demo_dir.iterdir()):
            if f.name.startswith(prefix) and f.suffix.lower() in (".mp4", ".avi", ".mkv", ".mov"):
                return str(f)
    for f in sorted(demo_dir.iterdir()):
        if f.suffix.lower() in (".mp4", ".avi", ".mkv", ".mov"):
            return str(f)
    return None


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="SENTIO Pipeline Benchmark",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  %(prog)s --synthetic              Synthetic FallDetector scaling\n"
            "  %(prog)s --synthetic --frames 200  Synthetic with 200 frames\n"
            "  %(prog)s --full                    Full pipeline with demo video\n"
            "  %(prog)s --video path/to/vid.mp4   Full pipeline with specific video\n"
            "  %(prog)s --ensemble                Ensemble 6-combo x 21-scenario\n"
            "  %(prog)s --ensemble --combos A,F   Ensemble with specific combos\n"
            "  %(prog)s --ensemble --frames 60    Ensemble with 60 frames/scenario\n"
        ),
    )

    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--synthetic", action="store_true",
                       help="Synthetic benchmark (no video needed)")
    mode.add_argument("--full", action="store_true",
                       help="Full pipeline benchmark with video")
    mode.add_argument("--ensemble", action="store_true",
                       help="Ensemble benchmark: 6 weight combos x 21 scenarios")

    parser.add_argument("--frames", "-n", type=int, default=100,
                         help="Number of frames (default: 100)")
    parser.add_argument("--video", "-v", type=str, default=None,
                         help="Path to video file")
    parser.add_argument("--seed", type=int, default=42,
                         help="Random seed (default: 42)")
    parser.add_argument("--combos", type=str, default=None,
                         help="Comma-separated combo letters for ensemble mode "
                              "(e.g. A,F). Default: all combos.")

    args = parser.parse_args()
    random.seed(args.seed)

    if args.ensemble:
        combo_filter = None
        if args.combos:
            combo_filter = [c.strip().upper() for c in args.combos.split(",")]
        benchmark_ensemble(args.frames, combo_filter)
    elif args.synthetic:
        benchmark_synthetic(args.frames)
    elif args.full or args.video:
        vp = args.video
        if vp is None:
            vp = find_default_video()
            if vp is None:
                print("[ERROR] No video file found in demo_videos/")
                print("Use --video PATH or --synthetic mode.")
                sys.exit(1)
        benchmark_full_pipeline(vp, args.frames)
    else:
        print("[INFO] No mode specified. Running synthetic benchmark.")
        print("       Use --full for full pipeline, --ensemble for combo comparison,")
        print("       or --help for options.")
        benchmark_synthetic(args.frames)


if __name__ == "__main__":
    main()
