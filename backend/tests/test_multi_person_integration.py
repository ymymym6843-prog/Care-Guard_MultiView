"""
Comprehensive integration tests for multi-person fall detection pipeline.

Tests the interaction between:
- FallDetector: Per-person state tracking, rule-based + ML ensemble scoring
- AlertManager: Per-person alert state machine (NORMAL → MONITORING → WARNING → DANGER → ACKNOWLEDGED)
- PersonTracker: IoU-based tracking with stable person_id assignment

Architecture:
- Each person has independent FallDetector state (PersonState) and AlertManager state (PersonAlert)
- Global alert state reflects the most severe individual alert
- PersonTracker maintains ID stability across frames via bounding box IoU matching
"""

import time
from unittest.mock import MagicMock, patch

import pytest

from app.services.alert_manager import AlertManager, AlertState
from app.services.fall_detector import FallDetector
from app.services.person_tracker import PersonTracker
from app.services.posture_classifier import PostureType


class TestMultiPersonIndependentStateTracking:
    """Test that each person's fall detection and alert state is independent."""

    @pytest.fixture(autouse=True)
    def _setup_mocks(self):
        """Mock ML classifier and posture classifier, disable grace periods."""
        with patch("app.services.fall_detector.fall_classifier") as mock_clf, \
             patch("app.services.fall_detector.posture_classifier") as mock_pc, \
             patch("app.services.fall_detector.settings") as mock_settings:

            # Disable ML classifier (pure rule-based)
            mock_clf.enabled = False
            mock_clf.add_frame = lambda *a, **kw: None

            # Mock posture classifier to return STANDING by default
            mock_pc.classify.return_value = PostureType.STANDING
            mock_pc.get_or_create_state.return_value = MagicMock(
                sitting_baseline_frames=0, posture_history=[]
            )
            mock_pc.get_shoulder_tilt_delta.return_value = 0.0
            mock_pc.get_sitting_baseline.return_value = 0.0

            # Instant detection settings
            mock_settings.FALL_GRACE_FRAMES = 0
            mock_settings.FALL_CONSECUTIVE_FRAMES = 1
            mock_settings.FALL_HEAD_HIP_THRESHOLD = 0.05
            mock_settings.FALL_COOLDOWN_SECONDS = 3.0
            mock_settings.FALL_RAPID_DESCENT_THRESHOLD = 0.15
            mock_settings.FALL_HORIZONTAL_ANGLE = 45.0
            mock_settings.FALL_COMPOSITE_THRESHOLD = 0.5
            mock_settings.FALL_RULE_WEIGHT = 0.5
            mock_settings.FALL_ML_WEIGHT = 0.5
            mock_settings.FALL_MIN_VISIBILITY = 0.5
            mock_settings.FALL_LOW_VIS_MIN = 0.3
            mock_settings.FALL_LOW_VIS_ACCUM_FRAMES = 3
            mock_settings.FALL_LOW_VIS_ACCUM_THRESHOLD = 0.35
            mock_settings.FALL_POST_FALL_CHECK_FRAMES = 10
            mock_settings.FALL_POST_FALL_MAX_VARIANCE = 0.0005
            mock_settings.FALL_LYING_STABLE_EXEMPT_FRAMES = 60
            mock_settings.FALL_SEATED_HEAD_HIP_THRESHOLD = 0.02
            mock_settings.FALL_SEATED_RAPID_DESCENT_THRESHOLD = 0.12
            mock_settings.FALL_SEATED_FORWARD_SLUMP_THRESHOLD = 0.25
            mock_settings.FALL_SEATED_LATERAL_TILT_THRESHOLD = 0.20
            mock_settings.FALL_SEATED_HEIGHT_DROP_RATIO = 0.45
            mock_settings.FALL_SEATED_BASELINE_MIN_FRAMES = 30
            mock_settings.FALL_SEATED_HORIZONTAL_ANGLE = 45.0
            mock_settings.FALL_PRE_IMPACT_THRESHOLD = 0.25
            mock_settings.FALL_PRE_IMPACT_ML_THRESHOLD = 0.4
            mock_settings.FALL_ENHANCED_RULES_ENABLED = False
            mock_settings.FALL_N1_ACCEL_THRESHOLD = 0.02
            mock_settings.FALL_N1_VELOCITY_GATE = 0.05
            mock_settings.FALL_N2_ARM_SPREAD_VEL = 0.08
            mock_settings.FALL_N2_WRIST_DROP = 0.02
            mock_settings.FALL_N3_MIN_ANKLE_SPAN = 0.05
            mock_settings.FALL_N3_GROWING_FRAMES = 2
            mock_settings.FALL_N4_ANGLE_RATE = 15.0
            mock_settings.FALL_N4_ANGLE_LIMIT = 130.0
            mock_settings.FALL_N5_STANDING_TILT = 0.30
            mock_settings.FALL_N6_ACCEL_RATIO = 1.3
            mock_settings.FALL_PROFILE = "balanced"
            mock_settings.FALL_WARNING_SECONDS = 1.5
            mock_settings.FALL_DANGER_SECONDS = 5.0

            yield mock_clf, mock_pc, mock_settings

    def test_three_persons_independent_fall_states(
        self, mock_landmarks_standing, mock_landmarks_fallen
    ):
        """
        Test 3 people with different states:
        - person_0: fallen
        - person_1: standing (normal)
        - person_2: sitting (posture changed)

        Each person's fall_detector state should be independent.
        """
        # Arrange
        detector = FallDetector()

        # Act
        # Person 0 falls
        result_p0 = detector.detect(mock_landmarks_fallen, person_id="person_0")

        # Person 1 standing normally
        result_p1 = detector.detect(mock_landmarks_standing, person_id="person_1")

        # Person 2 standing (separate state)
        result_p2 = detector.detect(mock_landmarks_standing, person_id="person_2")

        # Assert
        assert result_p0["is_fallen"] is True
        assert result_p0["confidence"] >= 0.5

        assert result_p1["is_fallen"] is False
        assert result_p1["confidence"] < 0.5

        assert result_p2["is_fallen"] is False
        assert result_p2["confidence"] < 0.5

        # Verify independent state storage
        assert "person_0" in detector._person_states
        assert "person_1" in detector._person_states
        assert "person_2" in detector._person_states

        assert detector._person_states["person_0"].is_fallen is True
        assert detector._person_states["person_1"].is_fallen is False
        assert detector._person_states["person_2"].is_fallen is False

    def test_three_persons_independent_alert_states(self, mock_landmarks_fallen):
        """
        Test AlertManager with 3 people in different alert states:
        - person_0: DANGER
        - person_1: MONITORING
        - person_2: NORMAL

        Each person should have independent alert state.
        """
        # Arrange
        detector = FallDetector()
        alert_manager = AlertManager()
        alert_manager.warning_seconds = 1.5
        alert_manager.danger_seconds = 5.0

        # Act
        # Person 0 → DANGER (actual fall type → immediate DANGER)
        fall_result_p0 = detector.detect(mock_landmarks_fallen, person_id="person_0")
        alert_manager.update(
            person_id="person_0",
            is_fallen=fall_result_p0["is_fallen"],
            confidence=fall_result_p0["confidence"],
            fall_duration=6.0,
            fall_type="front_fall",  # actual fall → immediate DANGER
        )

        # Person 1 → MONITORING (confidence < 0.5)
        fall_result_p1 = detector.detect(mock_landmarks_fallen, person_id="person_1")
        alert_manager.update(
            person_id="person_1",
            is_fallen=fall_result_p1["is_fallen"],
            confidence=0.35,  # < 0.5 → MONITORING
            fall_duration=0.5,
        )

        # Person 2 → NORMAL (not fallen)
        alert_manager.update(
            person_id="person_2",
            is_fallen=False,
            confidence=0.0,
            fall_duration=0.0,
        )

        # Assert
        assert alert_manager._person_alerts["person_0"].state == AlertState.DANGER
        assert alert_manager._person_alerts["person_1"].state == AlertState.MONITORING
        assert alert_manager._person_alerts["person_2"].state == AlertState.NORMAL

        # Global state should be most severe (DANGER)
        assert alert_manager.global_state == AlertState.DANGER

    def test_global_alert_state_reflects_most_severe(self):
        """
        Test that global alert state is the maximum severity across all persons.

        Severity order: NORMAL < ACKNOWLEDGED < MONITORING < WARNING < DANGER
        """
        # Arrange
        alert_manager = AlertManager()
        alert_manager.warning_seconds = 1.5
        alert_manager.danger_seconds = 5.0

        # Act
        # Person A: DANGER (actual fall type)
        alert_manager.update("person_A", is_fallen=True, confidence=0.9, fall_duration=6.0, fall_type="front_fall")

        # Person B: MONITORING (confidence < 0.5)
        alert_manager.update("person_B", is_fallen=True, confidence=0.35, fall_duration=0.5)

        # Person C: NORMAL
        alert_manager.update("person_C", is_fallen=False, confidence=0.0, fall_duration=0.0)

        # Assert
        assert alert_manager.global_state == AlertState.DANGER

        # Now acknowledge Person A
        alert_manager.acknowledge(person_id="person_A")

        # Global should downgrade to MONITORING (Person B, confidence < 0.5)
        assert alert_manager.global_state == AlertState.MONITORING


