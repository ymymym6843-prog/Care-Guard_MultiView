"""
Walking Aid Detector unit tests.

Tests:
- WalkingAidDetector graceful degradation (no model)
- MediaPipeWalkingAidHeuristic conditions
- WalkingAidStateTracker state transitions
- AlertManager walking aid alert integration
"""

import pytest

from app.services.walking_aid_detector import (
    WalkingAidDetection,
    WalkingAidDetector,
    MediaPipeWalkingAidHeuristic,
    WalkingAidStateTracker,
    HeuristicResult,
    WALKING_AID_CLASSES,
)


# ──────────────────────────────────────────────
# WalkingAidDetector tests
# ──────────────────────────────────────────────

class TestWalkingAidDetector:
    def test_detector_disabled_without_model(self):
        """Model file not found -> disabled, returns empty list."""
        detector = WalkingAidDetector()
        # Force model path to non-existent file
        from pathlib import Path
        detector._model_path = Path("/nonexistent/model.onnx")
        detector._enabled = None  # Reset lazy check

        assert detector.enabled is False

        import numpy as np
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        result = detector.detect(frame)
        assert result == []

    def test_detect_returns_list(self):
        """Detect always returns a list (even empty)."""
        detector = WalkingAidDetector()
        detector._enabled = False

        import numpy as np
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        result = detector.detect(frame)
        assert isinstance(result, list)

    def test_walking_aid_classes(self):
        """Verify class names are defined."""
        assert len(WALKING_AID_CLASSES) == 4
        assert "walker" in WALKING_AID_CLASSES
        assert "cane" in WALKING_AID_CLASSES
        assert "crutch" in WALKING_AID_CLASSES
        assert "wheelchair" in WALKING_AID_CLASSES

    def test_close_resets_state(self):
        detector = WalkingAidDetector()
        detector._enabled = True
        detector.close()
        assert detector._model is None
        assert detector._enabled is None


# ──────────────────────────────────────────────
# MediaPipeWalkingAidHeuristic tests
# ──────────────────────────────────────────────

def _make_landmarks_walker_pose():
    """Create landmarks simulating walker usage:
    - Wrists below hips
    - Wrists spread wider than shoulders
    """
    base = [{"x": 0.5, "y": 0.5, "z": 0.0, "visibility": 0.9}] * 33

    # Shoulders (indices 11, 12) - width 0.1
    base[11] = {"x": 0.45, "y": 0.3, "z": 0.0, "visibility": 0.9}  # LEFT_SHOULDER
    base[12] = {"x": 0.55, "y": 0.3, "z": 0.0, "visibility": 0.9}  # RIGHT_SHOULDER

    # Wrists (indices 15, 16) - below hips, spread wider than shoulders
    base[15] = {"x": 0.30, "y": 0.75, "z": 0.0, "visibility": 0.9}  # LEFT_WRIST
    base[16] = {"x": 0.70, "y": 0.75, "z": 0.0, "visibility": 0.9}  # RIGHT_WRIST

    # Hips (indices 23, 24) - above wrists
    base[23] = {"x": 0.45, "y": 0.6, "z": 0.0, "visibility": 0.9}  # LEFT_HIP
    base[24] = {"x": 0.55, "y": 0.6, "z": 0.0, "visibility": 0.9}  # RIGHT_HIP

    return base


def _make_landmarks_normal_pose():
    """Create landmarks for normal standing (no walker indicators)."""
    base = [{"x": 0.5, "y": 0.5, "z": 0.0, "visibility": 0.9}] * 33

    # Shoulders
    base[11] = {"x": 0.45, "y": 0.3, "z": 0.0, "visibility": 0.9}
    base[12] = {"x": 0.55, "y": 0.3, "z": 0.0, "visibility": 0.9}

    # Wrists at sides (NOT below hips)
    base[15] = {"x": 0.42, "y": 0.50, "z": 0.0, "visibility": 0.9}  # LEFT_WRIST
    base[16] = {"x": 0.58, "y": 0.50, "z": 0.0, "visibility": 0.9}  # RIGHT_WRIST

    # Hips
    base[23] = {"x": 0.45, "y": 0.6, "z": 0.0, "visibility": 0.9}
    base[24] = {"x": 0.55, "y": 0.6, "z": 0.0, "visibility": 0.9}

    return base


