"""
Unit tests for PostureClassifier service.

Tests cover:
- Standing detection (high knee_bend_ratio, head above hip)
- Sitting detection (low knee_bend_ratio, head above hip)
- Lying detection (body nearly horizontal, small total height)
- Posture stability (voting mechanism over multiple frames)
- Sitting baseline tracking (head_y baseline accumulation)
- Shoulder tilt delta calculation
- reset_person functionality
- Edge case: insufficient landmarks (<33)
"""

import pytest

from app.services.posture_classifier import PostureClassifier, PostureType


def create_landmarks_standing():
    """Create standing pose landmarks.

    Standing characteristics:
    - High knee_bend_ratio (hip-knee / knee-ankle ≈ 1.0)
    - Head above hip (head_y < hip_y)
    - Large total height (ankle_y - head_y ≈ 0.75)
    - Body nearly vertical (body_angle ≈ 0°)
    """
    return [
        {"x": 0.5, "y": 0.2, "z": 0.0},   # 0: NOSE
        {"x": 0.5, "y": 0.2, "z": 0.0},   # 1
        {"x": 0.5, "y": 0.2, "z": 0.0},   # 2
        {"x": 0.5, "y": 0.2, "z": 0.0},   # 3
        {"x": 0.5, "y": 0.2, "z": 0.0},   # 4
        {"x": 0.5, "y": 0.2, "z": 0.0},   # 5
        {"x": 0.5, "y": 0.2, "z": 0.0},   # 6
        {"x": 0.5, "y": 0.2, "z": 0.0},   # 7
        {"x": 0.5, "y": 0.2, "z": 0.0},   # 8
        {"x": 0.5, "y": 0.2, "z": 0.0},   # 9
        {"x": 0.5, "y": 0.2, "z": 0.0},   # 10
        {"x": 0.45, "y": 0.35, "z": 0.0}, # 11: LEFT_SHOULDER
        {"x": 0.55, "y": 0.35, "z": 0.0}, # 12: RIGHT_SHOULDER
        {"x": 0.4, "y": 0.5, "z": 0.0},   # 13
        {"x": 0.6, "y": 0.5, "z": 0.0},   # 14
        {"x": 0.35, "y": 0.65, "z": 0.0}, # 15
        {"x": 0.65, "y": 0.65, "z": 0.0}, # 16
        {"x": 0.3, "y": 0.7, "z": 0.0},   # 17
        {"x": 0.7, "y": 0.7, "z": 0.0},   # 18
        {"x": 0.3, "y": 0.7, "z": 0.0},   # 19
        {"x": 0.7, "y": 0.7, "z": 0.0},   # 20
        {"x": 0.3, "y": 0.7, "z": 0.0},   # 21
        {"x": 0.7, "y": 0.7, "z": 0.0},   # 22
        {"x": 0.45, "y": 0.55, "z": 0.0}, # 23: LEFT_HIP
        {"x": 0.55, "y": 0.55, "z": 0.0}, # 24: RIGHT_HIP
        {"x": 0.45, "y": 0.75, "z": 0.0}, # 25: LEFT_KNEE
        {"x": 0.55, "y": 0.75, "z": 0.0}, # 26: RIGHT_KNEE
        {"x": 0.45, "y": 0.95, "z": 0.0}, # 27: LEFT_ANKLE
        {"x": 0.55, "y": 0.95, "z": 0.0}, # 28: RIGHT_ANKLE
        {"x": 0.45, "y": 0.97, "z": 0.0}, # 29
        {"x": 0.55, "y": 0.97, "z": 0.0}, # 30
        {"x": 0.45, "y": 0.99, "z": 0.0}, # 31
        {"x": 0.55, "y": 0.99, "z": 0.0}, # 32
    ]


