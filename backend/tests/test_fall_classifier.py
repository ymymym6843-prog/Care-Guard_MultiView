"""
Unit tests for FallClassifier service.

Tests cover:
- Binary sigmoid model compatibility
- Binary softmax model compatibility
- 4-class fall_type extraction
- Buffer management
- Disabled classifier behavior
- predict_detailed() output structure
- predict() backward compatibility
"""

from collections import deque
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from app.services.fall_classifier import FallClassifier, FallPrediction, _CLASS_NAMES


# ── ONNX mock output fixtures ──

@pytest.fixture()
def mock_onnx_output_binary_sigmoid():
    """Binary sigmoid: single float output [0.85]."""
    return np.array([0.85], dtype=np.float32)


@pytest.fixture()
def mock_onnx_output_binary_softmax():
    """Binary softmax: [normal, fall] = [0.15, 0.85]."""
    return np.array([0.15, 0.85], dtype=np.float32)


@pytest.fixture()
def mock_onnx_output_4class():
    """4-class: [normal, front, back, side] = [0.1, 0.6, 0.2, 0.1]."""
    return np.array([0.1, 0.6, 0.2, 0.1], dtype=np.float32)


@pytest.fixture()
def mock_onnx_output_4class_back_fall():
    """4-class back fall dominant: [0.05, 0.1, 0.75, 0.1]."""
    return np.array([0.05, 0.1, 0.75, 0.1], dtype=np.float32)


@pytest.fixture()
def mock_onnx_output_4class_side_fall():
    """4-class side fall dominant: [0.1, 0.1, 0.1, 0.7]."""
    return np.array([0.1, 0.1, 0.1, 0.7], dtype=np.float32)


@pytest.fixture()
def mock_onnx_output_4class_normal():
    """4-class normal dominant: [0.85, 0.05, 0.05, 0.05]."""
    return np.array([0.85, 0.05, 0.05, 0.05], dtype=np.float32)


