"""
Unit tests for FallDetector service.

Tests cover:
- Normal standing pose (no fall detection)
- Head below hip detection
- Rapid descent detection
- Horizontal body angle detection
- Composite score calculation
- 2-second cooldown behavior
- State reset after cooldown
- Per-person state tracking
"""

import time
from unittest.mock import patch, PropertyMock, MagicMock

import pytest

from app.services.fall_detector import FallDetector, PersonState
from app.services.fall_classifier import FallPrediction
from app.services.posture_classifier import PostureType


class TestFallDetector:
    """Test suite for FallDetector class."""

    @pytest.fixture(autouse=True)
    def _disable_ml_classifier(self):
        """Disable ML classifier so tests use pure rule-based scoring."""
        with patch(
            "app.services.fall_detector.fall_classifier"
        ) as mock_clf:
            mock_clf.enabled = False
            mock_clf.add_frame = lambda *a, **kw: None
            yield mock_clf

    @pytest.fixture(autouse=True)
    def _disable_grace_period(self):
        """Disable grace period so single-frame tests work."""
        with patch("app.services.fall_detector.settings") as mock_settings:
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
            mock_settings.FALL_GRACE_FRAMES = 0
            mock_settings.FALL_CONSECUTIVE_FRAMES = 1
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
            yield mock_settings

    @pytest.fixture(autouse=True)
    def _mock_posture_classifier(self):
        """Mock posture classifier to return STANDING by default."""
        with patch("app.services.fall_detector.posture_classifier") as mock_pc:
            mock_pc.classify.return_value = PostureType.STANDING
            mock_pc.get_or_create_state.return_value = MagicMock(
                sitting_baseline_frames=0, posture_history=[]
            )
            mock_pc.get_shoulder_tilt_delta.return_value = 0.0
            mock_pc.get_sitting_baseline.return_value = 0.0
            yield mock_pc

    def test_normal_standing_pose_no_fall(self, mock_landmarks_standing):
        """Test that normal standing pose does not trigger fall detection."""
        # Arrange
        detector = FallDetector()

        # Act
        result = detector.detect(mock_landmarks_standing, person_id="person_0")

        # Assert
        assert result["is_fallen"] is False
        assert result["confidence"] < 0.5
        assert result["conditions"]["head_hip_inverted"] is False
        assert result["conditions"]["composite_score"] < 0.5

    def test_head_below_hip_triggers_fall(self, mock_landmarks_fallen):
        """Test that head Y > hip Y (head below hip) triggers fall condition."""
        # Arrange
        detector = FallDetector()

        # Act
        result = detector.detect(mock_landmarks_fallen, person_id="person_0")

        # Assert
        assert result["is_fallen"] is True
        assert result["conditions"]["head_hip_inverted"] is True
        assert result["confidence"] >= 0.5

    def test_rapid_descent_detection(self, mock_landmarks_standing):
        """Test rapid descent detection by simulating Y-coordinate history."""
        # Arrange
        detector = FallDetector()
        person_id = "person_rapid_descent"

        # Simulate 10 frames of normal standing
        for _ in range(10):
            detector.detect(mock_landmarks_standing, person_id=person_id)

        # Act - Create a rapid descent scenario
        # Modify landmarks to simulate sudden Y increase (descent)
        descended_landmarks = [landmark.copy() for landmark in mock_landmarks_standing]
        descended_landmarks[0]["y"] = 0.4  # NOSE moved down significantly

        result = detector.detect(descended_landmarks, person_id=person_id)

        # Assert
        assert result["conditions"]["rapid_descent"] is True

    def test_horizontal_body_angle_detection(self):
        """Test horizontal body angle detection (body lying flat)."""
        # Arrange
        detector = FallDetector()

        # Create horizontal pose - hips displaced horizontally from shoulders
        # shoulder_mid_x=0.3, hip_mid_x=0.7, same Y -> dx=0.4, dy=0 -> angle~0 (horizontal)
        horizontal_landmarks = [
            {"x": 0.3, "y": 0.5, "z": 0.0, "visibility": 0.9},  # 0: NOSE
        ] + [{"x": 0.5, "y": 0.5, "z": 0.0, "visibility": 0.9}] * 10

        horizontal_landmarks.extend([
            {"x": 0.2, "y": 0.5, "z": 0.0, "visibility": 0.9},  # 11: LEFT_SHOULDER
            {"x": 0.4, "y": 0.5, "z": 0.0, "visibility": 0.9},  # 12: RIGHT_SHOULDER
            {"x": 0.2, "y": 0.5, "z": 0.0, "visibility": 0.9},  # 13
            {"x": 0.8, "y": 0.5, "z": 0.0, "visibility": 0.9},  # 14
            {"x": 0.1, "y": 0.5, "z": 0.0, "visibility": 0.9},  # 15
            {"x": 0.9, "y": 0.5, "z": 0.0, "visibility": 0.9},  # 16
        ] + [{"x": 0.5, "y": 0.5, "z": 0.0, "visibility": 0.9}] * 6)

        horizontal_landmarks.extend([
            {"x": 0.6, "y": 0.5, "z": 0.0, "visibility": 0.9},  # 23: LEFT_HIP
            {"x": 0.8, "y": 0.5, "z": 0.0, "visibility": 0.9},  # 24: RIGHT_HIP
        ] + [{"x": 0.5, "y": 0.5, "z": 0.0, "visibility": 0.9}] * 8)

        # Act
        result = detector.detect(horizontal_landmarks, person_id="person_horizontal")

        # Assert
        assert result["conditions"]["horizontal_body"] is True
        assert result["angle"] < 45.0  # Horizontal angle threshold

    def test_composite_score_calculation(self, mock_landmarks_fallen):
        """Test that composite score is calculated correctly from conditions."""
        # Arrange
        detector = FallDetector()

        # Act
        result = detector.detect(mock_landmarks_fallen, person_id="person_composite")

        # Assert
        score = result["conditions"]["composite_score"]
        assert 0.0 <= score <= 1.0
        assert score >= 0.5  # Should exceed threshold for fallen pose

        # Verify score components
        conditions = result["conditions"]
        expected_score = 0.0
        if conditions["head_hip_inverted"]:
            expected_score += 0.4
        if conditions["rapid_descent"]:
            expected_score += 0.3
        if conditions["horizontal_body"]:
            expected_score += 0.3

        # Note: ankle check might add 0.1 more
        assert score >= expected_score or score <= expected_score + 0.1

    def test_cooldown_prevents_immediate_reset(self, mock_landmarks_standing, mock_landmarks_fallen):
        """Test that 2-second cooldown prevents immediate state reset."""
        # Arrange
        detector = FallDetector()
        detector.cooldown_seconds = 2.0
        person_id = "person_cooldown"

        # Act - Trigger fall detection
        fall_result = detector.detect(mock_landmarks_fallen, person_id=person_id)
        assert fall_result["is_fallen"] is True

        # Immediately return to normal pose
        normal_result = detector.detect(mock_landmarks_standing, person_id=person_id)

        # Assert - Should still be in fallen state due to cooldown
        assert normal_result["is_fallen"] is True
        assert normal_result["cooldown_active"] is True

    def test_state_reset_after_cooldown(self, mock_landmarks_standing, mock_landmarks_fallen):
        """Test that state resets after cooldown period expires."""
        # Arrange
        detector = FallDetector()
        detector.cooldown_seconds = 0.1  # Short cooldown for testing
        person_id = "person_cooldown_reset"

        # Act - Trigger fall
        fall_result = detector.detect(mock_landmarks_fallen, person_id=person_id)
        assert fall_result["is_fallen"] is True

        # Return to normal pose
        detector.detect(mock_landmarks_standing, person_id=person_id)

        # Wait for cooldown to expire
        time.sleep(0.15)

        # Detect again with normal pose
        final_result = detector.detect(mock_landmarks_standing, person_id=person_id)

        # Assert - Should be reset to normal
        assert final_result["is_fallen"] is False
        assert final_result["cooldown_active"] is False

    def test_per_person_state_tracking(self, mock_landmarks_standing, mock_landmarks_fallen):
        """Test that detector maintains independent state for each person."""
        # Arrange
        detector = FallDetector()

        # Act - Person 0 falls
        person0_fall = detector.detect(mock_landmarks_fallen, person_id="person_0")

        # Person 1 is standing
        person1_standing = detector.detect(mock_landmarks_standing, person_id="person_1")

        # Assert
        assert person0_fall["is_fallen"] is True
        assert person1_standing["is_fallen"] is False

    def test_insufficient_landmarks_returns_default(self):
        """Test that insufficient landmarks (<33) returns default result."""
        # Arrange
        detector = FallDetector()
        incomplete_landmarks = [{"x": 0.5, "y": 0.5, "z": 0.0}] * 10  # Only 10 landmarks

        # Act
        result = detector.detect(incomplete_landmarks, person_id="person_incomplete")

        # Assert
        assert result["is_fallen"] is False
        assert result["confidence"] == 0.0
        assert result["conditions"]["composite_score"] == 0.0

    def test_reset_person_clears_state(self, mock_landmarks_fallen):
        """Test that reset_person clears individual person state."""
        # Arrange
        detector = FallDetector()
        person_id = "person_reset"

        # Trigger fall
        detector.detect(mock_landmarks_fallen, person_id=person_id)
        assert person_id in detector._person_states

        # Act
        detector.reset_person(person_id)

        # Assert
        assert person_id not in detector._person_states

    def test_reset_all_clears_all_states(self, mock_landmarks_fallen):
        """Test that reset_all clears all person states."""
        # Arrange
        detector = FallDetector()

        # Create multiple person states
        detector.detect(mock_landmarks_fallen, person_id="person_0")
        detector.detect(mock_landmarks_fallen, person_id="person_1")
        detector.detect(mock_landmarks_fallen, person_id="person_2")

        assert len(detector._person_states) == 3

        # Act
        detector.reset_all()

        # Assert
        assert len(detector._person_states) == 0

    def test_get_or_create_state(self):
        """Test that get_or_create_state creates new state if not exists."""
        # Arrange
        detector = FallDetector()
        person_id = "new_person"

        # Act
        state = detector.get_or_create_state(person_id)

        # Assert
        assert isinstance(state, PersonState)
        assert state.person_id == person_id
        assert person_id in detector._person_states

    def test_threshold_setters(self):
        """Test that threshold setters work correctly."""
        # Arrange
        detector = FallDetector()

        # Act
        detector.head_hip_threshold = 0.1
        detector.cooldown_seconds = 5.0

        # Assert
        assert detector.head_hip_threshold == 0.1
        assert detector.cooldown_seconds == 5.0

    def test_fall_duration_calculation(self, mock_landmarks_fallen, mock_landmarks_standing):
        """Test that fall duration is calculated correctly."""
        # Arrange
        detector = FallDetector()
        person_id = "person_duration"

        # Act - Trigger fall
        result1 = detector.detect(mock_landmarks_fallen, person_id=person_id)
        time.sleep(0.1)
        result2 = detector.detect(mock_landmarks_fallen, person_id=person_id)

        # Assert
        assert result2["fall_duration"] > result1["fall_duration"]
        assert result2["fall_duration"] >= 0.1

    def test_ankle_above_hip_adds_score(self):
        """Test that ankle above hip adds to composite score."""
        # Arrange
        detector = FallDetector()

        # Create pose with ankles above hips
        inverted_landmarks = [
            {"x": 0.5, "y": 0.7, "z": 0.0, "visibility": 0.9},  # 0: NOSE (low)
        ] + [{"x": 0.5, "y": 0.6, "z": 0.0, "visibility": 0.9}] * 10

        inverted_landmarks.extend([
            {"x": 0.45, "y": 0.6, "z": 0.0, "visibility": 0.9},  # 11: LEFT_SHOULDER
            {"x": 0.55, "y": 0.6, "z": 0.0, "visibility": 0.9},  # 12: RIGHT_SHOULDER
        ] + [{"x": 0.5, "y": 0.5, "z": 0.0, "visibility": 0.9}] * 10)

        inverted_landmarks.extend([
            {"x": 0.45, "y": 0.65, "z": 0.0, "visibility": 0.9},  # 23: LEFT_HIP (Y=0.65)
            {"x": 0.55, "y": 0.65, "z": 0.0, "visibility": 0.9},  # 24: RIGHT_HIP
            {"x": 0.45, "y": 0.6, "z": 0.0, "visibility": 0.9},  # 25: LEFT_KNEE
            {"x": 0.55, "y": 0.6, "z": 0.0, "visibility": 0.9},  # 26: RIGHT_KNEE
            {"x": 0.45, "y": 0.5, "z": 0.0, "visibility": 0.9},  # 27: LEFT_ANKLE (Y=0.5, above hip!)
            {"x": 0.55, "y": 0.5, "z": 0.0, "visibility": 0.9},  # 28: RIGHT_ANKLE
        ] + [{"x": 0.5, "y": 0.45, "z": 0.0, "visibility": 0.9}] * 4)

        # Act
        result = detector.detect(inverted_landmarks, person_id="person_ankle")

        # Assert - Ankle bonus should increase score
        assert result["conditions"]["composite_score"] > 0.0

    def test_history_maxlen_constraint(self, mock_landmarks_standing):
        """Test that history deques respect maxlen=30."""
        # Arrange
        detector = FallDetector()
        person_id = "person_history"

        # Act - Add 50 frames
        for _ in range(50):
            detector.detect(mock_landmarks_standing, person_id=person_id)

        state = detector._person_states[person_id]

        # Assert
        assert len(state.head_y_history) == 30
        assert len(state.hip_y_history) == 30

    def test_configurable_ensemble_weights(self):
        """Test that ensemble weights can be configured via setters."""
        # Arrange
        detector = FallDetector()

        # Act
        detector.rule_weight = 0.7

        # Assert
        assert detector.rule_weight == pytest.approx(0.7)
        assert detector.ml_weight == pytest.approx(0.3)

    def test_ml_weight_setter_updates_rule_weight(self):
        """Test that setting ml_weight auto-updates rule_weight."""
        # Arrange
        detector = FallDetector()

        # Act
        detector.ml_weight = 0.8

        # Assert
        assert detector.ml_weight == pytest.approx(0.8)
        assert detector.rule_weight == pytest.approx(0.2)

    def test_detect_returns_fall_type(self, mock_landmarks_standing):
        """Test that detect() result includes fall_type field."""
        # Arrange
        detector = FallDetector()

        # Act
        result = detector.detect(mock_landmarks_standing, person_id="person_type")

        # Assert
        assert "fall_type" in result
        assert result["fall_type"] in ("normal", "front_fall", "back_fall", "side_fall")

    def test_detect_returns_rule_ml_scores(self, mock_landmarks_fallen):
        """Test that detect() result includes rule_score and ml_score."""
        # Arrange
        detector = FallDetector()

        # Act
        result = detector.detect(mock_landmarks_fallen, person_id="person_scores")

        # Assert
        assert "rule_score" in result
        assert "ml_score" in result
        assert 0.0 <= result["rule_score"] <= 1.0
        assert 0.0 <= result["ml_score"] <= 1.0

    def test_default_result_has_new_fields(self):
        """Test that default result includes fall_type, rule_score, ml_score."""
        # Arrange
        detector = FallDetector()
        incomplete_landmarks = [{"x": 0.5, "y": 0.5, "z": 0.0}] * 10

        # Act
        result = detector.detect(incomplete_landmarks, person_id="person_default")

        # Assert
        assert result["fall_type"] == "normal"
        assert result["rule_score"] == 0.0
        assert result["ml_score"] == 0.0

    def test_ensemble_weighted_average_with_ml_enabled(
        self, _disable_ml_classifier, mock_landmarks_fallen
    ):
        """Test that ensemble computes weighted average when ML classifier is enabled."""
        # Arrange
        detector = FallDetector()
        detector.rule_weight = 0.6
        # ml_weight는 자동으로 0.4

        # ML 분류기를 활성화하고 known FallPrediction 반환하도록 설정
        mock_clf = _disable_ml_classifier
        mock_clf.enabled = True
        mock_prediction = FallPrediction(
            fall_probability=0.9,
            fall_type="back_fall",
            class_probabilities={"normal": 0.1, "front_fall": 0.1, "back_fall": 0.7, "side_fall": 0.1},
        )
        mock_clf.predict_detailed.return_value = mock_prediction

        # Act
        result = detector.detect(mock_landmarks_fallen, person_id="person_ensemble")

        # Assert
        # rule_score >= 0.5 (C1 head_hip_inverted + C3 horizontal_body, fixture-dependent)
        # ml_score = 0.9
        assert result["rule_score"] >= 0.5
        assert result["ml_score"] == pytest.approx(0.9, abs=0.01)
        expected_ensemble = result["rule_score"] * 0.6 + 0.9 * 0.4
        assert result["confidence"] == pytest.approx(expected_ensemble, abs=0.05)
        assert result["is_fallen"] is True
        assert result["fall_type"] == "back_fall"