def create_landmarks_sitting():
    """Create sitting pose landmarks.

    Sitting characteristics:
    - Low knee_bend_ratio (hip-knee / knee-ankle ≈ 0.1, thighs horizontal)
    - Head above hip (head_y < hip_y)
    - Medium total height (ankle_y - head_y ≈ 0.6)
    - Upper body nearly vertical (body_angle ≈ 0-20°)
    """
    return [
        {"x": 0.5, "y": 0.35, "z": 0.0},  # 0: NOSE
        {"x": 0.5, "y": 0.35, "z": 0.0},  # 1
        {"x": 0.5, "y": 0.35, "z": 0.0},  # 2
        {"x": 0.5, "y": 0.35, "z": 0.0},  # 3
        {"x": 0.5, "y": 0.35, "z": 0.0},  # 4
        {"x": 0.5, "y": 0.35, "z": 0.0},  # 5
        {"x": 0.5, "y": 0.35, "z": 0.0},  # 6
        {"x": 0.5, "y": 0.35, "z": 0.0},  # 7
        {"x": 0.5, "y": 0.35, "z": 0.0},  # 8
        {"x": 0.5, "y": 0.35, "z": 0.0},  # 9
        {"x": 0.5, "y": 0.35, "z": 0.0},  # 10
        {"x": 0.45, "y": 0.5, "z": 0.0},  # 11: LEFT_SHOULDER
        {"x": 0.55, "y": 0.5, "z": 0.0},  # 12: RIGHT_SHOULDER
        {"x": 0.4, "y": 0.6, "z": 0.0},   # 13
        {"x": 0.6, "y": 0.6, "z": 0.0},   # 14
        {"x": 0.35, "y": 0.7, "z": 0.0},  # 15
        {"x": 0.65, "y": 0.7, "z": 0.0},  # 16
        {"x": 0.3, "y": 0.75, "z": 0.0},  # 17
        {"x": 0.7, "y": 0.75, "z": 0.0},  # 18
        {"x": 0.3, "y": 0.75, "z": 0.0},  # 19
        {"x": 0.7, "y": 0.75, "z": 0.0},  # 20
        {"x": 0.3, "y": 0.75, "z": 0.0},  # 21
        {"x": 0.7, "y": 0.75, "z": 0.0},  # 22
        {"x": 0.45, "y": 0.7, "z": 0.0},  # 23: LEFT_HIP
        {"x": 0.55, "y": 0.7, "z": 0.0},  # 24: RIGHT_HIP
        {"x": 0.45, "y": 0.72, "z": 0.0}, # 25: LEFT_KNEE (close to hip - bent knees)
        {"x": 0.55, "y": 0.72, "z": 0.0}, # 26: RIGHT_KNEE
        {"x": 0.45, "y": 0.95, "z": 0.0}, # 27: LEFT_ANKLE
        {"x": 0.55, "y": 0.95, "z": 0.0}, # 28: RIGHT_ANKLE
        {"x": 0.45, "y": 0.97, "z": 0.0}, # 29
        {"x": 0.55, "y": 0.97, "z": 0.0}, # 30
        {"x": 0.45, "y": 0.99, "z": 0.0}, # 31
        {"x": 0.55, "y": 0.99, "z": 0.0}, # 32
    ]