class TestAlertStateProgression:
    """Test alert state transitions for multiple persons."""

    @pytest.fixture(autouse=True)
    def _setup_mocks(self):
        """Mock dependencies."""
        with patch("app.services.fall_detector.fall_classifier") as mock_clf, \
             patch("app.services.fall_detector.posture_classifier") as mock_pc, \
             patch("app.services.fall_detector.settings") as mock_settings:

            mock_clf.enabled = False
            mock_clf.add_frame = lambda *a, **kw: None
            mock_pc.classify.return_value = PostureType.STANDING
            mock_pc.get_or_create_state.return_value = MagicMock(
                sitting_baseline_frames=0, posture_history=[]
            )
            mock_pc.get_shoulder_tilt_delta.return_value = 0.0
            mock_pc.get_sitting_baseline.return_value = 0.0

            mock_settings.FALL_GRACE_FRAMES = 0
            mock_settings.FALL_CONSECUTIVE_FRAMES = 1
            mock_settings.FALL_HEAD_HIP_THRESHOLD = 0.05
            mock_settings.FALL_COOLDOWN_SECONDS = 3.0
            mock_settings.FALL_RAPID_DESCENT_THRESHOLD = 0.15
            mock_settings.FALL_HORIZONTAL_ANGLE = 45.0
            mock_settings.FALL_COMPOSITE_THRESHOLD = 0.5
            mock_settings.FALL_RULE_WEIGHT = 1.0
            mock_settings.FALL_ML_WEIGHT = 0.0
            mock_settings.FALL_MIN_VISIBILITY = 0.5
            mock_settings.FALL_LOW_VIS_MIN = 0.3
            mock_settings.FALL_LOW_VIS_ACCUM_FRAMES = 3
            mock_settings.FALL_LOW_VIS_ACCUM_THRESHOLD = 0.35
            mock_settings.FALL_POST_FALL_CHECK_FRAMES = 10
            mock_settings.FALL_POST_FALL_MAX_VARIANCE = 0.0005
            mock_settings.FALL_LYING_STABLE_EXEMPT_FRAMES = 60
            mock_settings.FALL_SEATED_HEAD_HIP_THRESHOLD = 0.02
            mock_settings.FALL_SEATED_RAPID_DESCENT_THRESHOLD = 0.12
            mock_settings.FALL_SEATED_FORWARD_SLUMP_THRESHOLD = 0.25
            mock_settings.FALL_SEATED_LATERAL_TILT_THRESHOLD = 0.20
            mock_settings.FALL_SEATED_HEIGHT_DROP_RATIO = 0.45
            mock_settings.FALL_SEATED_BASELINE_MIN_FRAMES = 30
            mock_settings.FALL_SEATED_HORIZONTAL_ANGLE = 45.0
            # N1-N6 extended rule settings (Phase 26)
            mock_settings.FALL_ENHANCED_RULES_ENABLED = False
            mock_settings.FALL_N1_ACCEL_THRESHOLD = 0.02
            mock_settings.FALL_N1_VELOCITY_GATE = 0.05
            mock_settings.FALL_N2_ARM_SPREAD_VEL = 0.08
            mock_settings.FALL_N2_WRIST_DROP = 0.02
            mock_settings.FALL_N3_MIN_ANKLE_SPAN = 0.05
            mock_settings.FALL_N3_GROWING_FRAMES = 2
            mock_settings.FALL_N4_ANGLE_RATE = 15.0
            mock_settings.FALL_N4_ANGLE_LIMIT = 130.0
            mock_settings.FALL_N5_STANDING_TILT = 0.30
            mock_settings.FALL_N6_ACCEL_RATIO = 1.3
            mock_settings.FALL_PRE_IMPACT_THRESHOLD = 0.25
            mock_settings.FALL_PRE_IMPACT_ML_THRESHOLD = 0.4

            yield mock_clf, mock_pc, mock_settings

    def test_acknowledge_person_A_updates_global_state(self):
        """
        Test acknowledging one person updates global state correctly.

        Scenario:
        - Person A in DANGER, Person B in MONITORING, Person C normal
        - Acknowledge Person A → global state should become MONITORING
        """
        # Arrange
        alert_manager = AlertManager()
        alert_manager.warning_seconds = 1.5
        alert_manager.danger_seconds = 5.0

        # Person A → DANGER (actual fall type → immediate)
        alert_manager.update("person_A", is_fallen=True, confidence=0.9, fall_duration=6.0, fall_type="front_fall")
        # Person B → MONITORING (confidence < 0.5)
        alert_manager.update("person_B", is_fallen=True, confidence=0.35, fall_duration=0.5)
        # Person C → NORMAL
        alert_manager.update("person_C", is_fallen=False, confidence=0.0, fall_duration=0.0)

        assert alert_manager.global_state == AlertState.DANGER

        # Act
        result = alert_manager.acknowledge(person_id="person_A", acknowledged_by="nurse_1")

        # Assert
        assert result is True
        assert alert_manager._person_alerts["person_A"].state == AlertState.ACKNOWLEDGED
        assert alert_manager._person_alerts["person_A"].acknowledged_by == "nurse_1"
        assert alert_manager.global_state == AlertState.MONITORING

    def test_monitoring_to_warning_to_danger_with_duration(self):
        """
        Test full progression: MONITORING → WARNING → DANGER for one person.

        Uses actual fall_duration and increasing confidence to trigger transitions.
        """
        # Arrange
        alert_manager = AlertManager()
        alert_manager.warning_seconds = 2.0

        # Act & Assert
        # Initial fall → MONITORING (confidence < 0.5)
        result1 = alert_manager.update(
            "person_0", is_fallen=True, confidence=0.35, fall_duration=0.5
        )
        assert result1["state"] == AlertState.MONITORING.value
        assert result1["changed"] is True

        # Duration exceeds warning_seconds → WARNING (keep low confidence to avoid instant DANGER)
        result2 = alert_manager.update(
            "person_0", is_fallen=True, confidence=0.35, fall_duration=2.5
        )
        assert result2["state"] == AlertState.WARNING.value
        assert result2["changed"] is True

        # DANGER (confidence increases to >= 0.70, max_conf >= 0.70, threshold=0.5s)
        result3 = alert_manager.update(
            "person_0", is_fallen=True, confidence=0.75, fall_duration=5.5
        )
        assert result3["state"] == AlertState.DANGER.value
        assert result3["changed"] is True