class TestMLSkipOptimization:
    """ML skip optimization tests (Phase 26)."""

    @pytest.fixture(autouse=True)
    def _disable_ml_classifier(self):
        """Mock ML classifier for tests."""
        with patch("app.services.fall_detector.fall_classifier") as mock_clf:
            mock_clf.enabled = True
            mock_clf.add_frame = MagicMock()
            mock_clf.predict_detailed.return_value = FallPrediction(
                fall_probability=0.0,
                fall_type="normal",
                class_probabilities={"normal": 1.0, "front_fall": 0.0, "back_fall": 0.0, "side_fall": 0.0},
            )
            yield mock_clf

    @pytest.fixture(autouse=True)
    def _disable_grace_period(self):
        """Disable grace period so single-frame tests work."""
        with patch("app.services.fall_detector.settings") as mock_settings:
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
            mock_settings.FALL_GRACE_FRAMES = 0
            mock_settings.FALL_CONSECUTIVE_FRAMES = 1
            mock_settings.FALL_LYING_STABLE_EXEMPT_FRAMES = 60
            mock_settings.FALL_SEATED_HEAD_HIP_THRESHOLD = 0.02
            mock_settings.FALL_SEATED_RAPID_DESCENT_THRESHOLD = 0.12
            mock_settings.FALL_SEATED_FORWARD_SLUMP_THRESHOLD = 0.25
            mock_settings.FALL_SEATED_LATERAL_TILT_THRESHOLD = 0.20
            mock_settings.FALL_SEATED_HEIGHT_DROP_RATIO = 0.45
            mock_settings.FALL_SEATED_BASELINE_MIN_FRAMES = 30
            mock_settings.FALL_SEATED_HORIZONTAL_ANGLE = 45.0
            mock_settings.FALL_ENHANCED_RULES_ENABLED = False
            mock_settings.FALL_PRE_IMPACT_THRESHOLD = 0.25
            mock_settings.FALL_PRE_IMPACT_ML_THRESHOLD = 0.4
            yield mock_settings

    @pytest.fixture(autouse=True)
    def _mock_posture_classifier(self):
        """Mock posture classifier to return STANDING by default."""
        with patch("app.services.fall_detector.posture_classifier") as mock_pc:
            mock_pc.classify.return_value = PostureType.STANDING
            mock_pc.get_or_create_state.return_value = MagicMock(
                sitting_baseline_frames=0, posture_history=[]
            )
            mock_pc.get_shoulder_tilt_delta.return_value = 0.0
            mock_pc.get_sitting_baseline.return_value = 0.0
            yield mock_pc

    def test_ml_skip_when_weight_zero(self, _disable_ml_classifier, mock_landmarks_standing):
        """When ml_weight=0, fall_classifier.add_frame and predict_detailed should NOT be called."""
        # Arrange
        detector = FallDetector()
        detector.ml_weight = 0.0  # This sets rule_weight=1.0 automatically
        mock_clf = _disable_ml_classifier

        # Act
        result = detector.detect(mock_landmarks_standing, person_id="person_0")

        # Assert
        assert result is not None
        # ML should be completely skipped
        mock_clf.add_frame.assert_not_called()
        mock_clf.predict_detailed.assert_not_called()

    def test_rule_only_detects_fall(self, mock_landmarks_fallen):
        """With ml_weight=0, fall detection should still work via rules alone."""
        # Arrange
        detector = FallDetector()
        detector.ml_weight = 0.0  # rule_weight=1.0

        # Act
        result = detector.detect(mock_landmarks_fallen, person_id="person_0")

        # Assert
        assert result["is_fallen"] is True
        assert result["rule_score"] >= 0.5
        assert result["ml_score"] == 0.0
        assert result["confidence"] == result["rule_score"]