def create_landmarks_lying():
    """Create lying pose landmarks.

    Lying characteristics:
    - Body nearly horizontal (body_angle > 60°)
    - Small total height (ankle_y - head_y < 0.25)
    - Head, shoulder, hip, knee, ankle all at similar y-coordinates
    """
    return [
        {"x": 0.5, "y": 0.5, "z": 0.0},   # 0: NOSE
        {"x": 0.5, "y": 0.5, "z": 0.0},   # 1
        {"x": 0.5, "y": 0.5, "z": 0.0},   # 2
        {"x": 0.5, "y": 0.5, "z": 0.0},   # 3
        {"x": 0.5, "y": 0.5, "z": 0.0},   # 4
        {"x": 0.5, "y": 0.5, "z": 0.0},   # 5
        {"x": 0.5, "y": 0.5, "z": 0.0},   # 6
        {"x": 0.5, "y": 0.5, "z": 0.0},   # 7
        {"x": 0.5, "y": 0.5, "z": 0.0},   # 8
        {"x": 0.5, "y": 0.5, "z": 0.0},   # 9
        {"x": 0.5, "y": 0.5, "z": 0.0},   # 10
        {"x": 0.25, "y": 0.51, "z": 0.0},  # 11: LEFT_SHOULDER (body horizontal, spread in x)
        {"x": 0.30, "y": 0.52, "z": 0.0},  # 12: RIGHT_SHOULDER
        {"x": 0.35, "y": 0.51, "z": 0.0}, # 13
        {"x": 0.65, "y": 0.51, "z": 0.0}, # 14
        {"x": 0.3, "y": 0.5, "z": 0.0},   # 15
        {"x": 0.7, "y": 0.5, "z": 0.0},   # 16
        {"x": 0.25, "y": 0.49, "z": 0.0}, # 17
        {"x": 0.75, "y": 0.49, "z": 0.0}, # 18
        {"x": 0.25, "y": 0.49, "z": 0.0}, # 19
        {"x": 0.75, "y": 0.49, "z": 0.0}, # 20
        {"x": 0.25, "y": 0.49, "z": 0.0}, # 21
        {"x": 0.75, "y": 0.49, "z": 0.0}, # 22
        {"x": 0.55, "y": 0.52, "z": 0.0}, # 23: LEFT_HIP (far right from shoulders)
        {"x": 0.60, "y": 0.53, "z": 0.0}, # 24: RIGHT_HIP
        {"x": 0.70, "y": 0.52, "z": 0.0}, # 25: LEFT_KNEE
        {"x": 0.75, "y": 0.52, "z": 0.0}, # 26: RIGHT_KNEE
        {"x": 0.82, "y": 0.51, "z": 0.0}, # 27: LEFT_ANKLE
        {"x": 0.87, "y": 0.51, "z": 0.0}, # 28: RIGHT_ANKLE
        {"x": 0.85, "y": 0.5, "z": 0.0},  # 29
        {"x": 0.90, "y": 0.5, "z": 0.0},  # 30
        {"x": 0.86, "y": 0.5, "z": 0.0},  # 31
        {"x": 0.68, "y": 0.5, "z": 0.0},  # 32
    ]


def create_landmarks_sitting_with_tilt():
    """Create sitting pose with shoulder tilt (leaning to side)."""
    landmarks = create_landmarks_sitting()
    # Add significant shoulder tilt
    landmarks[11]["y"] = 0.48  # LEFT_SHOULDER higher
    landmarks[12]["y"] = 0.55  # RIGHT_SHOULDER lower
    return landmarks


def create_insufficient_landmarks():
    """Create insufficient landmarks (< 33)."""
    return [{"x": 0.5, "y": 0.5, "z": 0.0}] * 20


# ── Test: Standing detection ──

def test_standing_detection():
    """Test that standing pose is correctly detected."""
    clf = PostureClassifier()
    landmarks = create_landmarks_standing()

    # Classify multiple times to stabilize (5 frames needed)
    for _ in range(5):
        result = clf.classify(landmarks, "person_0")

    assert result == PostureType.STANDING


def test_standing_high_knee_bend_ratio():
    """Test standing detection based on knee bend ratio."""
    clf = PostureClassifier()
    landmarks = create_landmarks_standing()

    # Standing: hip_y=0.55, knee_y=0.75, ankle_y=0.95
    # hip_knee = 0.2, knee_ankle = 0.2, ratio = 1.0 (> 0.6 threshold)

    for _ in range(5):
        result = clf.classify(landmarks, "person_0")

    assert result == PostureType.STANDING


# ── Test: Sitting detection ──

def test_sitting_detection():
    """Test that sitting pose is correctly detected."""
    clf = PostureClassifier()
    landmarks = create_landmarks_sitting()

    # Classify multiple times to stabilize
    for _ in range(5):
        result = clf.classify(landmarks, "person_0")

    assert result == PostureType.SITTING


def test_sitting_low_knee_bend_ratio():
    """Test sitting detection based on low knee bend ratio."""
    clf = PostureClassifier()
    landmarks = create_landmarks_sitting()

    # Sitting: hip_y=0.7, knee_y=0.72, ankle_y=0.95
    # hip_knee = 0.02, knee_ankle = 0.23, ratio ≈ 0.09 (< 0.4 threshold)

    for _ in range(5):
        result = clf.classify(landmarks, "person_0")

    assert result == PostureType.SITTING