class TestPersonTrackerStability:
    """Test PersonTracker ID stability with multi-person scenarios."""

    def test_two_persons_id_stability_across_frames(self):
        """
        Test that two persons maintain stable IDs across 10 frames with slight movement.

        Simulates two people moving slightly (bboxes overlap < IOU_THRESHOLD but still trackable).
        """
        # Arrange
        tracker = PersonTracker(max_lost_seconds=2.0)

        # Mock pose objects with bbox attribute
        class MockPose:
            def __init__(self, bbox):
                self.bbox = bbox
                self.person_id = None

        # Act - Frame 1: Two persons appear
        pose_0 = MockPose(bbox=(0.1, 0.2, 0.4, 0.8))
        pose_1 = MockPose(bbox=(0.6, 0.3, 0.9, 0.9))
        assignments_1 = tracker.update([pose_0, pose_1])

        id_p0_frame1 = assignments_1[0]
        id_p1_frame1 = assignments_1[1]

        # Frame 2-10: Slight movement (high IoU)
        for i in range(2, 11):
            # Person 0 moves right slightly
            pose_0 = MockPose(bbox=(0.1 + i * 0.01, 0.2, 0.4 + i * 0.01, 0.8))
            # Person 1 moves left slightly
            pose_1 = MockPose(bbox=(0.6 - i * 0.01, 0.3, 0.9 - i * 0.01, 0.9))

            assignments = tracker.update([pose_0, pose_1])

            # Assert IDs remain stable
            assert assignments[0] == id_p0_frame1
            assert assignments[1] == id_p1_frame1

    def test_one_person_disappears_other_remains_stable(self):
        """
        Test that when one person disappears (timeout), the other's ID remains stable.
        We keep person_1 alive by continuously updating before timeout.
        """
        # Arrange
        tracker = PersonTracker(max_lost_seconds=0.3)

        class MockPose:
            def __init__(self, bbox):
                self.bbox = bbox
                self.person_id = None

        # Act
        # Frame 1: Two persons
        pose_0 = MockPose(bbox=(0.1, 0.2, 0.4, 0.8))
        pose_1 = MockPose(bbox=(0.6, 0.3, 0.9, 0.9))
        assignments_1 = tracker.update([pose_0, pose_1])
        id_p0 = assignments_1[0]
        id_p1 = assignments_1[1]

        # Keep person_1 alive but not person_0 (send only person_1 for several updates)
        for _ in range(3):
            time.sleep(0.15)
            pose_1_update = MockPose(bbox=(0.6, 0.3, 0.9, 0.9))
            tracker.update([pose_1_update])

        # After ~0.45s, person_0 should have timed out (max_lost=0.3s)
        # Final update with person_1 only
        pose_1_final = MockPose(bbox=(0.6, 0.3, 0.9, 0.9))
        assignments_2 = tracker.update([pose_1_final])

        # Assert
        # person_1 should remain with same ID
        assert assignments_2[0] == id_p1

    def test_overlapping_bboxes_greedy_matching(self):
        """
        Test that greedy IoU matching handles overlapping bboxes correctly.

        When multiple current detections could match multiple tracked persons,
        the highest IoU pairs should be matched first.
        """
        # Arrange
        tracker = PersonTracker()

        class MockPose:
            def __init__(self, bbox):
                self.bbox = bbox
                self.person_id = None

        # Act
        # Frame 1: Two persons
        pose_0 = MockPose(bbox=(0.1, 0.1, 0.5, 0.5))
        pose_1 = MockPose(bbox=(0.5, 0.5, 0.9, 0.9))
        assignments_1 = tracker.update([pose_0, pose_1])
        id_p0 = assignments_1[0]
        id_p1 = assignments_1[1]

        # Frame 2: Both move toward center (partial overlap)
        pose_0_moved = MockPose(bbox=(0.2, 0.2, 0.6, 0.6))  # Moved right/down
        pose_1_moved = MockPose(bbox=(0.4, 0.4, 0.8, 0.8))  # Moved left/up

        assignments_2 = tracker.update([pose_0_moved, pose_1_moved])

        # Assert
        # IDs should be preserved based on best IoU match
        assert assignments_2[0] == id_p0
        assert assignments_2[1] == id_p1