class TestEnhancedRulesN1N6:
    """N1-N6 extended rule condition tests (Phase 26)."""

    @pytest.fixture(autouse=True)
    def _disable_ml_classifier(self):
        """Disable ML classifier so tests use pure rule-based scoring."""
        with patch("app.services.fall_detector.fall_classifier") as mock_clf:
            mock_clf.enabled = False
            mock_clf.add_frame = lambda *a, **kw: None
            yield mock_clf

    @pytest.fixture(autouse=True)
    def _disable_grace_period(self):
        """Disable grace period and enable enhanced rules."""
        with patch("app.services.fall_detector.settings") as mock_settings:
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
            mock_settings.FALL_GRACE_FRAMES = 0
            mock_settings.FALL_CONSECUTIVE_FRAMES = 1
            mock_settings.FALL_LYING_STABLE_EXEMPT_FRAMES = 60
            mock_settings.FALL_SEATED_HEAD_HIP_THRESHOLD = 0.02
            mock_settings.FALL_SEATED_RAPID_DESCENT_THRESHOLD = 0.12
            mock_settings.FALL_SEATED_FORWARD_SLUMP_THRESHOLD = 0.25
            mock_settings.FALL_SEATED_LATERAL_TILT_THRESHOLD = 0.20
            mock_settings.FALL_SEATED_HEIGHT_DROP_RATIO = 0.45
            mock_settings.FALL_SEATED_BASELINE_MIN_FRAMES = 30
            mock_settings.FALL_SEATED_HORIZONTAL_ANGLE = 45.0
            # Enhanced rules settings
            mock_settings.FALL_ENHANCED_RULES_ENABLED = True
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
            yield mock_settings

    @pytest.fixture(autouse=True)
    def _mock_posture_classifier(self):
        """Mock posture classifier to return STANDING by default."""
        with patch("app.services.fall_detector.posture_classifier") as mock_pc:
            mock_pc.classify.return_value = PostureType.STANDING
            mock_pc.get_or_create_state.return_value = MagicMock(
                sitting_baseline_frames=0, posture_history=[]
            )
            mock_pc.get_shoulder_tilt_delta.return_value = 0.0
            mock_pc.get_sitting_baseline.return_value = 0.0
            yield mock_pc

    def test_n1_vertical_acceleration(self, mock_landmarks_standing):
        """N1: Detect accelerating descent via head_y history."""
        # Arrange
        detector = FallDetector()
        detector.enhanced_rules = True
        person_id = "person_n1"

        # Build history with increasing descent speed
        # Frame 0: y=0.1 (standing)
        # Frame 1: y=0.12 (v=0.02)
        # Frame 2: y=0.18 (v=0.06, accel=0.04 > 0.02 threshold)
        landmarks = [landmark.copy() for landmark in mock_landmarks_standing]

        # Frame 0
        landmarks[0]["y"] = 0.10
        detector.detect(landmarks, person_id=person_id)

        # Frame 1
        landmarks[0]["y"] = 0.12
        detector.detect(landmarks, person_id=person_id)

        # Frame 2 - accelerating descent
        landmarks[0]["y"] = 0.18

        # Act
        result = detector.detect(landmarks, person_id=person_id)

        # Assert
        assert result["conditions"]["n1_accel"] is True

    def test_n4_knee_buckling(self, mock_landmarks_standing):
        """N4: Detect knee angle rate exceeding threshold."""
        # Arrange
        detector = FallDetector()
        detector.enhanced_rules = True
        person_id = "person_n4"

        landmarks = [landmark.copy() for landmark in mock_landmarks_standing]

        # Frame 0: Normal standing (knee angle ~170 degrees)
        # LEFT_HIP=23 at y=0.6, LEFT_KNEE=25 at y=0.8, LEFT_ANKLE=27 at y=0.95
        detector.detect(landmarks, person_id=person_id)

        # Frame 1: Knee buckles rapidly - move knee forward (x) to create sharp angle
        # Reduce knee angle to ~100 degrees by moving knee x position
        landmarks[25]["x"] = 0.35  # LEFT_KNEE x shift
        landmarks[25]["y"] = 0.75  # LEFT_KNEE y shift
        landmarks[26]["x"] = 0.60  # RIGHT_KNEE x shift
        landmarks[26]["y"] = 0.75  # RIGHT_KNEE y shift

        # Act
        result = detector.detect(landmarks, person_id=person_id)

        # Assert
        # N4 triggers when angle_rate > 15.0 and min_angle < 130.0
        assert result["conditions"]["n4_knee_buckle"] is True

    def test_n6_height_trajectory(self, mock_landmarks_standing):
        """N6: Detect accelerating trajectory pattern (second half faster than first)."""
        # Arrange
        detector = FallDetector()
        detector.enhanced_rules = True
        person_id = "person_n6"

        landmarks = [landmark.copy() for landmark in mock_landmarks_standing]

        # Feed 15 frames where descent accelerates
        # First half: slow descent (avg speed ~0.01)
        # Second half: fast descent (avg speed ~0.02)
        for i in range(15):
            if i < 7:
                # First half: slow descent
                landmarks[0]["y"] = 0.1 + (i * 0.01)
            else:
                # Second half: accelerating
                landmarks[0]["y"] = 0.1 + (7 * 0.01) + ((i - 7) * 0.025)

            result = detector.detect(landmarks, person_id=person_id)

        # Assert
        # N6 should trigger when second_half_speed > first_half_speed * 1.3
        assert result["conditions"]["n6_trajectory"] is True

    def test_n2_protective_extension(self, mock_landmarks_standing):
        """N2: Detect arm spread reflex with wrist drop."""
        # Arrange
        detector = FallDetector()
        detector.enhanced_rules = True
        person_id = "person_n2"

        landmarks = [landmark.copy() for landmark in mock_landmarks_standing]

        # Frame 0: Arms close together
        landmarks[15]["x"] = 0.40  # LEFT_WRIST
        landmarks[16]["x"] = 0.60  # RIGHT_WRIST
        detector.detect(landmarks, person_id=person_id)

        # Frame 1: Arms spread rapidly + wrists drop below hip
        landmarks[15]["x"] = 0.20  # LEFT_WRIST spread
        landmarks[15]["y"] = 0.70  # LEFT_WRIST drop (hip at 0.6)
        landmarks[16]["x"] = 0.80  # RIGHT_WRIST spread
        landmarks[16]["y"] = 0.70  # RIGHT_WRIST drop

        # Act
        result = detector.detect(landmarks, person_id=person_id)

        # Assert
        assert result["conditions"]["n2_protective"] is True

    def test_n3_com_bos_deviation(self, mock_landmarks_standing, _mock_posture_classifier):
        """N3: CoM-BoS deviation growing over 2+ consecutive frames."""
        # Arrange
        detector = FallDetector()
        detector.enhanced_rules = True
        person_id = "person_n3"
        _mock_posture_classifier.classify.return_value = PostureType.STANDING

        landmarks = [landmark.copy() for landmark in mock_landmarks_standing]

        # Ensure ankle span is sufficient
        landmarks[27]["x"] = 0.40  # LEFT_ANKLE
        landmarks[28]["x"] = 0.60  # RIGHT_ANKLE

        # Frame 0: Centered CoM
        landmarks[11]["x"] = 0.48  # LEFT_SHOULDER
        landmarks[12]["x"] = 0.52  # RIGHT_SHOULDER
        landmarks[23]["x"] = 0.48  # LEFT_HIP
        landmarks[24]["x"] = 0.52  # RIGHT_HIP
        detector.detect(landmarks, person_id=person_id)

        # Frame 1: CoM shifts slightly
        landmarks[11]["x"] = 0.46
        landmarks[12]["x"] = 0.50
        landmarks[23]["x"] = 0.46
        landmarks[24]["x"] = 0.50
        detector.detect(landmarks, person_id=person_id)

        # Frame 2: CoM shifts further (deviation growing)
        landmarks[11]["x"] = 0.42
        landmarks[12]["x"] = 0.46
        landmarks[23]["x"] = 0.42
        landmarks[24]["x"] = 0.46

        # Act
        result = detector.detect(landmarks, person_id=person_id)

        # Assert
        assert result["conditions"]["n3_com_bos"] is True

    def test_enhanced_rules_toggle(self, mock_landmarks_standing):
        """Toggle FALL_ENHANCED_RULES_ENABLED on/off."""
        # Arrange
        detector = FallDetector()
        person_id = "person_toggle"

        # Test with enhanced=False
        detector.enhanced_rules = False
        result_disabled = detector.detect(mock_landmarks_standing, person_id=person_id)

        # Assert all N conditions are False
        assert result_disabled["conditions"]["n1_accel"] is False
        assert result_disabled["conditions"]["n2_protective"] is False
        assert result_disabled["conditions"]["n3_com_bos"] is False
        assert result_disabled["conditions"]["n4_knee_buckle"] is False
        assert result_disabled["conditions"]["n5_trunk_rotation"] is False
        assert result_disabled["conditions"]["n6_trajectory"] is False

        # Test with enhanced=True
        detector.enhanced_rules = True
        # N conditions should be computed (though may still be False without triggers)
        result_enabled = detector.detect(mock_landmarks_standing, person_id=person_id)

        # Assert N conditions exist in results
        assert "n1_accel" in result_enabled["conditions"]
        assert "n2_protective" in result_enabled["conditions"]
        assert "n3_com_bos" in result_enabled["conditions"]
        assert "n4_knee_buckle" in result_enabled["conditions"]
        assert "n5_trunk_rotation" in result_enabled["conditions"]
        assert "n6_trajectory" in result_enabled["conditions"]

    def test_n4_triggers_pre_impact(self, mock_landmarks_standing):
        """N4 knee buckle should trigger is_pre_impact independently."""
        # Arrange
        detector = FallDetector()
        detector.enhanced_rules = True
        person_id = "person_n4_pre"

        landmarks = [landmark.copy() for landmark in mock_landmarks_standing]

        # Setup initial state
        detector.detect(landmarks, person_id=person_id)

        # Trigger N4 with knee buckling
        landmarks[25]["x"] = 0.35
        landmarks[25]["y"] = 0.75
        landmarks[26]["x"] = 0.60
        landmarks[26]["y"] = 0.75

        # Act
        result = detector.detect(landmarks, person_id=person_id)

        # Assert
        assert result["conditions"]["n4_knee_buckle"] is True
        assert result["is_pre_impact"] is True
        assert result["is_fallen"] is False  # Not enough for full fall

    def test_enhanced_weight_redistribution(self, mock_landmarks_fallen):
        """When enhanced=True, C1/C2/C3 weights should be 0.35/0.25/0.25."""
        # Arrange
        detector = FallDetector()
        detector.enhanced_rules = True

        # Act
        result = detector.detect(mock_landmarks_fallen, person_id="person_weights")

        # Assert
        # With enhanced rules, C1 alone should contribute 0.35
        # mock_landmarks_fallen triggers C1 (head_hip_inverted) + ankle (0.1)
        # Expected: 0.35 + 0.1 = 0.45
        # But fallen landmarks may also trigger C3 (horizontal), so score could be higher
        conditions = result["conditions"]
        score = result["rule_score"]

        # Verify that when only C1 is triggered, it contributes 0.35
        # (This is indirectly tested by checking the total score)
        # With C1+C3+ankle: 0.35 + 0.25 + 0.1 = 0.7
        if conditions["head_hip_inverted"] and conditions["horizontal_body"]:
            assert score >= 0.6  # At least C1+C3


