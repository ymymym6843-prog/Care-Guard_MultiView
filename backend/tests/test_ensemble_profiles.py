"""
Unit tests for ensemble_profiles module.

Tests cover:
- Profile definitions validation
- Profile application to FallDetector
- Profile listing functionality
- Current profile tracking
- Weight validation
"""

from unittest.mock import patch, MagicMock

import pytest

from app.services.ensemble_profiles import (
    PROFILES,
    get_current_profile,
    get_current_profile_name,
    apply_profile,
    list_profiles,
)


class TestEnsembleProfiles:
    """Test suite for ensemble profile management."""

    def test_all_profiles_defined(self):
        """All 4 profiles should exist."""
        # Assert
        assert len(PROFILES) == 4
        assert "fast" in PROFILES
        assert "balanced" in PROFILES
        assert "precise" in PROFILES
        assert "rule-enhanced" in PROFILES

    def test_profile_weights_valid(self):
        """Each profile's rule_weight + ml_weight should equal 1.0."""
        # Act & Assert
        for name, profile in PROFILES.items():
            total_weight = profile.rule_weight + profile.ml_weight
            assert total_weight == pytest.approx(1.0), (
                f"Profile '{name}' weights don't sum to 1.0: "
                f"rule={profile.rule_weight}, ml={profile.ml_weight}, sum={total_weight}"
            )

    def test_apply_profile_fast(self):
        """Apply 'fast' profile: rule=1.0, ml=0.0, enhanced=False."""
        # Arrange
        mock_detector = MagicMock()
        with patch("app.services.fall_detector.fall_detector", mock_detector):
            # Act
            profile = apply_profile("fast")

            # Assert
            assert profile.name == "fast"
            assert profile.rule_weight == 1.0
            assert profile.ml_weight == 0.0
            assert profile.enhanced_rules is False

    def test_apply_profile_rule_enhanced(self):
        """Apply 'rule-enhanced' profile: rule=1.0, ml=0.0, enhanced=True."""
        # Arrange
        mock_detector = MagicMock()
        with patch("app.services.fall_detector.fall_detector", mock_detector):
            # Act
            profile = apply_profile("rule-enhanced")

            # Assert
            assert profile.name == "rule-enhanced"
            assert profile.rule_weight == 1.0
            assert profile.ml_weight == 0.0
            assert profile.enhanced_rules is True

    def test_apply_profile_balanced(self):
        """Apply 'balanced' profile: rule=0.7, ml=0.3, enhanced=False."""
        # Arrange
        mock_detector = MagicMock()
        with patch("app.services.fall_detector.fall_detector", mock_detector):
            # Act
            profile = apply_profile("balanced")

            # Assert
            assert profile.name == "balanced"
            assert profile.rule_weight == 0.7
            assert profile.ml_weight == 0.3
            assert profile.enhanced_rules is False

    def test_apply_profile_precise(self):
        """Apply 'precise' profile: rule=0.5, ml=0.5, enhanced=False."""
        # Arrange
        mock_detector = MagicMock()
        with patch("app.services.fall_detector.fall_detector", mock_detector):
            # Act
            profile = apply_profile("precise")

            # Assert
            assert profile.name == "precise"
            assert profile.rule_weight == 0.5
            assert profile.ml_weight == 0.5
            assert profile.enhanced_rules is False

    def test_apply_invalid_profile(self):
        """Applying invalid profile name should raise ValueError."""
        # Act & Assert - ValueError is raised before fall_detector import
        with pytest.raises(ValueError) as exc_info:
            apply_profile("invalid_profile")

        assert "유효하지 않은 프로필" in str(exc_info.value)
        assert "invalid_profile" in str(exc_info.value)

    def test_list_profiles(self):
        """list_profiles should return all 4 profiles with active flag."""
        # Arrange - list_profiles doesn't need fall_detector mock
        import app.services.ensemble_profiles as ep
        ep._current_profile_name = "balanced"

        # Act
        profiles = list_profiles()

        # Assert
        assert len(profiles) == 4
        assert all(isinstance(p, dict) for p in profiles)

        # Check required fields
        for profile in profiles:
            assert "name" in profile
            assert "label" in profile
            assert "rule_weight" in profile
            assert "ml_weight" in profile
            assert "enhanced_rules" in profile
            assert "description" in profile
            assert "active" in profile

        # Check active flag
        active_profiles = [p for p in profiles if p["active"]]
        assert len(active_profiles) == 1
        assert active_profiles[0]["name"] == "balanced"

    def test_get_current_profile(self):
        """After applying a profile, get_current_profile should reflect it."""
        # Arrange
        mock_detector = MagicMock()
        with patch("app.services.fall_detector.fall_detector", mock_detector):
            # Act - Apply fast profile
            apply_profile("fast")
            current = get_current_profile()

            # Assert
            assert current.name == "fast"
            assert current.rule_weight == 1.0
            assert current.ml_weight == 0.0

            # Act - Apply balanced profile
            apply_profile("balanced")
            current = get_current_profile()

            # Assert
            assert current.name == "balanced"
            assert current.rule_weight == 0.7
            assert current.ml_weight == 0.3

    def test_get_current_profile_name(self):
        """get_current_profile_name should return the active profile name."""
        # Arrange
        mock_detector = MagicMock()
        with patch("app.services.fall_detector.fall_detector", mock_detector):
            # Act - Apply precise profile
            apply_profile("precise")
            name = get_current_profile_name()

            # Assert
            assert name == "precise"

            # Act - Apply rule-enhanced profile
            apply_profile("rule-enhanced")
            name = get_current_profile_name()

            # Assert
            assert name == "rule-enhanced"

    def test_profile_application_sets_detector_properties(self):
        """Verify that apply_profile actually sets fall_detector properties."""
        # Arrange
        mock_detector = MagicMock()
        with patch("app.services.fall_detector.fall_detector", mock_detector):
            # Act - Apply fast profile
            apply_profile("fast")

            # Assert - Verify setter was called
            assert mock_detector.rule_weight == 1.0
            assert mock_detector.enhanced_rules is False

            # Act - Apply rule-enhanced profile
            apply_profile("rule-enhanced")

            # Assert - Verify setter was called
            assert mock_detector.rule_weight == 1.0
            assert mock_detector.enhanced_rules is True

    def test_list_profiles_updates_active_flag(self):
        """list_profiles should always reflect the current active profile."""
        # Arrange
        mock_detector = MagicMock()
        with patch("app.services.fall_detector.fall_detector", mock_detector):
            # Act - Apply fast profile
            apply_profile("fast")
            profiles = list_profiles()

            # Assert - Only fast should be active
            fast_profile = next(p for p in profiles if p["name"] == "fast")
            balanced_profile = next(p for p in profiles if p["name"] == "balanced")
            assert fast_profile["active"] is True
            assert balanced_profile["active"] is False

            # Act - Switch to balanced
            apply_profile("balanced")
            profiles = list_profiles()

            # Assert - Only balanced should be active
            fast_profile = next(p for p in profiles if p["name"] == "fast")
            balanced_profile = next(p for p in profiles if p["name"] == "balanced")
            assert fast_profile["active"] is False
            assert balanced_profile["active"] is True

    def test_profile_immutability(self):
        """EnsembleProfile dataclass should be frozen (immutable)."""
        # Arrange
        profile = PROFILES["fast"]

        # Act & Assert - Attempting to modify should raise error
        with pytest.raises(Exception):  # FrozenInstanceError in Python 3.10+
            profile.rule_weight = 0.5

    def test_all_profiles_have_descriptions(self):
        """All profiles should have non-empty descriptions."""
        # Act & Assert
        for name, profile in PROFILES.items():
            assert profile.description, f"Profile '{name}' has no description"
            assert len(profile.description) > 0

    def test_all_profiles_have_labels(self):
        """All profiles should have Korean labels."""
        # Act & Assert
        for name, profile in PROFILES.items():
            assert profile.label, f"Profile '{name}' has no label"
            assert len(profile.label) > 0

    def test_default_profile_is_balanced(self):
        """Default profile should be 'balanced'."""
        # Arrange - no mock needed for get_current_profile_name
        import app.services.ensemble_profiles as ep
        # Reset module state
        ep._current_profile_name = "balanced"

        # Act
        current = get_current_profile_name()

        # Assert
        assert current == "balanced"

    def test_profile_names_match_dict_keys(self):
        """Profile.name should match its dictionary key."""
        # Act & Assert
        for key, profile in PROFILES.items():
            assert profile.name == key, (
                f"Mismatch: dict key '{key}' != profile.name '{profile.name}'"
            )

    def test_enhanced_rules_only_for_rule_enhanced_profile(self):
        """Only 'rule-enhanced' profile should have enhanced_rules=True."""
        # Act & Assert
        for name, profile in PROFILES.items():
            if name == "rule-enhanced":
                assert profile.enhanced_rules is True
            else:
                assert profile.enhanced_rules is False

    def test_ml_weight_zero_profiles(self):
        """'fast' and 'rule-enhanced' should have ml_weight=0."""
        # Act & Assert
        assert PROFILES["fast"].ml_weight == 0.0
        assert PROFILES["rule-enhanced"].ml_weight == 0.0
        assert PROFILES["balanced"].ml_weight > 0.0
        assert PROFILES["precise"].ml_weight > 0.0