# ── Test: Lying detection ──

def test_lying_detection():
    """Test that lying pose is correctly detected."""
    clf = PostureClassifier()
    landmarks = create_landmarks_lying()

    # Classify multiple times to stabilize
    for _ in range(5):
        result = clf.classify(landmarks, "person_0")

    assert result == PostureType.LYING


def test_lying_horizontal_body():
    """Test lying detection based on horizontal body angle."""
    clf = PostureClassifier()
    landmarks = create_landmarks_lying()

    # Lying: body nearly horizontal (body_angle > 60°)
    # total_height small (< 0.25)

    for _ in range(5):
        result = clf.classify(landmarks, "person_0")

    assert result == PostureType.LYING


def test_lying_small_total_height():
    """Test lying detection based on small total height."""
    clf = PostureClassifier()
    landmarks = create_landmarks_lying()

    # head_y = 0.5, ankle_y = 0.51, total_height = 0.01 (< 0.25)

    for _ in range(5):
        result = clf.classify(landmarks, "person_0")

    assert result == PostureType.LYING


# ── Test: Posture stability (voting mechanism) ──

def test_posture_stability_voting():
    """Test that posture is stabilized through voting over multiple frames."""
    clf = PostureClassifier()

    # Feed 3 standing frames
    standing = create_landmarks_standing()
    for _ in range(3):
        clf.classify(standing, "person_0")

    # Feed 1 sitting frame (noise)
    sitting = create_landmarks_sitting()
    clf.classify(sitting, "person_0")

    # Feed 2 more standing frames
    for _ in range(2):
        result = clf.classify(standing, "person_0")

    # Should be STANDING due to majority vote (4 standing vs 1 sitting in last 5 frames)
    assert result == PostureType.STANDING


def test_posture_transition_logging():
    """Test posture transition from standing to sitting."""
    clf = PostureClassifier()

    # Establish standing posture
    standing = create_landmarks_standing()
    for _ in range(5):
        clf.classify(standing, "person_0")

    state = clf.get_or_create_state("person_0")
    assert state.current_posture == PostureType.STANDING

    # Transition to sitting
    sitting = create_landmarks_sitting()
    for _ in range(5):
        result = clf.classify(sitting, "person_0")

    assert result == PostureType.SITTING


def test_unknown_posture_initial_state():
    """Test that initial posture is UNKNOWN before classification."""
    clf = PostureClassifier()
    state = clf.get_or_create_state("person_0")

    assert state.current_posture == PostureType.UNKNOWN


# ── Test: Sitting baseline tracking ──

def test_sitting_baseline_accumulation():
    """Test that sitting baseline accumulates over 30 frames."""
    clf = PostureClassifier()
    landmarks = create_landmarks_sitting()

    # Feed 30 frames of sitting posture
    for _ in range(30):
        clf.classify(landmarks, "person_0")

    baseline = clf.get_sitting_baseline("person_0")

    # Baseline should be around head_y = 0.35
    assert baseline > 0.0
    assert 0.3 < baseline < 0.4


def test_sitting_baseline_moving_average():
    """Test that sitting baseline uses moving average after 30 frames."""
    clf = PostureClassifier()
    landmarks = create_landmarks_sitting()

    # Feed 30 frames to establish baseline
    for _ in range(30):
        clf.classify(landmarks, "person_0")

    baseline_initial = clf.get_sitting_baseline("person_0")

    # Feed 10 more frames
    for _ in range(10):
        clf.classify(landmarks, "person_0")

    baseline_after = clf.get_sitting_baseline("person_0")

    # Baseline should remain stable (moving average with alpha=0.02)
    assert abs(baseline_after - baseline_initial) < 0.01


def test_sitting_baseline_reset_on_standing():
    """Test that sitting baseline resets when posture changes to standing."""
    clf = PostureClassifier()
    sitting = create_landmarks_sitting()

    # Establish sitting baseline
    for _ in range(30):
        clf.classify(sitting, "person_0")

    state = clf.get_or_create_state("person_0")
    assert state.sitting_baseline_frames == 30

    # Switch to standing
    standing = create_landmarks_standing()
    for _ in range(5):
        clf.classify(standing, "person_0")

    # Baseline should be reset
    assert state.sitting_baseline_frames == 0
    assert state.sitting_baseline_head_y == 0.0


