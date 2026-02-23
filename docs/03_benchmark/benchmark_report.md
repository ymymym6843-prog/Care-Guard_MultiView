# SENTIO Ensemble Benchmark Report

Generated: 2026-02-05 14:43:41
Frames per scenario: 60
Scenarios: 21 (fall=8, normal=10, pre-impact=3)

## Weight Combinations

| Combo | Rule | ML | Enhanced | Description |
|-------|------|----|----------|-------------|
| A | 100% | 0% | OFF | Rule 4 conditions only (max speed) |
| B | 70% | 30% | OFF | Rule-focused |
| C | 50% | 50% | OFF | Current setting (baseline) |
| D | 30% | 70% | OFF | ML-focused |
| E | 0% | 100% | OFF | ML only |
| F | 100% | 0% | ON | Rule-enhanced 10 conditions |

## Speed Comparison

| Combo | Mean (ms) | P50 (ms) | P95 (ms) | P99 (ms) | FPS |
|-------|-----------|----------|----------|----------|-----|
| A | 0.03 | 0.03 | 0.05 | 0.20 | 28807 |
| B | 1.92 | 0.80 | 1.66 | 35.91 | 520 |
| C | 1.34 | 0.77 | 1.82 | 21.29 | 745 |
| D | 1.20 | 0.91 | 2.22 | 16.11 | 836 |
| E | 1.10 | 0.90 | 1.70 | 14.40 | 909 |
| F | 0.08 | 0.04 | 0.06 | 0.97 | 13039 |

## Accuracy Matrix

| Scenario | Expected |  A |  B |  C |  D |  E |  F |
|----------|----------| ----| ----| ----| ----| ----| ----|
| forward_fall | FALL |  OK |  OK |  OK |  OK |  OK |  OK |
| backward_fall | FALL |  MISS |  MISS |  MISS |  MISS |  MISS |  OK |
| side_fall | FALL |  OK |  MISS |  MISS |  MISS |  MISS |  MISS |
| trip | FALL |  OK |  MISS |  MISS |  MISS |  MISS |  OK |
| slow_fall | FALL |  MISS |  OK |  OK |  OK |  OK |  MISS |
| bed_fall | FALL |  OK |  OK |  OK |  OK |  OK |  OK |
| knee_buckle_fall | FALL |  MISS |  MISS |  MISS |  MISS |  OK |  MISS |
| slip | FALL |  MISS |  MISS |  MISS |  MISS |  MISS |  MISS |
| walking | NORMAL |  OK |  OK |  OK |  OK |  OK |  OK |
| sitting | NORMAL |  OK |  OK |  OK |  OK |  OK |  OK |
| bending | NORMAL |  FP |  FP |  FP |  FP |  FP |  FP |
| stretching | NORMAL |  OK |  OK |  OK |  OK |  OK |  OK |
| bed_lying | NORMAL |  FP |  FP |  FP |  FP |  FP |  FP |
| wheelchair | NORMAL |  OK |  OK |  OK |  OK |  OK |  OK |
| fast_sit | NORMAL |  OK |  OK |  OK |  OK |  OK |  OK |
| fast_walk | NORMAL |  OK |  OK |  OK |  OK |  OK |  OK |
| stairs | NORMAL |  OK |  OK |  OK |  OK |  OK |  OK |
| phone_call | NORMAL |  OK |  OK |  OK |  OK |  OK |  OK |
| stumble | PRE |  MISS |  MISS |  MISS |  MISS |  MISS |  MISS |
| balance_recovery | PRE |  MISS |  MISS |  MISS |  MISS |  MISS |  MISS |
| knee_slight_bend | PRE |  MISS |  MISS |  MISS |  MISS |  MISS |  MISS |

## Summary Metrics

| Metric |  A |  B |  C |  D |  E |  F |
|--------| ----| ----| ----| ----| ----| ----|
| FNR |  50.0% |  62.5% |  62.5% |  62.5% |  50.0% |  50.0% |
| FPR |  20.0% |  20.0% |  20.0% |  20.0% |  20.0% |  20.0% |
| Pre-impact |  0.0% |  0.0% |  0.0% |  0.0% |  0.0% |  0.0% |
| Accuracy |  71.4% |  66.7% |  66.7% |  66.7% |  71.4% |  71.4% |