class TestMixedFallTypesAndBypassLogic:
    """Test alert bypass logic with different fall types."""

    @pytest.fixture(autouse=True)
    def _setup_mocks(self):
        """Mock dependencies with ML enabled for fall_type detection."""
        with patch("app.services.fall_detector.fall_classifier") as mock_clf, \
             patch("app.services.fall_detector.posture_classifier") as mock_pc, \
             patch("app.services.fall_detector.settings") as mock_settings:

            # Enable ML for fall_type classification
            mock_clf.enabled = True
            mock_clf.add_frame = lambda *a, **kw: None

            mock_pc.classify.return_value = PostureType.STANDING
            mock_pc.get_or_create_state.return_value = MagicMock(
                sitting_baseline_frames=0, posture_history=[]
            )
            mock_pc.get_shoulder_tilt_delta.return_value = 0.0
            mock_pc.get_sitting_baseline.return_value = 0.0

            mock_settings.FALL_GRACE_FRAMES = 0
            mock_settings.FALL_CONSECUTIVE_FRAMES = 1
            mock_settings.FALL_HEAD_HIP_THRESHOLD = 0.05
            mock_settings.FALL_COOLDOWN_SECONDS = 3.0
            mock_settings.FALL_RAPID_DESCENT_THRESHOLD = 0.15
            mock_settings.FALL_HORIZONTAL_ANGLE = 45.0
            mock_settings.FALL_COMPOSITE_THRESHOLD = 0.5
            mock_settings.FALL_RULE_WEIGHT = 0.5
            mock_settings.FALL_ML_WEIGHT = 0.5
            mock_settings.FALL_MIN_VISIBILITY = 0.5
            mock_settings.FALL_LOW_VIS_MIN = 0.3
            mock_settings.FALL_LOW_VIS_ACCUM_FRAMES = 3
            mock_settings.FALL_LOW_VIS_ACCUM_THRESHOLD = 0.35
            mock_settings.FALL_POST_FALL_CHECK_FRAMES = 10
            mock_settings.FALL_POST_FALL_MAX_VARIANCE = 0.0005
            mock_settings.FALL_LYING_STABLE_EXEMPT_FRAMES = 60
            mock_settings.FALL_SEATED_HEAD_HIP_THRESHOLD = 0.02
            mock_settings.FALL_SEATED_RAPID_DESCENT_THRESHOLD = 0.12
            mock_settings.FALL_SEATED_FORWARD_SLUMP_THRESHOLD = 0.25
            mock_settings.FALL_SEATED_LATERAL_TILT_THRESHOLD = 0.20
            mock_settings.FALL_SEATED_HEIGHT_DROP_RATIO = 0.45
            mock_settings.FALL_SEATED_BASELINE_MIN_FRAMES = 30
            mock_settings.FALL_SEATED_HORIZONTAL_ANGLE = 45.0
            # N1-N6 extended rule settings (Phase 26)
            mock_settings.FALL_ENHANCED_RULES_ENABLED = False
            mock_settings.FALL_N1_ACCEL_THRESHOLD = 0.02
            mock_settings.FALL_N1_VELOCITY_GATE = 0.05
            mock_settings.FALL_N2_ARM_SPREAD_VEL = 0.08
            mock_settings.FALL_N2_WRIST_DROP = 0.02
            mock_settings.FALL_N3_MIN_ANKLE_SPAN = 0.05
            mock_settings.FALL_N3_GROWING_FRAMES = 2
            mock_settings.FALL_N4_ANGLE_RATE = 15.0
            mock_settings.FALL_N4_ANGLE_LIMIT = 130.0
            mock_settings.FALL_N5_STANDING_TILT = 0.30
            mock_settings.FALL_N6_ACCEL_RATIO = 1.3
            mock_settings.FALL_PRE_IMPACT_THRESHOLD = 0.25
            mock_settings.FALL_PRE_IMPACT_ML_THRESHOLD = 0.4

            yield mock_clf, mock_pc, mock_settings

    def test_actual_fall_bypasses_to_danger_regardless_of_confidence(
        self, _setup_mocks, mock_landmarks_fallen
    ):
        """
        Test that actual fall types (front_fall, back_fall, side_fall) bypass
        MONITORING and WARNING, going directly to DANGER regardless of confidence.
        """
        # Arrange
        mock_clf, mock_pc, mock_settings = _setup_mocks

        from app.services.fall_classifier import FallPrediction
        mock_clf.predict_detailed.return_value = FallPrediction(
            fall_probability=0.5,  # Low confidence
            fall_type="front_fall",  # Actual fall
            class_probabilities={"normal": 0.1, "front_fall": 0.7, "back_fall": 0.1, "side_fall": 0.1},
        )

        detector = FallDetector()
        alert_manager = AlertManager()

        # Act
        result = detector.detect(mock_landmarks_fallen, person_id="person_0")
        alert_result = alert_manager.update(
            person_id="person_0",
            is_fallen=result["is_fallen"],
            confidence=result["confidence"],
            fall_duration=0.3,
            fall_type=result["fall_type"],
        )

        # Assert
        assert result["fall_type"] == "front_fall"
        # Should go directly to DANGER (actual falls skip WARNING)
        assert alert_result["state"] == AlertState.DANGER.value

    def test_pre_impact_goes_to_monitoring_first(self, _setup_mocks, mock_landmarks_fallen):
        """
        Test that pre_impact (precursor) goes to MONITORING first,
        then progresses to WARNING after warning_seconds.
        """
        # Arrange
        mock_clf, mock_pc, mock_settings = _setup_mocks

        from app.services.fall_classifier import FallPrediction
        mock_clf.predict_detailed.return_value = FallPrediction(
            fall_probability=0.3,
            fall_type="pre_impact",
            class_probabilities={"normal": 0.7, "pre_impact": 0.3},
        )

        detector = FallDetector()
        alert_manager = AlertManager()
        alert_manager.warning_seconds = 1.5

        # Act
        result = detector.detect(mock_landmarks_fallen, person_id="person_0")

        # Initial detection → MONITORING (override confidence < 0.5 for MONITORING path)
        alert_result_1 = alert_manager.update(
            person_id="person_0",
            is_fallen=result["is_fallen"],
            confidence=0.35,  # < 0.5 → MONITORING
            fall_duration=0.3,
            fall_type="pre_impact",
        )

        # After warning_seconds → WARNING
        alert_result_2 = alert_manager.update(
            person_id="person_0",
            is_fallen=result["is_fallen"],
            confidence=0.35,
            fall_duration=2.0,
            fall_type="pre_impact",
        )

        # Assert
        assert alert_result_1["state"] == AlertState.MONITORING.value
        assert alert_result_2["state"] == AlertState.WARNING.value

    def test_multiple_persons_different_fall_types_handled_independently(
        self, _setup_mocks, mock_landmarks_fallen
    ):
        """
        Test that multiple persons with different fall types are handled independently.

        - Person A: front_fall (actual) → DANGER immediately
        - Person B: pre_impact → MONITORING first
        """
        # Arrange
        mock_clf, mock_pc, mock_settings = _setup_mocks

        from app.services.fall_classifier import FallPrediction

        detector = FallDetector()
        alert_manager = AlertManager()
        alert_manager.warning_seconds = 1.5

        # Act
        # Person A: front_fall
        mock_clf.predict_detailed.return_value = FallPrediction(
            fall_probability=0.7,
            fall_type="front_fall",
            class_probabilities={"normal": 0.1, "front_fall": 0.8, "back_fall": 0.05, "side_fall": 0.05},
        )
        result_A = detector.detect(mock_landmarks_fallen, person_id="person_A")
        alert_A = alert_manager.update(
            person_id="person_A",
            is_fallen=result_A["is_fallen"],
            confidence=result_A["confidence"],
            fall_duration=0.3,
            fall_type=result_A["fall_type"],
        )

        # Person B: pre_impact → MONITORING (override confidence < 0.5)
        mock_clf.predict_detailed.return_value = FallPrediction(
            fall_probability=0.3,
            fall_type="pre_impact",
            class_probabilities={"normal": 0.7, "pre_impact": 0.3},
        )
        result_B = detector.detect(mock_landmarks_fallen, person_id="person_B")
        alert_B = alert_manager.update(
            person_id="person_B",
            is_fallen=result_B["is_fallen"],
            confidence=0.35,  # < 0.5 → MONITORING
            fall_duration=0.3,
            fall_type="pre_impact",
        )

        # Assert
        assert alert_A["state"] == AlertState.DANGER.value  # Actual fall → immediate DANGER
        assert alert_B["state"] == AlertState.MONITORING.value

        # Global state should be DANGER (most severe)
        assert alert_manager.global_state == AlertState.DANGER