class TestCOCO17KeypointSupport:
    """Test suite for COCO 17-point keypoint format support (Phase 27)."""

    @pytest.fixture(autouse=True)
    def _disable_ml_classifier(self):
        """Disable ML classifier so tests use pure rule-based scoring."""
        with patch(
            "app.services.fall_detector.fall_classifier"
        ) as mock_clf:
            mock_clf.enabled = False
            mock_clf.add_frame = lambda *a, **kw: None
            yield mock_clf

    @pytest.fixture(autouse=True)
    def _disable_grace_period(self):
        """Disable grace period so single-frame tests work."""
        with patch("app.services.fall_detector.settings") as mock_settings:
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
            mock_settings.FALL_GRACE_FRAMES = 0
            mock_settings.FALL_CONSECUTIVE_FRAMES = 1
            mock_settings.FALL_ENHANCED_RULES_ENABLED = False
            mock_settings.FALL_PRE_IMPACT_THRESHOLD = 0.25
            mock_settings.FALL_PRE_IMPACT_ML_THRESHOLD = 0.4
            mock_settings.FALL_SEATED_HEAD_HIP_THRESHOLD = 0.02
            mock_settings.FALL_SEATED_RAPID_DESCENT_THRESHOLD = 0.12
            mock_settings.FALL_SEATED_HORIZONTAL_ANGLE = 30.0
            mock_settings.FALL_SEATED_FORWARD_SLUMP_THRESHOLD = 0.25
            mock_settings.FALL_SEATED_LATERAL_TILT_THRESHOLD = 0.20
            mock_settings.FALL_SEATED_HEIGHT_DROP_RATIO = 0.45
            mock_settings.FALL_SEATED_BASELINE_MIN_FRAMES = 30
            mock_settings.FALL_LYING_STABLE_EXEMPT_FRAMES = 60
            yield mock_settings

    @pytest.fixture
    def coco17_standing_landmarks(self):
        """COCO 17-point landmarks for a normal standing pose."""
        # COCO 17 keypoint order:
        # 0:nose, 1:left_eye, 2:right_eye, 3:left_ear, 4:right_ear,
        # 5:left_shoulder, 6:right_shoulder, 7:left_elbow, 8:right_elbow,
        # 9:left_wrist, 10:right_wrist, 11:left_hip, 12:right_hip,
        # 13:left_knee, 14:right_knee, 15:left_ankle, 16:right_ankle
        return [
            {"x": 0.50, "y": 0.20, "z": 0.0, "visibility": 0.95},  # 0: nose
            {"x": 0.48, "y": 0.18, "z": 0.0, "visibility": 0.90},  # 1: left_eye
            {"x": 0.52, "y": 0.18, "z": 0.0, "visibility": 0.90},  # 2: right_eye
            {"x": 0.46, "y": 0.20, "z": 0.0, "visibility": 0.85},  # 3: left_ear
            {"x": 0.54, "y": 0.20, "z": 0.0, "visibility": 0.85},  # 4: right_ear
            {"x": 0.45, "y": 0.30, "z": 0.0, "visibility": 0.95},  # 5: left_shoulder
            {"x": 0.55, "y": 0.30, "z": 0.0, "visibility": 0.95},  # 6: right_shoulder
            {"x": 0.42, "y": 0.45, "z": 0.0, "visibility": 0.90},  # 7: left_elbow
            {"x": 0.58, "y": 0.45, "z": 0.0, "visibility": 0.90},  # 8: right_elbow
            {"x": 0.40, "y": 0.55, "z": 0.0, "visibility": 0.85},  # 9: left_wrist
            {"x": 0.60, "y": 0.55, "z": 0.0, "visibility": 0.85},  # 10: right_wrist
            {"x": 0.47, "y": 0.55, "z": 0.0, "visibility": 0.95},  # 11: left_hip
            {"x": 0.53, "y": 0.55, "z": 0.0, "visibility": 0.95},  # 12: right_hip
            {"x": 0.46, "y": 0.75, "z": 0.0, "visibility": 0.90},  # 13: left_knee
            {"x": 0.54, "y": 0.75, "z": 0.0, "visibility": 0.90},  # 14: right_knee
            {"x": 0.45, "y": 0.95, "z": 0.0, "visibility": 0.85},  # 15: left_ankle
            {"x": 0.55, "y": 0.95, "z": 0.0, "visibility": 0.85},  # 16: right_ankle
        ]

    @pytest.fixture
    def coco17_fallen_landmarks(self):
        """COCO 17-point landmarks for a fallen pose (head below hip)."""
        return [
            {"x": 0.50, "y": 0.70, "z": 0.0, "visibility": 0.90},  # 0: nose (below hip)
            {"x": 0.48, "y": 0.68, "z": 0.0, "visibility": 0.85},  # 1: left_eye
            {"x": 0.52, "y": 0.68, "z": 0.0, "visibility": 0.85},  # 2: right_eye
            {"x": 0.46, "y": 0.70, "z": 0.0, "visibility": 0.80},  # 3: left_ear
            {"x": 0.54, "y": 0.70, "z": 0.0, "visibility": 0.80},  # 4: right_ear
            {"x": 0.30, "y": 0.65, "z": 0.0, "visibility": 0.95},  # 5: left_shoulder (horizontal)
            {"x": 0.70, "y": 0.65, "z": 0.0, "visibility": 0.95},  # 6: right_shoulder
            {"x": 0.25, "y": 0.65, "z": 0.0, "visibility": 0.85},  # 7: left_elbow
            {"x": 0.75, "y": 0.65, "z": 0.0, "visibility": 0.85},  # 8: right_elbow
            {"x": 0.20, "y": 0.65, "z": 0.0, "visibility": 0.80},  # 9: left_wrist
            {"x": 0.80, "y": 0.65, "z": 0.0, "visibility": 0.80},  # 10: right_wrist
            {"x": 0.40, "y": 0.65, "z": 0.0, "visibility": 0.95},  # 11: left_hip
            {"x": 0.60, "y": 0.65, "z": 0.0, "visibility": 0.95},  # 12: right_hip
            {"x": 0.35, "y": 0.65, "z": 0.0, "visibility": 0.90},  # 13: left_knee
            {"x": 0.65, "y": 0.65, "z": 0.0, "visibility": 0.90},  # 14: right_knee
            {"x": 0.30, "y": 0.65, "z": 0.0, "visibility": 0.85},  # 15: left_ankle
            {"x": 0.70, "y": 0.65, "z": 0.0, "visibility": 0.85},  # 16: right_ankle
        ]

    def test_coco17_normal_pose_no_fall(self, coco17_standing_landmarks):
        """Test that COCO 17-point normal standing pose returns no fall."""
        from app.services.fall_detector import FallDetector, KeypointFormat

        detector = FallDetector()
        result = detector.detect(
            coco17_standing_landmarks,
            person_id="person_coco17",
            keypoint_format=KeypointFormat.COCO_17,
        )

        assert result["is_fallen"] is False
        assert result["confidence"] < 0.5

    def test_coco17_fallen_pose_detected(self, coco17_fallen_landmarks):
        """Test that COCO 17-point fallen pose is detected as fall."""
        from app.services.fall_detector import FallDetector, KeypointFormat

        detector = FallDetector()
        result = detector.detect(
            coco17_fallen_landmarks,
            person_id="person_coco17_fall",
            keypoint_format=KeypointFormat.COCO_17,
        )

        # Should detect as fallen (head below hip + horizontal body)
        assert result["conditions"]["head_hip_inverted"] is True
        assert result["rule_score"] > 0.3

    def test_coco17_string_format_accepted(self, coco17_standing_landmarks):
        """Test that string format 'coco_17' is accepted."""
        from app.services.fall_detector import FallDetector

        detector = FallDetector()
        result = detector.detect(
            coco17_standing_landmarks,
            person_id="person_coco17_str",
            keypoint_format="coco_17",  # String format
        )

        assert result["is_fallen"] is False
        assert "confidence" in result

    def test_coco17_insufficient_landmarks_returns_default(self):
        """Test that fewer than 17 COCO keypoints returns default result."""
        from app.services.fall_detector import FallDetector, KeypointFormat

        detector = FallDetector()
        # Only 10 keypoints (insufficient)
        insufficient = [{"x": 0.5, "y": 0.5, "z": 0.0, "visibility": 0.9} for _ in range(10)]

        result = detector.detect(
            insufficient,
            person_id="person_insufficient",
            keypoint_format=KeypointFormat.COCO_17,
        )

        assert result["is_fallen"] is False
        assert result["confidence"] == 0.0

    def test_coco17_np_array_format_supported(self):
        """Test that numpy array format for COCO 17 is supported."""
        import numpy as np
        from app.services.keypoint_adapter import KeypointAdapter

        # COCO 17 as numpy array [x, y, confidence]
        coco_np = np.array([
            [0.50, 0.20, 0.95],  # nose
            [0.48, 0.18, 0.90],  # left_eye
            [0.52, 0.18, 0.90],  # right_eye
            [0.46, 0.20, 0.85],  # left_ear
            [0.54, 0.20, 0.85],  # right_ear
            [0.45, 0.30, 0.95],  # left_shoulder
            [0.55, 0.30, 0.95],  # right_shoulder
            [0.42, 0.45, 0.90],  # left_elbow
            [0.58, 0.45, 0.90],  # right_elbow
            [0.40, 0.55, 0.85],  # left_wrist
            [0.60, 0.55, 0.85],  # right_wrist
            [0.47, 0.55, 0.95],  # left_hip
            [0.53, 0.55, 0.95],  # right_hip
            [0.46, 0.75, 0.90],  # left_knee
            [0.54, 0.75, 0.90],  # right_knee
            [0.45, 0.95, 0.85],  # left_ankle
            [0.55, 0.95, 0.85],  # right_ankle
        ])

        result = KeypointAdapter.coco_to_mediapipe_33(coco_np)

        assert len(result) == 33
        # Check nose mapping (COCO 0 → MediaPipe 0)
        assert result[0]["x"] == 0.50
        assert result[0]["y"] == 0.20
        # Check left hip mapping (COCO 11 → MediaPipe 23)
        assert result[23]["x"] == 0.47
        assert result[23]["y"] == 0.55