## Demo Video Test Results (2026-02-06)

| Video | Type | Result | Falls (frames) | Notes |
|-------|------|--------|----------------|-------|
| BY_back_fall_balance.mp4 | FALL | ✅ DETECTED | 54 | Back fall - balance loss |
| BY_back_fall_slip.mp4 | FALL | ✅ DETECTED | 30 | Back fall - slip |
| BY_hospital_back_C1.mp4 | FALL | ✅ DETECTED | 10 | Hospital camera C1 |
| BY_hospital_back_C3.mp4 | FALL | ✅ DETECTED | 28 | Hospital camera C3 |
| BY_hospital_back_C5.mp4 | FALL | ✅ DETECTED | 4 | Hospital camera C5 |
| FY_front_fall_balance.mp4 | FALL | ✅ DETECTED | 35 | Front fall - balance |
| FY_front_fall_slip.mp4 | FALL | ✅ DETECTED | 9 | Front fall - slip |
| FY_front_fall_trip.mp4 | FALL | ✅ DETECTED | 29 | Trip fall (was 0, fixed!) |
| FY_hospital_front_C1.mp4 | FALL | ✅ DETECTED | 1 | Hospital camera C1 |
| FY_hospital_front_C5.mp4 | FALL | ✅ DETECTED | 6 | Hospital camera C5 |
| SY_side_fall_balance.mp4 | FALL | ✅ DETECTED | 14 | Side fall - balance |
| SY_side_fall_slip.mp4 | FALL | ✅ DETECTED | 23 | Side fall - slip |
| SY_hospital_side_C1.mp4 | FALL | ✅ DETECTED | 4 | Hospital camera C1 |
| SY_hospital_side_C3.mp4 | FALL | ✅ DETECTED | 3 | Hospital camera C3 |
| SY_hospital_side_C5.mp4 | FALL | ✅ DETECTED | 6 | Hospital camera C5 |
| crutch_test.mp4 | FALL | ✅ DETECTED | 11 | Crutch user fall |
| wheelchair_test.mp4 | FALL | ✅ DETECTED | 18 | Wheelchair user fall |
| N_hospital_normal_C1.mp4 | NORMAL | ⚠️ 1 FP | 1 | Minor |
| N_hospital_normal_C5.mp4 | NORMAL | ✅ OK | 0 | No false positives |
| N_normal_sideview_01.mp4 | NORMAL | ⚠️ 2 FP | 2 | Minor |
| N_normal_sideview_02.mp4 | NORMAL | ⚠️ 1 FP | 1 | Minor |
| N_normal_standing_01.mp4 | NORMAL | ✅ OK | 0 | No false positives |
| N_normal_standing_02.mp4 | NORMAL | ✅ OK | 0 | No false positives |
| N_normal_standing_03.mp4 | NORMAL | ⚠️ 14 FP | 14 | Improved (was 65) |

**Summary:** 100% Recall (all fall videos detected), reduced false positive duration

## Accuracy Improvements (2026-02-06)

### 1. Quick Recovery Detection
Reduces intentional lying false positives by detecting controlled movements after lying down. When a person deliberately lies down and quickly recovers, the system recognizes this as non-emergency behavior.

### 2. Multi-frame Accumulation
Handles low visibility scenarios by accumulating detection confidence across multiple frames. This ensures that brief occlusions or poor lighting conditions don't cause missed detections while maintaining accuracy.

### 3. Controlled Movement Post-Fall
Detects smooth controlled movements after a fall event. This helps distinguish between actual falls requiring assistance and intentional movements (e.g., exercise, stretching) that may involve lying on the ground.

## Resource Usage

- CPU: start=0.0%, end=799.4%
- Memory: start=49.8 MB, end=91.6 MB, delta=+41.9 MB

## Recommendation

> Best combo: A (Rule 4 conditions only (max speed)) -- FNR=50.0%, FPR=20.0%, FPS=28807, Pre-impact=0%

### Selection criteria (priority order)
1. **FNR ~ 0**: No missed falls (safety-critical)
2. **FPS >= 10**: Real-time processing capability
3. **FPR minimum**: Fewest false alarms among qualifying combos