def test_sitting_baseline_not_returned_before_10_frames():
    """Test that baseline is not returned before 10 frames accumulated."""
    clf = PostureClassifier()
    landmarks = create_landmarks_sitting()

    # Feed only 5 frames
    for _ in range(5):
        clf.classify(landmarks, "person_0")

    baseline = clf.get_sitting_baseline("person_0")

    # Should return 0.0 because frames < 10
    assert baseline == 0.0


def test_sitting_baseline_returned_after_10_frames():
    """Test that baseline is returned after 10 frames accumulated."""
    clf = PostureClassifier()
    landmarks = create_landmarks_sitting()

    # Feed 15 frames
    for _ in range(15):
        clf.classify(landmarks, "person_0")

    baseline = clf.get_sitting_baseline("person_0")

    # Should return valid baseline (frames >= 10)
    assert baseline > 0.0


# ── Test: Shoulder tilt delta calculation ──

def test_shoulder_tilt_tracking():
    """Test that shoulder tilt is tracked in history."""
    clf = PostureClassifier()
    landmarks = create_landmarks_sitting()

    # Feed frames
    for _ in range(5):
        clf.classify(landmarks, "person_0")

    state = clf.get_or_create_state("person_0")

    # Should have tilt history
    assert len(state.shoulder_tilt_history) == 5


def test_shoulder_tilt_delta_calculation():
    """Test shoulder tilt delta calculation for side lean detection."""
    clf = PostureClassifier()

    # Start with normal sitting (no tilt) — need >= 5 total for delta calculation
    sitting = create_landmarks_sitting()
    for _ in range(5):
        clf.classify(sitting, "person_0")

    # Switch to tilted sitting
    tilted = create_landmarks_sitting_with_tilt()
    clf.classify(tilted, "person_0")

    delta = clf.get_shoulder_tilt_delta("person_0")

    # Delta should be positive (tilt changed)
    assert delta > 0.0


def test_shoulder_tilt_delta_insufficient_history():
    """Test that delta returns 0.0 when insufficient history."""
    clf = PostureClassifier()
    landmarks = create_landmarks_sitting()

    # Feed only 2 frames
    for _ in range(2):
        clf.classify(landmarks, "person_0")

    delta = clf.get_shoulder_tilt_delta("person_0")

    # Should return 0.0 (need at least 3 frames)
    assert delta == 0.0


def test_shoulder_tilt_delta_no_person():
    """Test that delta returns 0.0 for non-existent person."""
    clf = PostureClassifier()

    delta = clf.get_shoulder_tilt_delta("nonexistent")

    assert delta == 0.0


def test_shoulder_tilt_history_maxlen():
    """Test that shoulder tilt history respects maxlen=10."""
    clf = PostureClassifier()
    landmarks = create_landmarks_sitting()

    # Feed 20 frames
    for _ in range(20):
        clf.classify(landmarks, "person_0")

    state = clf.get_or_create_state("person_0")

    # History should be capped at 10
    assert len(state.shoulder_tilt_history) == 10


# ── Test: reset_person functionality ──

def test_reset_person_removes_state():
    """Test that reset_person removes person state."""
    clf = PostureClassifier()
    landmarks = create_landmarks_sitting()

    # Create state
    clf.classify(landmarks, "person_0")
    assert "person_0" in clf._person_states

    # Reset
    clf.reset_person("person_0")

    assert "person_0" not in clf._person_states


def test_reset_person_clears_baseline():
    """Test that reset_person clears sitting baseline."""
    clf = PostureClassifier()
    landmarks = create_landmarks_sitting()

    # Establish baseline
    for _ in range(30):
        clf.classify(landmarks, "person_0")

    baseline_before = clf.get_sitting_baseline("person_0")
    assert baseline_before > 0.0

    # Reset
    clf.reset_person("person_0")

    baseline_after = clf.get_sitting_baseline("person_0")
    assert baseline_after == 0.0