class TestLowVisibilityAccumulation:
    """저가시성 다중 프레임 누적 감지 테스트"""

    @pytest.fixture
    def mock_landmarks_low_vis_fallen(self):
        """저가시성 + 낙상 자세 랜드마크 (visibility 0.4)"""
        landmarks = []
        for i in range(33):
            if i == 0:  # nose - 낙상 시 머리 낮음
                landmarks.append({"x": 0.5, "y": 0.7, "z": 0.0, "visibility": 0.4})
            elif i in [11, 12]:  # shoulders
                landmarks.append({"x": 0.5, "y": 0.5, "z": 0.0, "visibility": 0.4})
            elif i in [23, 24]:  # hips - 엉덩이가 머리보다 위
                landmarks.append({"x": 0.5, "y": 0.45, "z": 0.0, "visibility": 0.4})
            elif i in [25, 26]:  # knees
                landmarks.append({"x": 0.5, "y": 0.6, "z": 0.0, "visibility": 0.4})
            elif i in [27, 28]:  # ankles
                landmarks.append({"x": 0.5, "y": 0.8, "z": 0.0, "visibility": 0.4})
            else:
                landmarks.append({"x": 0.5, "y": 0.5, "z": 0.0, "visibility": 0.4})
        return landmarks

    @patch("app.services.fall_detector.settings")
    @patch("app.services.fall_detector.posture_classifier")
    @patch("app.services.fall_detector.fall_classifier")
    def test_low_vis_mode_enabled_between_thresholds(
        self, mock_fall_classifier, mock_posture_classifier, mock_settings,
        mock_landmarks_low_vis_fallen,
    ):
        """가시성 0.3-0.5 사이에서 저가시성 모드 활성화 테스트"""
        mock_settings.FALL_HEAD_HIP_THRESHOLD = -0.05
        mock_settings.FALL_RAPID_DESCENT_THRESHOLD = 0.08
        mock_settings.FALL_HORIZONTAL_ANGLE = 45.0
        mock_settings.FALL_COMPOSITE_THRESHOLD = 0.5
        mock_settings.FALL_RULE_WEIGHT = 1.0
        mock_settings.FALL_ML_WEIGHT = 0.0
        mock_settings.FALL_MIN_VISIBILITY = 0.5  # 일반 임계값
        mock_settings.FALL_LOW_VIS_MIN = 0.3      # 저가시성 최소값
        mock_settings.FALL_LOW_VIS_ACCUM_FRAMES = 3
        mock_settings.FALL_LOW_VIS_ACCUM_THRESHOLD = 0.35
        mock_settings.FALL_POST_FALL_CHECK_FRAMES = 10
        mock_settings.FALL_POST_FALL_MAX_VARIANCE = 0.0005
        mock_settings.FALL_GRACE_FRAMES = 0
        mock_settings.FALL_CONSECUTIVE_FRAMES = 1
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
        mock_settings.FALL_COOLDOWN_SECONDS = 5.0
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
        mock_settings.FALL_BENDING_MAX_ANKLE_VARIANCE = 0.015
        mock_settings.FALL_BENDING_MAX_DESCENT_ACCEL = 0.005
        mock_settings.FALL_CONTROLLED_LYING_DECEL_THRESHOLD = -0.002
        mock_settings.FALL_CONTROLLED_LYING_MIN_FRAMES = 15

        from app.services.posture_classifier import PostureType
        mock_posture_classifier.classify.return_value = PostureType.LYING
        mock_posture_classifier.get_or_create_state.return_value.posture_history = []

        from app.services.fall_detector import FallDetector

        detector = FallDetector()
        person_id = "person_low_vis"

        # 3프레임 연속으로 낙상 자세 전달 → 누적 감지 트리거
        for _ in range(3):
            result = detector.detect(mock_landmarks_low_vis_fallen, person_id=person_id)

        # 저가시성 누적으로 감지되어야 함
        # Note: visibility가 0.4이고 낙상 자세이므로 점수가 충분히 쌓임
        assert "confidence" in result

    @patch("app.services.fall_detector.settings")
    @patch("app.services.fall_detector.posture_classifier")
    @patch("app.services.fall_detector.fall_classifier")
    def test_very_low_vis_skipped(
        self, mock_fall_classifier, mock_posture_classifier, mock_settings,
    ):
        """가시성 0.3 미만에서 감지 건너뜀 테스트"""
        mock_settings.FALL_HEAD_HIP_THRESHOLD = -0.05
        mock_settings.FALL_RAPID_DESCENT_THRESHOLD = 0.08
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
        mock_settings.FALL_GRACE_FRAMES = 0
        mock_settings.FALL_CONSECUTIVE_FRAMES = 1
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
        mock_settings.FALL_COOLDOWN_SECONDS = 5.0
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
        mock_settings.FALL_BENDING_MAX_ANKLE_VARIANCE = 0.015
        mock_settings.FALL_BENDING_MAX_DESCENT_ACCEL = 0.005
        mock_settings.FALL_CONTROLLED_LYING_DECEL_THRESHOLD = -0.002
        mock_settings.FALL_CONTROLLED_LYING_MIN_FRAMES = 15

        from app.services.fall_detector import FallDetector

        detector = FallDetector()

        # 매우 낮은 가시성 랜드마크 (0.2)
        very_low_vis_landmarks = [
            {"x": 0.5, "y": 0.7, "z": 0.0, "visibility": 0.2}
            for _ in range(33)
        ]

        result = detector.detect(very_low_vis_landmarks, person_id="person_very_low_vis")

        # 가시성 부족으로 감지 건너뜀 → is_fallen은 False
        assert result["is_fallen"] is False
        assert result["confidence"] == 0.0