class TestMediaPipeHeuristic:
    def test_walker_pose_builds_confidence(self):
        """Walker-like pose should build confidence over frames."""
        heuristic = MediaPipeWalkingAidHeuristic(consecutive_frames=3)
        landmarks = _make_landmarks_walker_pose()

        # First few frames: building confidence
        for i in range(2):
            result = heuristic.estimate(landmarks, "p1")
            assert result.is_probable is False
            assert "building_confidence" in result.reason

    def test_walker_pose_becomes_probable(self):
        """After enough frames, walker is detected as probable."""
        heuristic = MediaPipeWalkingAidHeuristic(consecutive_frames=3)
        landmarks = _make_landmarks_walker_pose()

        for _ in range(3):
            result = heuristic.estimate(landmarks, "p1")

        assert result.is_probable is True
        assert result.confidence > 0.0

    def test_normal_pose_not_detected(self):
        """Normal standing pose should not trigger walker detection."""
        heuristic = MediaPipeWalkingAidHeuristic(consecutive_frames=3)
        landmarks = _make_landmarks_normal_pose()

        for _ in range(10):
            result = heuristic.estimate(landmarks, "p1")

        assert result.is_probable is False

    def test_empty_landmarks(self):
        """Empty or insufficient landmarks returns not probable."""
        heuristic = MediaPipeWalkingAidHeuristic()

        result = heuristic.estimate([], "p1")
        assert result.is_probable is False
        assert "insufficient" in result.reason

    def test_low_visibility(self):
        """Low visibility wrists -> not probable."""
        heuristic = MediaPipeWalkingAidHeuristic(consecutive_frames=1)
        landmarks = _make_landmarks_walker_pose()
        landmarks[15]["visibility"] = 0.1  # Low visibility
        landmarks[16]["visibility"] = 0.1

        result = heuristic.estimate(landmarks, "p1")
        assert result.is_probable is False
        assert "visibility" in result.reason

    def test_reset_person(self):
        """Resetting a person clears their count."""
        heuristic = MediaPipeWalkingAidHeuristic(consecutive_frames=5)
        landmarks = _make_landmarks_walker_pose()

        for _ in range(3):
            heuristic.estimate(landmarks, "p1")

        heuristic.reset_person("p1")

        # Count reset, starts from 0
        result = heuristic.estimate(landmarks, "p1")
        assert "1/" in result.reason  # count is 1 again

    def test_cleanup(self):
        """Cleanup removes stale person IDs."""
        heuristic = MediaPipeWalkingAidHeuristic()
        landmarks = _make_landmarks_walker_pose()

        heuristic.estimate(landmarks, "p1")
        heuristic.estimate(landmarks, "p2")

        heuristic.cleanup({"p1"})  # p2 is stale
        assert "p2" not in heuristic._person_counts

    def test_independent_person_tracking(self):
        """Different persons tracked independently."""
        heuristic = MediaPipeWalkingAidHeuristic(consecutive_frames=2)
        walker = _make_landmarks_walker_pose()
        normal = _make_landmarks_normal_pose()

        heuristic.estimate(walker, "p1")
        heuristic.estimate(normal, "p2")
        heuristic.estimate(walker, "p1")

        r1 = heuristic.estimate(walker, "p1")
        r2 = heuristic.estimate(normal, "p2")

        assert r1.is_probable is True
        assert r2.is_probable is False


# ──────────────────────────────────────────────
# WalkingAidStateTracker tests
# ──────────────────────────────────────────────

def _make_aid_detection(class_name="walker", cx=0.5, cy=0.7, conf=0.8):
    cls_id = WALKING_AID_CLASSES.index(class_name)
    return WalkingAidDetection(
        class_id=cls_id,
        class_name=class_name,
        confidence=conf,
        bbox_xyxy=(cx - 0.05, cy - 0.05, cx + 0.05, cy + 0.05),
        center_xy=(cx, cy),
    )