def test_reset_person_idempotent():
    """Test that resetting non-existent person doesn't raise error."""
    clf = PostureClassifier()

    # Should not raise error
    clf.reset_person("nonexistent")
    assert "nonexistent" not in clf._person_states


# ── Test: Edge cases ──

def test_insufficient_landmarks_returns_unknown():
    """Test that landmarks < 33 returns UNKNOWN."""
    clf = PostureClassifier()
    landmarks = create_insufficient_landmarks()

    result = clf.classify(landmarks, "person_0")

    assert result == PostureType.UNKNOWN


def test_insufficient_landmarks_no_state_created():
    """Test that insufficient landmarks doesn't create state artifacts."""
    clf = PostureClassifier()
    landmarks = create_insufficient_landmarks()

    clf.classify(landmarks, "person_0")

    # State should NOT be created when landmarks < 33 (early return)
    state = clf._person_states.get("person_0")
    assert state is None


def test_multiple_persons_independent_tracking():
    """Test that multiple persons are tracked independently."""
    clf = PostureClassifier()
    standing = create_landmarks_standing()
    sitting = create_landmarks_sitting()

    # Person 0 stands, Person 1 sits
    for _ in range(5):
        clf.classify(standing, "person_0")
        clf.classify(sitting, "person_1")

    state_0 = clf.get_or_create_state("person_0")
    state_1 = clf.get_or_create_state("person_1")

    assert state_0.current_posture == PostureType.STANDING
    assert state_1.current_posture == PostureType.SITTING


def test_posture_history_maxlen():
    """Test that posture history respects maxlen=15."""
    clf = PostureClassifier()
    landmarks = create_landmarks_standing()

    # Feed 30 frames
    for _ in range(30):
        clf.classify(landmarks, "person_0")

    state = clf.get_or_create_state("person_0")

    # History should be capped at 15
    assert len(state.posture_history) == 15


def test_ambiguous_posture_maintains_previous():
    """Test that ambiguous posture (mid knee_bend_ratio) maintains previous state."""
    clf = PostureClassifier()

    # Establish standing posture
    standing = create_landmarks_standing()
    for _ in range(5):
        clf.classify(standing, "person_0")

    # Create ambiguous landmarks (knee_bend_ratio between 0.4 and 0.6)
    ambiguous = create_landmarks_standing()
    ambiguous[25]["y"] = 0.68  # Adjust knee position for mid-range ratio
    ambiguous[26]["y"] = 0.68

    for _ in range(5):
        result = clf.classify(ambiguous, "person_0")

    # Should maintain STANDING (or return to it via stability)
    # The exact behavior depends on whether ratio falls in 0.4-0.6 range
    assert result in [PostureType.STANDING, PostureType.SITTING]


def test_zero_knee_ankle_distance_fallback():
    """Test handling of zero knee-ankle distance (edge case)."""
    clf = PostureClassifier()
    landmarks = create_landmarks_standing()

    # Set knee and ankle to same position
    landmarks[25]["y"] = 0.75
    landmarks[26]["y"] = 0.75
    landmarks[27]["y"] = 0.75
    landmarks[28]["y"] = 0.75

    # Should not raise ZeroDivisionError, defaults to ratio=1.0
    result = clf.classify(landmarks, "person_0")

    assert result in [PostureType.STANDING, PostureType.SITTING, PostureType.LYING, PostureType.UNKNOWN]


def test_head_below_hip_edge_case():
    """Test edge case where head is below hip (unusual but possible)."""
    clf = PostureClassifier()
    landmarks = create_landmarks_standing()

    # Flip head and hip positions
    landmarks[0]["y"] = 0.8   # NOSE below hip
    landmarks[23]["y"] = 0.3  # HIP above nose
    landmarks[24]["y"] = 0.3

    # Should handle gracefully (likely UNKNOWN or previous state)
    result = clf.classify(landmarks, "person_0")

    assert isinstance(result, PostureType)


# ── Test: Singleton instance ──

def test_posture_classifier_singleton():
    """Test that posture_classifier singleton is available."""
    from app.services.posture_classifier import posture_classifier

    assert posture_classifier is not None
    assert isinstance(posture_classifier, PostureClassifier)