class TestBufferCleanupSimulation:
    """Test cleanup of stale person states."""

    @pytest.fixture(autouse=True)
    def _setup_mocks(self):
        """Mock dependencies."""
        with patch("app.services.fall_detector.fall_classifier") as mock_clf, \
             patch("app.services.fall_detector.posture_classifier") as mock_pc, \
             patch("app.services.fall_detector.settings") as mock_settings:

            mock_clf.enabled = False
            mock_clf.add_frame = lambda *a, **kw: None
            mock_pc.classify.return_value = PostureType.STANDING
            mock_pc.get_or_create_state.return_value = MagicMock(
                sitting_baseline_frames=0, posture_history=[]
            )
            mock_pc.get_shoulder_tilt_delta.return_value = 0.0
            mock_pc.get_sitting_baseline.return_value = 0.0

            mock_settings.FALL_GRACE_FRAMES = 0
            mock_settings.FALL_CONSECUTIVE_FRAMES = 1
            mock_settings.FALL_HEAD_HIP_THRESHOLD = 0.05
            mock_settings.FALL_COOLDOWN_SECONDS = 3.0
            mock_settings.FALL_RAPID_DESCENT_THRESHOLD = 0.15
            mock_settings.FALL_HORIZONTAL_ANGLE = 45.0
            mock_settings.FALL_COMPOSITE_THRESHOLD = 0.5
            mock_settings.FALL_RULE_WEIGHT = 1.0
            mock_settings.FALL_ML_WEIGHT = 0.0
            mock_settings.FALL_MIN_VISIBILITY = 0.5
            mock_settings.FALL_LOW_VIS_MIN = 0.3
            mock_settings.FALL_LOW_VIS_ACCUM_FRAMES = 3
            mock_settings.FALL_LOW_VIS_ACCUM_THRESHOLD = 0.35
            mock_settings.FALL_POST_FALL_CHECK_FRAMES = 10
            mock_settings.FALL_POST_FALL_MAX_VARIANCE = 0.0005
            mock_settings.FALL_LYING_STABLE_EXEMPT_FRAMES = 60
            mock_settings.FALL_SEATED_HEAD_HIP_THRESHOLD = 0.02
            mock_settings.FALL_SEATED_RAPID_DESCENT_THRESHOLD = 0.12
            mock_settings.FALL_SEATED_FORWARD_SLUMP_THRESHOLD = 0.25
            mock_settings.FALL_SEATED_LATERAL_TILT_THRESHOLD = 0.20
            mock_settings.FALL_SEATED_HEIGHT_DROP_RATIO = 0.45
            mock_settings.FALL_SEATED_BASELINE_MIN_FRAMES = 30
            mock_settings.FALL_SEATED_HORIZONTAL_ANGLE = 45.0
            # N1-N6 extended rule settings (Phase 26)
            mock_settings.FALL_ENHANCED_RULES_ENABLED = False
            mock_settings.FALL_N1_ACCEL_THRESHOLD = 0.02
            mock_settings.FALL_N1_VELOCITY_GATE = 0.05
            mock_settings.FALL_N2_ARM_SPREAD_VEL = 0.08
            mock_settings.FALL_N2_WRIST_DROP = 0.02
            mock_settings.FALL_N3_MIN_ANKLE_SPAN = 0.05
            mock_settings.FALL_N3_GROWING_FRAMES = 2
            mock_settings.FALL_N4_ANGLE_RATE = 15.0
            mock_settings.FALL_N4_ANGLE_LIMIT = 130.0
            mock_settings.FALL_N5_STANDING_TILT = 0.30
            mock_settings.FALL_N6_ACCEL_RATIO = 1.3
            mock_settings.FALL_PRE_IMPACT_THRESHOLD = 0.25
            mock_settings.FALL_PRE_IMPACT_ML_THRESHOLD = 0.4

            yield mock_clf, mock_pc, mock_settings

    def test_person_tracker_cleanup_stale_persons(self, mock_landmarks_standing):
        """
        Test that PersonTracker removes stale persons after timeout.

        Scenario:
        - Create states for 5 persons
        - Only detect 2 persons in next frame (after timeout)
        - Verify 3 stale persons are removed, 2 active remain
        """
        # Arrange
        tracker = PersonTracker(max_lost_seconds=0.1)

        class MockPose:
            def __init__(self, bbox):
                self.bbox = bbox
                self.person_id = None

        # Act
        # Frame 1: 5 persons detected
        poses_frame1 = [
            MockPose(bbox=(0.0 + i * 0.2, 0.1, 0.15 + i * 0.2, 0.9))
            for i in range(5)
        ]
        assignments_1 = tracker.update(poses_frame1)

        # Verify all 5 tracked
        assert tracker.active_count == 5

        # Wait for all to expire (PersonTracker removes expired on next update)
        time.sleep(0.15)

        # Frame 2: Only 2 persons re-detected
        poses_frame2 = [
            MockPose(bbox=(0.0, 0.1, 0.15, 0.9)),
            MockPose(bbox=(0.2, 0.1, 0.35, 0.9)),
        ]
        assignments_2 = tracker.update(poses_frame2)

        # Assert
        # Only 2 persons should remain active (old 5 expired, 2 re-created)
        assert tracker.active_count == 2
        # 2 new assignments should exist
        assert len(assignments_2) == 2

    def test_fall_detector_keeps_active_person_states(self, mock_landmarks_standing):
        """
        Test that FallDetector retains states for active persons.

        Note: FallDetector does not auto-cleanup. This test verifies that
        calling reset_person() only affects the specified person.
        """
        # Arrange
        detector = FallDetector()

        # Create states for 5 persons
        for i in range(5):
            detector.detect(mock_landmarks_standing, person_id=f"person_{i}")

        assert len(detector._person_states) == 5

        # Act - Reset 3 persons manually (simulating cleanup)
        detector.reset_person("person_2")
        detector.reset_person("person_3")
        detector.reset_person("person_4")

        # Assert
        assert len(detector._person_states) == 2
        assert "person_0" in detector._person_states
        assert "person_1" in detector._person_states
        assert "person_2" not in detector._person_states
        assert "person_3" not in detector._person_states
        assert "person_4" not in detector._person_states