class TestFallClassifier:
    """Test suite for FallClassifier class."""

    def _make_classifier(self, enabled=False, output_dim=1):
        """Create a FallClassifier with controlled state."""
        clf = FallClassifier()
        clf._initialized = True
        clf._enabled = enabled
        clf._output_dim = output_dim
        return clf

    def _fill_buffer(self, clf, person_id="person_0"):
        """Fill a person's buffer to SEQUENCE_LENGTH (30 frames)."""
        landmarks = [{"x": 0.5, "y": 0.5, "z": 0.0}] * 33
        for _ in range(clf.SEQUENCE_LENGTH):
            clf.add_frame(person_id, landmarks)

    # ── Binary sigmoid compatibility ──

    def test_binary_sigmoid_high_fall(self, mock_onnx_output_binary_sigmoid):
        """Test binary sigmoid model with high fall probability."""
        clf = self._make_classifier(enabled=True, output_dim=1)
        self._fill_buffer(clf)

        with patch.object(clf, "_run_inference", return_value=mock_onnx_output_binary_sigmoid):
            result = clf.predict_detailed("person_0")

        assert result.fall_probability == pytest.approx(0.85, abs=0.01)
        assert result.fall_type == "unknown"  # Binary model returns "unknown" (no directional info)
        assert result.class_probabilities["normal"] == pytest.approx(0.15, abs=0.01)

    def test_binary_sigmoid_low_fall(self):
        """Test binary sigmoid model with low fall probability (normal)."""
        clf = self._make_classifier(enabled=True, output_dim=1)
        self._fill_buffer(clf)
        output = np.array([0.2], dtype=np.float32)

        with patch.object(clf, "_run_inference", return_value=output):
            result = clf.predict_detailed("person_0")

        assert result.fall_probability == pytest.approx(0.2, abs=0.01)
        assert result.fall_type == "normal"

    # ── Binary softmax compatibility ──

    def test_binary_softmax_fall(self, mock_onnx_output_binary_softmax):
        """Test binary softmax model [normal, fall]."""
        clf = self._make_classifier(enabled=True, output_dim=2)
        self._fill_buffer(clf)

        with patch.object(clf, "_run_inference", return_value=mock_onnx_output_binary_softmax):
            result = clf.predict_detailed("person_0")

        assert result.fall_probability == pytest.approx(0.85, abs=0.01)
        assert result.fall_type == "unknown"  # Binary model returns "unknown" (no directional info)
        assert result.class_probabilities["normal"] == pytest.approx(0.15, abs=0.01)

    def test_binary_softmax_normal(self):
        """Test binary softmax model with normal prediction."""
        clf = self._make_classifier(enabled=True, output_dim=2)
        self._fill_buffer(clf)
        output = np.array([0.9, 0.1], dtype=np.float32)

        with patch.object(clf, "_run_inference", return_value=output):
            result = clf.predict_detailed("person_0")

        assert result.fall_probability == pytest.approx(0.1, abs=0.01)
        assert result.fall_type == "normal"

    # ── 4-class fall_type extraction ──

    def test_4class_front_fall(self, mock_onnx_output_4class):
        """Test 4-class model with front fall dominant."""
        clf = self._make_classifier(enabled=True, output_dim=4)
        self._fill_buffer(clf)

        with patch.object(clf, "_run_inference", return_value=mock_onnx_output_4class):
            result = clf.predict_detailed("person_0")

        assert result.fall_probability == pytest.approx(0.9, abs=0.01)  # 1.0 - 0.1
        assert result.fall_type == "front_fall"
        assert result.class_probabilities["front_fall"] == pytest.approx(0.6, abs=0.01)

    def test_4class_back_fall(self, mock_onnx_output_4class_back_fall):
        """Test 4-class model with back fall dominant."""
        clf = self._make_classifier(enabled=True, output_dim=4)
        self._fill_buffer(clf)

        with patch.object(clf, "_run_inference", return_value=mock_onnx_output_4class_back_fall):
            result = clf.predict_detailed("person_0")

        assert result.fall_probability == pytest.approx(0.95, abs=0.01)
        assert result.fall_type == "back_fall"

    def test_4class_side_fall(self, mock_onnx_output_4class_side_fall):
        """Test 4-class model with side fall dominant."""
        clf = self._make_classifier(enabled=True, output_dim=4)
        self._fill_buffer(clf)

        with patch.object(clf, "_run_inference", return_value=mock_onnx_output_4class_side_fall):
            result = clf.predict_detailed("person_0")

        assert result.fall_probability == pytest.approx(0.9, abs=0.01)
        assert result.fall_type == "side_fall"

    def test_4class_normal(self, mock_onnx_output_4class_normal):
        """Test 4-class model with normal prediction."""
        clf = self._make_classifier(enabled=True, output_dim=4)
        self._fill_buffer(clf)

        with patch.object(clf, "_run_inference", return_value=mock_onnx_output_4class_normal):
            result = clf.predict_detailed("person_0")

        assert result.fall_probability == pytest.approx(0.15, abs=0.01)
        assert result.fall_type == "normal"

    # ── Buffer management ──

    def test_add_frame_populates_buffer(self):
        """Test that add_frame correctly populates the buffer."""
        clf = self._make_classifier()
        landmarks = [{"x": 0.5, "y": 0.5, "z": 0.0}] * 33

        clf.add_frame("person_0", landmarks)
        assert len(clf._buffers["person_0"]) == 1

    def test_buffer_maxlen(self):
        """Test that buffer respects maxlen=30."""
        clf = self._make_classifier()
        landmarks = [{"x": 0.5, "y": 0.5, "z": 0.0}] * 33

        for _ in range(50):
            clf.add_frame("person_0", landmarks)

        assert len(clf._buffers["person_0"]) == clf.SEQUENCE_LENGTH

    def test_insufficient_landmarks_ignored(self):
        """Test that frames with <33 landmarks are ignored."""
        clf = self._make_classifier()
        landmarks = [{"x": 0.5, "y": 0.5, "z": 0.0}] * 10  # only 10

        clf.add_frame("person_0", landmarks)
        assert "person_0" not in clf._buffers

    # ── Disabled classifier behavior ──

    def test_disabled_predict_returns_zero(self):
        """Test that disabled classifier returns 0.0."""
        clf = self._make_classifier(enabled=False)
        self._fill_buffer(clf)

        result = clf.predict("person_0")
        assert result == 0.0

    def test_disabled_predict_detailed_returns_default(self):
        """Test that disabled classifier returns default FallPrediction."""
        clf = self._make_classifier(enabled=False)
        self._fill_buffer(clf)

        result = clf.predict_detailed("person_0")
        assert result.fall_probability == 0.0
        assert result.fall_type == "normal"
        assert result.class_probabilities["normal"] == 1.0

    # ── predict() backward compatibility ──

    def test_predict_returns_float(self, mock_onnx_output_4class):
        """Test that predict() returns a plain float (backward compatible)."""
        clf = self._make_classifier(enabled=True, output_dim=4)
        self._fill_buffer(clf)

        with patch.object(clf, "_run_inference", return_value=mock_onnx_output_4class):
            result = clf.predict("person_0")

        assert isinstance(result, float)
        assert 0.0 <= result <= 1.0

    # ── Reset ──

    def test_reset_person(self):
        """Test reset_person clears buffer."""
        clf = self._make_classifier()
        self._fill_buffer(clf, "person_0")
        assert "person_0" in clf._buffers

        clf.reset_person("person_0")
        assert "person_0" not in clf._buffers

    def test_reset_all(self):
        """Test reset_all clears all buffers."""
        clf = self._make_classifier()
        self._fill_buffer(clf, "person_0")
        self._fill_buffer(clf, "person_1")

        clf.reset_all()
        assert len(clf._buffers) == 0

    # ── CLASS_NAMES ──

    def test_class_names_mapping(self):
        """Test that _CLASS_NAMES has expected entries."""
        assert _CLASS_NAMES[0] == "normal"
        assert _CLASS_NAMES[1] == "front_fall"
        assert _CLASS_NAMES[2] == "back_fall"
        assert _CLASS_NAMES[3] == "side_fall"