class TestWalkingAidStateTracker:
    def test_initial_state(self):
        tracker = WalkingAidStateTracker()
        state = tracker.get_state("p1")
        assert state.aid_type is None
        assert state.established is False
        assert state.is_missing is False
        assert state.detection_count == 0

    def test_yolo_detection_increments_count(self):
        tracker = WalkingAidStateTracker()
        det = _make_aid_detection("walker", cx=0.5, cy=0.7)
        no_heuristic = HeuristicResult(is_probable=False, confidence=0.0, reason="")

        state = tracker.update("p1", (0.5, 0.5), [det], no_heuristic, frame_num=1)

        assert state.aid_type == "walker"
        assert state.detection_count == 1
        assert state.established is False

    def test_establish_after_enough_frames(self):
        tracker = WalkingAidStateTracker()
        tracker._establish_frames = 3  # Lower for testing
        det = _make_aid_detection("walker", cx=0.5, cy=0.7)
        no_heuristic = HeuristicResult(is_probable=False, confidence=0.0, reason="")

        for i in range(3):
            state = tracker.update("p1", (0.5, 0.5), [det], no_heuristic, frame_num=i)

        assert state.established is True
        assert state.aid_type == "walker"

    def test_missing_after_established(self):
        tracker = WalkingAidStateTracker()
        tracker._establish_frames = 2
        tracker._missing_frames = 3
        det = _make_aid_detection("walker", cx=0.5, cy=0.7)
        no_heuristic = HeuristicResult(is_probable=False, confidence=0.0, reason="")

        # Establish
        for i in range(2):
            tracker.update("p1", (0.5, 0.5), [det], no_heuristic, frame_num=i)

        # Now no detection -> missing count increases
        for i in range(3):
            state = tracker.update("p1", (0.5, 0.5), [], no_heuristic, frame_num=10 + i)

        assert state.is_missing is True
        assert state.established is True

    def test_heuristic_supplements_detection(self):
        tracker = WalkingAidStateTracker()
        tracker._establish_frames = 2
        heuristic_yes = HeuristicResult(is_probable=True, confidence=0.5, reason="test")

        for i in range(2):
            state = tracker.update("p1", (0.5, 0.5), [], heuristic_yes, frame_num=i)

        assert state.established is True
        assert state.aid_type == "walker"  # Heuristic defaults to walker

    def test_no_match_far_detection(self):
        """Detection too far from person -> not matched."""
        tracker = WalkingAidStateTracker()
        tracker._assoc_dist = 0.1  # Strict matching
        det = _make_aid_detection("walker", cx=0.9, cy=0.9)  # Far from person at (0.1, 0.1)
        no_heuristic = HeuristicResult(is_probable=False, confidence=0.0, reason="")

        state = tracker.update("p1", (0.1, 0.1), [det], no_heuristic, frame_num=1)

        assert state.detection_count == 0

    def test_cleanup_removes_stale(self):
        tracker = WalkingAidStateTracker()
        tracker.get_state("p1")
        tracker.get_state("p2")

        tracker.cleanup({"p1"})

        assert "p2" not in tracker._states
        assert "p1" in tracker._states

    def test_count_established(self):
        tracker = WalkingAidStateTracker()
        tracker._establish_frames = 1
        det = _make_aid_detection("walker")
        no_heuristic = HeuristicResult(is_probable=False, confidence=0.0, reason="")

        tracker.update("p1", (0.5, 0.5), [det], no_heuristic, frame_num=1)
        tracker.update("p2", (0.5, 0.5), [det], no_heuristic, frame_num=1)

        assert tracker.count_established() == 2

    def test_get_missing_alerts(self):
        tracker = WalkingAidStateTracker()
        tracker._establish_frames = 1
        tracker._missing_frames = 1
        det = _make_aid_detection("walker")
        no_heuristic = HeuristicResult(is_probable=False, confidence=0.0, reason="")

        # Establish
        tracker.update("p1", (0.5, 0.5), [det], no_heuristic, frame_num=1)

        # Go missing
        tracker.update("p1", (0.5, 0.5), [], no_heuristic, frame_num=2)

        alerts = tracker.get_missing_alerts()
        assert len(alerts) == 1
        assert alerts[0][0] == "p1"
        assert alerts[0][1].is_missing is True

    def test_wheelchair_detection(self):
        tracker = WalkingAidStateTracker()
        tracker._establish_frames = 1
        det = _make_aid_detection("wheelchair", cx=0.5, cy=0.6)
        no_heuristic = HeuristicResult(is_probable=False, confidence=0.0, reason="")

        state = tracker.update("p1", (0.5, 0.5), [det], no_heuristic, frame_num=1)
        assert state.aid_type == "wheelchair"
        assert state.established is True


# ──────────────────────────────────────────────
# AlertManager walking aid integration test
# ──────────────────────────────────────────────

class TestAlertManagerWalkingAid:
    def test_walking_aid_missing_info_only(self):
        """보행도구 분실은 알림 레벨을 변경하지 않음 (정보 표시만)."""
        from app.services.alert_manager import AlertManager, AlertState
        from app.services.walking_aid_detector import WalkingAidState

        mgr = AlertManager()
        aid_state = WalkingAidState(
            aid_type="walker",
            detection_count=20,
            missing_count=15,
            established=True,
            is_missing=True,
        )

        result = mgr.update_walking_aid_alert("p1", aid_state)

        assert result["walking_aid_missing"] is True
        assert result["changed"] is True
        # 알림 상태는 NORMAL 유지 (MONITORING으로 변경하지 않음)
        assert mgr._person_alerts["p1"].state == AlertState.NORMAL
        assert mgr._person_alerts["p1"].walking_aid_warned is True

    def test_walking_aid_does_not_affect_fall_state(self):
        """보행도구 분실은 낙상 알림 상태에 영향을 주지 않음."""
        from app.services.alert_manager import AlertManager, AlertState
        from app.services.walking_aid_detector import WalkingAidState

        mgr = AlertManager()
        # 낙상 경고 활성화
        mgr.update("p1", is_fallen=True, confidence=0.9, fall_duration=3.0, fall_type="front_fall")

        aid_state = WalkingAidState(
            aid_type="walker",
            established=True,
            is_missing=True,
        )
        result = mgr.update_walking_aid_alert("p1", aid_state)

        # 낙상 상태 그대로 유지
        assert mgr._person_alerts["p1"].state in (AlertState.WARNING, AlertState.DANGER)
        assert mgr._person_alerts["p1"].walking_aid_warned is True

    def test_walking_aid_not_missing_no_alert(self):
        from app.services.alert_manager import AlertManager, AlertState
        from app.services.walking_aid_detector import WalkingAidState

        mgr = AlertManager()
        aid_state = WalkingAidState(
            aid_type="walker",
            established=True,
            is_missing=False,  # Not missing
        )

        result = mgr.update_walking_aid_alert("p1", aid_state)
        assert result["changed"] is False