class TestConcurrentFallDetection:
    """Test simultaneous fall detection for multiple persons."""

    @pytest.fixture(autouse=True)
    def _setup_mocks(self):
        """Mock dependencies."""
        with patch("app.services.fall_detector.fall_classifier") as mock_clf, \
             patch("app.services.fall_detector.posture_classifier") as mock_pc, \
             patch("app.services.fall_detector.settings") as mock_settings:

            mock_clf.enabled = False
            mock_clf.add_frame = lambda *a, **kw: None
            mock_pc.classify.return_value = PostureType.STANDING
            mock_pc.get_or_create_state.return_value = MagicMock(
                sitting_baseline_frames=0, posture_history=[]
            )
            mock_pc.get_shoulder_tilt_delta.return_value = 0.0
            mock_pc.get_sitting_baseline.return_value = 0.0

            mock_settings.FALL_GRACE_FRAMES = 0
            mock_settings.FALL_CONSECUTIVE_FRAMES = 1
            mock_settings.FALL_HEAD_HIP_THRESHOLD = 0.05
            mock_settings.FALL_COOLDOWN_SECONDS = 3.0
            mock_settings.FALL_RAPID_DESCENT_THRESHOLD = 0.15
            mock_settings.FALL_HORIZONTAL_ANGLE = 45.0
            mock_settings.FALL_COMPOSITE_THRESHOLD = 0.5
            mock_settings.FALL_RULE_WEIGHT = 1.0
            mock_settings.FALL_ML_WEIGHT = 0.0
            mock_settings.FALL_MIN_VISIBILITY = 0.5
            mock_settings.FALL_LOW_VIS_MIN = 0.3
            mock_settings.FALL_LOW_VIS_ACCUM_FRAMES = 3
            mock_settings.FALL_LOW_VIS_ACCUM_THRESHOLD = 0.35
            mock_settings.FALL_POST_FALL_CHECK_FRAMES = 10
            mock_settings.FALL_POST_FALL_MAX_VARIANCE = 0.0005
            mock_settings.FALL_LYING_STABLE_EXEMPT_FRAMES = 60
            mock_settings.FALL_SEATED_HEAD_HIP_THRESHOLD = 0.02
            mock_settings.FALL_SEATED_RAPID_DESCENT_THRESHOLD = 0.12
            mock_settings.FALL_SEATED_FORWARD_SLUMP_THRESHOLD = 0.25
            mock_settings.FALL_SEATED_LATERAL_TILT_THRESHOLD = 0.20
            mock_settings.FALL_SEATED_HEIGHT_DROP_RATIO = 0.45
            mock_settings.FALL_SEATED_BASELINE_MIN_FRAMES = 30
            mock_settings.FALL_SEATED_HORIZONTAL_ANGLE = 45.0
            # N1-N6 extended rule settings (Phase 26)
            mock_settings.FALL_ENHANCED_RULES_ENABLED = False
            mock_settings.FALL_N1_ACCEL_THRESHOLD = 0.02
            mock_settings.FALL_N1_VELOCITY_GATE = 0.05
            mock_settings.FALL_N2_ARM_SPREAD_VEL = 0.08
            mock_settings.FALL_N2_WRIST_DROP = 0.02
            mock_settings.FALL_N3_MIN_ANKLE_SPAN = 0.05
            mock_settings.FALL_N3_GROWING_FRAMES = 2
            mock_settings.FALL_N4_ANGLE_RATE = 15.0
            mock_settings.FALL_N4_ANGLE_LIMIT = 130.0
            mock_settings.FALL_N5_STANDING_TILT = 0.30
            mock_settings.FALL_N6_ACCEL_RATIO = 1.3
            mock_settings.FALL_PRE_IMPACT_THRESHOLD = 0.25
            mock_settings.FALL_PRE_IMPACT_ML_THRESHOLD = 0.4

            yield mock_clf, mock_pc, mock_settings

    def test_two_persons_fall_simultaneously(self, mock_landmarks_fallen):
        """
        Test that two persons falling simultaneously are both detected independently.

        Both should get independent fall states and alert states.
        """
        # Arrange
        detector = FallDetector()
        alert_manager = AlertManager()
        alert_manager.warning_seconds = 1.5
        alert_manager.danger_seconds = 5.0

        # Act
        # Both persons fall at the same time
        result_p0 = detector.detect(mock_landmarks_fallen, person_id="person_0")
        result_p1 = detector.detect(mock_landmarks_fallen, person_id="person_1")

        # Update alerts (use moderate confidence with short duration to stay at WARNING)
        alert_p0 = alert_manager.update(
            person_id="person_0",
            is_fallen=result_p0["is_fallen"],
            confidence=0.6,  # >= 0.5 → WARNING, < 0.70 → no DANGER escalation
            fall_duration=0.3,
        )
        alert_p1 = alert_manager.update(
            person_id="person_1",
            is_fallen=result_p1["is_fallen"],
            confidence=0.6,
            fall_duration=0.3,
        )

        # Assert
        # Both should be fallen
        assert result_p0["is_fallen"] is True
        assert result_p1["is_fallen"] is True

        # Both should have independent fall states in detector
        assert detector._person_states["person_0"].is_fallen is True
        assert detector._person_states["person_1"].is_fallen is True

        # Both should be in WARNING state (confidence >= 0.5 → WARNING, < 0.70 → stays WARNING)
        assert alert_p0["state"] == AlertState.WARNING.value
        assert alert_p1["state"] == AlertState.WARNING.value

        # Global state should be WARNING (most severe among two WARNING states)
        assert alert_manager.global_state == AlertState.WARNING

    def test_concurrent_falls_with_different_severities(self, mock_landmarks_fallen):
        """
        Test that concurrent falls with different durations result in different alert states.

        - Person 0: short duration → MONITORING
        - Person 1: long duration → DANGER
        """
        # Arrange
        detector = FallDetector()
        alert_manager = AlertManager()
        alert_manager.warning_seconds = 1.5
        alert_manager.danger_seconds = 5.0

        # Act
        # Both fall
        result_p0 = detector.detect(mock_landmarks_fallen, person_id="person_0")
        result_p1 = detector.detect(mock_landmarks_fallen, person_id="person_1")

        # Person 0: short duration → MONITORING (confidence < 0.5)
        alert_manager.update(
            person_id="person_0",
            is_fallen=result_p0["is_fallen"],
            confidence=0.35,  # < 0.5 → MONITORING
            fall_duration=0.5,
        )

        # Person 1: actual fall type → immediate DANGER
        alert_manager.update(
            person_id="person_1",
            is_fallen=result_p1["is_fallen"],
            confidence=0.8,
            fall_duration=6.0,
            fall_type="back_fall",  # actual fall → immediate DANGER
        )

        # Assert
        assert alert_manager._person_alerts["person_0"].state == AlertState.MONITORING
        assert alert_manager._person_alerts["person_1"].state == AlertState.DANGER

        # Global state = most severe (DANGER)
        assert alert_manager.global_state == AlertState.DANGER

    def test_acknowledge_one_person_keeps_other_active(self, mock_landmarks_fallen):
        """
        Test that acknowledging one person's fall doesn't affect the other.
        """
        # Arrange
        detector = FallDetector()
        alert_manager = AlertManager()
        alert_manager.warning_seconds = 1.5

        # Both fall → WARNING (confidence >= 0.5, < 0.70, short duration to avoid DANGER)
        result_p0 = detector.detect(mock_landmarks_fallen, person_id="person_0")
        result_p1 = detector.detect(mock_landmarks_fallen, person_id="person_1")

        alert_manager.update(
            person_id="person_0",
            is_fallen=True,
            confidence=0.6,  # >= 0.5 → WARNING, < 0.70 → no DANGER
            fall_duration=0.3,
        )
        alert_manager.update(
            person_id="person_1",
            is_fallen=True,
            confidence=0.6,
            fall_duration=0.3,
        )

        assert alert_manager._person_alerts["person_0"].state == AlertState.WARNING
        assert alert_manager._person_alerts["person_1"].state == AlertState.WARNING

        # Act - Acknowledge only person_0
        alert_manager.acknowledge(person_id="person_0", acknowledged_by="nurse_1")

        # Assert
        assert alert_manager._person_alerts["person_0"].state == AlertState.ACKNOWLEDGED
        assert alert_manager._person_alerts["person_1"].state == AlertState.WARNING

        # Global state should still be WARNING (person_1)
        assert alert_manager.global_state == AlertState.WARNING


class TestCooldownWithMultiplePersons:
    """Test cooldown behavior with multiple persons."""

    @pytest.fixture(autouse=True)
    def _setup_mocks(self):
        """Mock dependencies."""
        with patch("app.services.fall_detector.fall_classifier") as mock_clf, \
             patch("app.services.fall_detector.posture_classifier") as mock_pc, \
             patch("app.services.fall_detector.settings") as mock_settings:

            mock_clf.enabled = False
            mock_clf.add_frame = lambda *a, **kw: None
            mock_pc.classify.return_value = PostureType.STANDING
            mock_pc.get_or_create_state.return_value = MagicMock(
                sitting_baseline_frames=0, posture_history=[]
            )
            mock_pc.get_shoulder_tilt_delta.return_value = 0.0
            mock_pc.get_sitting_baseline.return_value = 0.0

            mock_settings.FALL_GRACE_FRAMES = 0
            mock_settings.FALL_CONSECUTIVE_FRAMES = 1
            mock_settings.FALL_HEAD_HIP_THRESHOLD = 0.05
            mock_settings.FALL_COOLDOWN_SECONDS = 0.5  # Short cooldown for testing
            mock_settings.FALL_RAPID_DESCENT_THRESHOLD = 0.15
            mock_settings.FALL_HORIZONTAL_ANGLE = 45.0
            mock_settings.FALL_COMPOSITE_THRESHOLD = 0.5
            mock_settings.FALL_RULE_WEIGHT = 1.0
            mock_settings.FALL_ML_WEIGHT = 0.0
            mock_settings.FALL_MIN_VISIBILITY = 0.5
            mock_settings.FALL_LOW_VIS_MIN = 0.3
            mock_settings.FALL_LOW_VIS_ACCUM_FRAMES = 3
            mock_settings.FALL_LOW_VIS_ACCUM_THRESHOLD = 0.35
            mock_settings.FALL_POST_FALL_CHECK_FRAMES = 10
            mock_settings.FALL_POST_FALL_MAX_VARIANCE = 0.0005
            mock_settings.FALL_LYING_STABLE_EXEMPT_FRAMES = 60
            mock_settings.FALL_SEATED_HEAD_HIP_THRESHOLD = 0.02
            mock_settings.FALL_SEATED_RAPID_DESCENT_THRESHOLD = 0.12
            mock_settings.FALL_SEATED_FORWARD_SLUMP_THRESHOLD = 0.25
            mock_settings.FALL_SEATED_LATERAL_TILT_THRESHOLD = 0.20
            mock_settings.FALL_SEATED_HEIGHT_DROP_RATIO = 0.45
            mock_settings.FALL_SEATED_BASELINE_MIN_FRAMES = 30
            mock_settings.FALL_SEATED_HORIZONTAL_ANGLE = 45.0
            # N1-N6 extended rule settings (Phase 26)
            mock_settings.FALL_ENHANCED_RULES_ENABLED = False
            mock_settings.FALL_N1_ACCEL_THRESHOLD = 0.02
            mock_settings.FALL_N1_VELOCITY_GATE = 0.05
            mock_settings.FALL_N2_ARM_SPREAD_VEL = 0.08
            mock_settings.FALL_N2_WRIST_DROP = 0.02
            mock_settings.FALL_N3_MIN_ANKLE_SPAN = 0.05
            mock_settings.FALL_N3_GROWING_FRAMES = 2
            mock_settings.FALL_N4_ANGLE_RATE = 15.0
            mock_settings.FALL_N4_ANGLE_LIMIT = 130.0
            mock_settings.FALL_N5_STANDING_TILT = 0.30
            mock_settings.FALL_N6_ACCEL_RATIO = 1.3
            mock_settings.FALL_PRE_IMPACT_THRESHOLD = 0.25
            mock_settings.FALL_PRE_IMPACT_ML_THRESHOLD = 0.4

            yield mock_clf, mock_pc, mock_settings

    def test_cooldown_independent_per_person(
        self, mock_landmarks_standing, mock_landmarks_fallen
    ):
        """
        Test that cooldown is tracked independently for each person.

        - Person 0 falls, then recovers → cooldown active
        - Person 1 falls, recovers later → different cooldown timing
        """
        # Arrange
        detector = FallDetector()
        detector.cooldown_seconds = 0.5

        # Act
        # Person 0 falls
        detector.detect(mock_landmarks_fallen, person_id="person_0")
        assert detector._person_states["person_0"].is_fallen is True

        # Person 0 recovers (but cooldown prevents immediate reset)
        result_p0_recover = detector.detect(mock_landmarks_standing, person_id="person_0")
        assert result_p0_recover["is_fallen"] is True  # Still fallen due to cooldown
        assert result_p0_recover["cooldown_active"] is True

        # Person 1 falls (independent timing)
        detector.detect(mock_landmarks_fallen, person_id="person_1")
        assert detector._person_states["person_1"].is_fallen is True

        # Wait for person_0 cooldown to expire
        time.sleep(0.6)
        result_p0_final = detector.detect(mock_landmarks_standing, person_id="person_0")

        # Person 1 recovers (cooldown just started)
        result_p1_recover = detector.detect(mock_landmarks_standing, person_id="person_1")

        # Assert
        # Person 0 should be reset
        assert result_p0_final["is_fallen"] is False
        assert result_p0_final["cooldown_active"] is False

        # Person 1 should still be in cooldown
        assert result_p1_recover["is_fallen"] is True
        assert result_p1_recover["cooldown_active"] is True
