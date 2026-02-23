"""
Unit tests for AlertManager service.

Tests cover:
- Initial state is "normal"
- Low-confidence fall → monitoring path
- High-confidence fall → direct WARNING bypass
- Actual fall_type → direct WARNING bypass
- Transition to "warning" after warning_seconds
- Transition to "danger" after danger_seconds
- Acknowledge resets state
- Normal pose resets alert state
- Per-person state tracking
- Global state management
- Event callbacks
"""

import time

import pytest

from app.services.alert_manager import AlertManager, AlertState, PersonAlert


class TestAlertManager:
    """Test suite for AlertManager class."""

    def test_initial_state_is_normal(self):
        """Test that AlertManager initializes with normal state."""
        manager = AlertManager()
        assert manager.global_state == AlertState.NORMAL
        assert manager.alert_duration == 0.0

    def test_low_confidence_fall_transitions_to_monitoring(self):
        """Test that low-confidence fall (< 0.5) transitions to monitoring."""
        manager = AlertManager()
        person_id = "person_0"

        result = manager.update(
            person_id=person_id,
            is_fallen=True,
            confidence=0.35,
            fall_duration=0.5,
        )

        assert result["state"] == AlertState.MONITORING.value
        assert result["changed"] is True
        assert result["person_id"] == person_id
        assert manager.global_state == AlertState.MONITORING

    def test_high_confidence_bypasses_monitoring(self):
        """Test that confidence >= 0.5 goes directly to WARNING (not MONITORING)."""
        manager = AlertManager()
        person_id = "person_high_conf"

        result = manager.update(
            person_id=person_id,
            is_fallen=True,
            confidence=0.6,
            fall_duration=0.3,  # < 0.5s to avoid immediate DANGER escalation
        )

        assert result["state"] == AlertState.WARNING.value
        assert result["changed"] is True
        assert manager.global_state == AlertState.WARNING

    def test_actual_fall_type_bypasses_to_danger(self):
        """Test that actual fall types (front/back/side) go directly to DANGER."""
        for fall_type in ("front_fall", "back_fall", "side_fall"):
            manager = AlertManager()
            result = manager.update(
                person_id=f"person_{fall_type}",
                is_fallen=True,
                confidence=0.5,  # low confidence
                fall_duration=0.3,
                fall_type=fall_type,
            )
            assert result["state"] == AlertState.DANGER.value, f"Failed for {fall_type}"
            assert manager.global_state == AlertState.DANGER

    def test_pre_impact_goes_to_monitoring(self):
        """Test that pre_impact with low confidence goes to MONITORING."""
        manager = AlertManager()
        result = manager.update(
            person_id="person_pre",
            is_fallen=True,
            confidence=0.35,
            fall_duration=0.3,
            fall_type="pre_impact",
        )
        assert result["state"] == AlertState.MONITORING.value

    def test_transition_to_warning_after_warning_seconds(self):
        """Test transition from monitoring to warning after warning_seconds."""
        manager = AlertManager()
        manager.warning_seconds = 3.0
        person_id = "person_warning"

        # Initial fall detection → monitoring (confidence < 0.5)
        manager.update(person_id, is_fallen=True, confidence=0.35, fall_duration=0.5)

        # fall_duration exceeds warning_seconds → warning
        result = manager.update(person_id, is_fallen=True, confidence=0.35, fall_duration=3.5)

        assert result["state"] == AlertState.WARNING.value
        assert result["changed"] is True
        assert manager.global_state == AlertState.WARNING

    def test_transition_to_danger_after_danger_seconds(self):
        """Test transition to danger with high confidence (>= 0.70)."""
        manager = AlertManager()
        manager.warning_seconds = 3.0
        person_id = "person_danger"

        # monitoring (confidence < 0.5)
        manager.update(person_id, is_fallen=True, confidence=0.35, fall_duration=0.5)
        # warning (duration exceeds warning_seconds, low confidence stays below 0.70)
        manager.update(person_id, is_fallen=True, confidence=0.35, fall_duration=3.5)
        # danger (confidence jumps to 0.75, max_conf >= 0.70, threshold=0.5s)
        result = manager.update(person_id, is_fallen=True, confidence=0.75, fall_duration=4.5)

        assert result["state"] == AlertState.DANGER.value
        assert result["changed"] is True
        assert manager.global_state == AlertState.DANGER

    def test_acknowledge_resets_warning_state(self):
        """Test that acknowledge resets warning state to acknowledged."""
        manager = AlertManager()
        person_id = "person_ack"

        # Trigger warning (confidence >= 0.5 → WARNING directly)
        manager.update(person_id, is_fallen=True, confidence=0.6, fall_duration=0.5)

        result = manager.acknowledge(person_id=person_id, acknowledged_by="staff_user")

        assert result is True
        assert manager._person_alerts[person_id].state == AlertState.ACKNOWLEDGED
        assert manager._person_alerts[person_id].acknowledged_by == "staff_user"
        assert manager.global_state == AlertState.ACKNOWLEDGED

    def test_acknowledge_resets_danger_state(self):
        """Test that acknowledge works for danger state."""
        manager = AlertManager()
        person_id = "person_ack_danger"

        # Trigger danger via actual fall type (immediate DANGER)
        manager.update(person_id, is_fallen=True, confidence=0.8, fall_duration=0.5, fall_type="front_fall")

        result = manager.acknowledge(person_id=person_id)

        assert result is True
        assert manager._person_alerts[person_id].state == AlertState.ACKNOWLEDGED

    def test_acknowledge_all_persons(self):
        """Test acknowledge without person_id acknowledges all active alerts."""
        manager = AlertManager()

        # Create multiple warnings (confidence >= 0.5 → WARNING directly)
        manager.update("person_0", is_fallen=True, confidence=0.6, fall_duration=0.5)
        manager.update("person_1", is_fallen=True, confidence=0.6, fall_duration=0.5)

        result = manager.acknowledge(person_id=None, acknowledged_by="admin")

        assert result is True
        assert manager._person_alerts["person_0"].state == AlertState.ACKNOWLEDGED
        assert manager._person_alerts["person_1"].state == AlertState.ACKNOWLEDGED
        assert manager._person_alerts["person_0"].acknowledged_by == "admin"

    def test_normal_pose_resets_monitoring_state(self):
        """Test that normal pose (is_fallen=False) resets monitoring state."""
        manager = AlertManager()
        person_id = "person_reset"

        # Trigger monitoring (confidence < 0.5)
        manager.update(person_id, is_fallen=True, confidence=0.35, fall_duration=0.5)
        assert manager._person_alerts[person_id].state == AlertState.MONITORING

        # Return to normal
        result = manager.update(person_id, is_fallen=False, confidence=0.0, fall_duration=0.0)

        assert result["state"] == AlertState.NORMAL.value
        assert result["changed"] is True
        assert manager._person_alerts[person_id].fall_start_time is None

    def test_warning_resets_on_normal_pose(self):
        """Test that WARNING auto-resets to NORMAL after min hold time when person recovers."""
        manager = AlertManager()
        manager.warning_seconds = 1.0
        person_id = "person_warning_reset"

        # Trigger warning (confidence >= 0.5 → WARNING directly)
        manager.update(person_id, is_fallen=True, confidence=0.6, fall_duration=0.5)
        assert manager._person_alerts[person_id].state == AlertState.WARNING

        # Normal pose within min hold time → WARNING maintained
        result = manager.update(person_id, is_fallen=False, confidence=0.0, fall_duration=0.0)
        assert manager._person_alerts[person_id].state == AlertState.WARNING

        # Simulate time passing beyond min hold time (max(1.0+1.0, 3.0) = 3.0s)
        manager._person_alerts[person_id].warning_time = time.time() - 4.0
        result = manager.update(person_id, is_fallen=False, confidence=0.0, fall_duration=0.0)
        assert manager._person_alerts[person_id].state == AlertState.NORMAL

    def test_danger_auto_resets_after_recovery_period(self):
        """Test that DANGER auto-resets to NORMAL after recovery cooldown."""
        import time as _time

        manager = AlertManager()
        manager.warning_seconds = 1.0
        person_id = "person_danger_reset"

        # Trigger danger via actual fall
        manager.update(person_id, is_fallen=True, confidence=0.8, fall_duration=0.0, fall_type="front_fall")
        assert manager._person_alerts[person_id].state == AlertState.DANGER

        # First normal pose → starts recovery timer but stays DANGER
        manager.update(person_id, is_fallen=False, confidence=0.0, fall_duration=0.0)
        assert manager._person_alerts[person_id].state == AlertState.DANGER
        assert manager._person_alerts[person_id].recovery_start_time is not None

        # Simulate time passing beyond auto-reset threshold
        manager._person_alerts[person_id].recovery_start_time = _time.time() - 6.0
        result = manager.update(person_id, is_fallen=False, confidence=0.0, fall_duration=0.0)
        assert manager._person_alerts[person_id].state == AlertState.NORMAL

    def test_danger_recovery_resets_on_re_fall(self):
        """Test that recovery timer resets if fall is re-detected during DANGER."""
        manager = AlertManager()
        person_id = "person_refall"

        # Trigger danger
        manager.update(person_id, is_fallen=True, confidence=0.8, fall_duration=0.0, fall_type="back_fall")
        assert manager._person_alerts[person_id].state == AlertState.DANGER

        # Start recovery
        manager.update(person_id, is_fallen=False, confidence=0.0, fall_duration=0.0)
        assert manager._person_alerts[person_id].recovery_start_time is not None

        # Re-detected fall → recovery timer should reset
        manager.update(person_id, is_fallen=True, confidence=0.7, fall_duration=1.0, fall_type="back_fall")
        assert manager._person_alerts[person_id].recovery_start_time is None

    def test_acknowledged_resets_to_normal_on_normal_pose(self):
        """Test that acknowledged state resets to normal when normal pose returns."""
        manager = AlertManager()
        person_id = "person_ack_reset"

        # Trigger WARNING and acknowledge (confidence >= 0.5 → WARNING directly)
        manager.update(person_id, is_fallen=True, confidence=0.6, fall_duration=0.5)
        manager.acknowledge(person_id=person_id)
        assert manager._person_alerts[person_id].state == AlertState.ACKNOWLEDGED

        # Normal pose
        result = manager.update(person_id, is_fallen=False, confidence=0.0, fall_duration=0.0)

        assert result["state"] == AlertState.NORMAL.value
        assert manager._person_alerts[person_id].fall_start_time is None
        assert manager._person_alerts[person_id].acknowledged_by is None

    def test_per_person_state_tracking(self):
        """Test that AlertManager maintains independent state for each person."""
        manager = AlertManager()

        # Person 0 in warning (confidence >= 0.5 → WARNING directly), Person 1 normal
        manager.update("person_0", is_fallen=True, confidence=0.6, fall_duration=0.5)
        manager.update("person_1", is_fallen=False, confidence=0.0, fall_duration=0.0)

        assert manager._person_alerts["person_0"].state == AlertState.WARNING
        assert manager._person_alerts["person_1"].state == AlertState.NORMAL

    def test_global_state_reflects_most_severe(self):
        """Test that global state reflects the most severe individual state."""
        manager = AlertManager()

        # person_0: monitoring (confidence < 0.5)
        manager.update("person_0", is_fallen=True, confidence=0.35, fall_duration=0.5)
        # person_1: warning (confidence >= 0.5)
        manager.update("person_1", is_fallen=True, confidence=0.6, fall_duration=0.5)
        # person_2: danger (actual fall type → immediate DANGER)
        manager.update("person_2", is_fallen=True, confidence=0.6, fall_duration=0.5, fall_type="front_fall")

        assert manager.global_state == AlertState.DANGER

    def test_alert_duration_property(self):
        """Test that alert_duration property returns correct duration."""
        manager = AlertManager()
        person_id = "person_duration"

        # Trigger WARNING (confidence >= 0.5)
        manager.update(person_id, is_fallen=True, confidence=0.6, fall_duration=0.5)

        assert manager.alert_duration > 0.0

    def test_on_alert_change_callback(self):
        """Test that alert change callbacks are triggered."""
        manager = AlertManager()
        callback_data = []

        def test_callback(data):
            callback_data.append(data)

        manager.on_alert_change(test_callback)

        # Low confidence (< 0.5) → monitoring
        manager.update("person_0", is_fallen=True, confidence=0.35, fall_duration=0.5)

        assert len(callback_data) == 1
        assert callback_data[0]["state"] == AlertState.MONITORING.value

    def test_on_alert_change_callback_high_confidence(self):
        """Test callback fires with WARNING state for high confidence."""
        manager = AlertManager()
        callback_data = []

        def test_callback(data):
            callback_data.append(data)

        manager.on_alert_change(test_callback)

        # High confidence → direct WARNING (fall_duration < 0.5 to avoid DANGER escalation)
        manager.update("person_0", is_fallen=True, confidence=0.6, fall_duration=0.3)

        assert len(callback_data) == 1
        assert callback_data[0]["state"] == AlertState.WARNING.value

    def test_on_event_callback_for_warning(self):
        """Test that event callbacks are triggered for warning state."""
        manager = AlertManager()
        manager.warning_seconds = 1.0
        event_data = []

        def test_event_callback(data):
            event_data.append(data)

        manager.on_event(test_event_callback)

        # Trigger monitoring (no event for MONITORING)
        manager.update("person_0", is_fallen=True, confidence=0.35, fall_duration=0.5)

        # Trigger warning via duration (should fire event)
        manager.update("person_0", is_fallen=True, confidence=0.35, fall_duration=1.5)

        assert len(event_data) >= 1
        assert event_data[-1]["state"] == AlertState.WARNING.value

    def test_get_state_for_frontend_danger(self):
        """Test get_state_for_frontend returns 'danger' for DANGER state."""
        manager = AlertManager()

        # Actual fall type → immediate DANGER
        manager.update("person_0", is_fallen=True, confidence=0.8, fall_duration=0.5, fall_type="front_fall")
        state = manager.get_state_for_frontend()

        assert state == "danger"

    def test_get_state_for_frontend_warning(self):
        """Test get_state_for_frontend returns 'warning' for WARNING state."""
        manager = AlertManager()

        # Confidence >= 0.5 → WARNING directly
        manager.update("person_0", is_fallen=True, confidence=0.6, fall_duration=0.5)
        state = manager.get_state_for_frontend()

        assert state == "warning"

    def test_get_state_for_frontend_monitoring_maps_to_safe(self):
        """Test get_state_for_frontend returns 'safe' for MONITORING state (alarm fatigue prevention)."""
        manager = AlertManager()

        # Confidence < 0.5 → MONITORING (maps to "safe" on frontend)
        manager.update("person_0", is_fallen=True, confidence=0.35, fall_duration=0.5)
        state = manager.get_state_for_frontend()

        assert state == "safe"

    def test_get_state_for_frontend_safe(self):
        """Test get_state_for_frontend returns 'safe' for normal states."""
        manager = AlertManager()
        state = manager.get_state_for_frontend()
        assert state == "safe"

    def test_warning_seconds_setter(self):
        """Test that warning_seconds setter works correctly."""
        manager = AlertManager()
        manager.warning_seconds = 5.0
        assert manager.warning_seconds == 5.0

    def test_danger_seconds_setter(self):
        """Test that danger_seconds setter works correctly."""
        manager = AlertManager()
        manager.danger_seconds = 15.0
        assert manager.danger_seconds == 15.0

    def test_acknowledge_returns_false_for_normal_state(self):
        """Test that acknowledge returns False when no active alerts."""
        manager = AlertManager()
        result = manager.acknowledge(person_id="nonexistent_person")
        assert not result

    def test_state_does_not_change_if_already_in_target_state(self):
        """Test that changed=False when already in target state."""
        manager = AlertManager()
        person_id = "person_same_state"

        result1 = manager.update(person_id, is_fallen=True, confidence=0.6, fall_duration=0.5)
        result2 = manager.update(person_id, is_fallen=True, confidence=0.6, fall_duration=0.6)

        assert result1["changed"] is True
        assert result2["changed"] is False

    def test_monitoring_to_warning_to_danger_progression(self):
        """Test full progression from monitoring to warning to danger."""
        manager = AlertManager()
        manager.warning_seconds = 3.0
        person_id = "person_progression"

        # Monitoring (confidence < 0.5)
        r1 = manager.update(person_id, is_fallen=True, confidence=0.35, fall_duration=0.5)
        assert r1["state"] == AlertState.MONITORING.value
        assert r1["changed"] is True

        # Warning (duration exceeds warning_seconds, keep low confidence to avoid instant DANGER)
        r2 = manager.update(person_id, is_fallen=True, confidence=0.35, fall_duration=3.5)
        assert r2["state"] == AlertState.WARNING.value
        assert r2["changed"] is True

        # Danger (confidence increases to >= 0.70, max_conf >= 0.70, threshold=0.5s)
        r3 = manager.update(person_id, is_fallen=True, confidence=0.75, fall_duration=4.5)
        assert r3["state"] == AlertState.DANGER.value
        assert r3["changed"] is True

    def test_result_includes_confidence(self):
        """Test that update result includes confidence value."""
        manager = AlertManager()
        result = manager.update("person_0", is_fallen=True, confidence=0.85, fall_duration=0.5)

        assert "confidence" in result
        assert result["confidence"] == 0.85

    def test_actual_fall_immediate_danger_first_frame(self):
        """Test that actual falls reach DANGER on the very first update (no waiting)."""
        manager = AlertManager()
        result = manager.update(
            person_id="person_immediate",
            is_fallen=True,
            confidence=0.4,  # even low confidence
            fall_duration=0.1,  # very first frame
            fall_type="front_fall",
        )
        assert result["state"] == AlertState.DANGER.value
        assert result["changed"] is True
        assert manager.get_state_for_frontend() == "danger"

    def test_pre_impact_does_not_reach_danger_immediately(self):
        """Test that pre_impact stays at MONITORING, not DANGER."""
        manager = AlertManager()
        result = manager.update(
            person_id="person_pre",
            is_fallen=True,
            confidence=0.35,
            fall_duration=0.3,
            fall_type="pre_impact",
        )
        assert result["state"] == AlertState.MONITORING.value
        # Should NOT be danger, MONITORING maps to "safe" for frontend
        assert manager.get_state_for_frontend() == "safe"

    def test_pre_impact_escalates_with_high_confidence(self):
        """Test that pre_impact escalates to DANGER when confidence reaches >= 0.70."""
        manager = AlertManager()
        manager.warning_seconds = 1.0

        # monitoring (confidence < 0.5)
        manager.update("person_0", is_fallen=True, confidence=0.35, fall_duration=0.3, fall_type="pre_impact")
        assert manager._person_alerts["person_0"].state == AlertState.MONITORING

        # warning (duration exceeds warning_seconds)
        manager.update("person_0", is_fallen=True, confidence=0.35, fall_duration=1.5, fall_type="pre_impact")
        assert manager._person_alerts["person_0"].state == AlertState.WARNING

        # Not yet danger (max_confidence 0.35 < 0.70, can_danger=False)
        r = manager.update("person_0", is_fallen=True, confidence=0.55, fall_duration=3.0, fall_type="pre_impact")
        assert r["state"] == AlertState.WARNING.value

        # Now danger (confidence 0.75 → max_conf >= 0.70, threshold=0.5s, duration 5.5 >= 0.5)
        r = manager.update("person_0", is_fallen=True, confidence=0.75, fall_duration=5.5, fall_type="pre_impact")
        assert r["state"] == AlertState.DANGER.value

    def test_actual_fall_all_types_immediate_danger(self):
        """Test that all three actual fall types reach DANGER immediately."""
        for fall_type in ("front_fall", "back_fall", "side_fall"):
            manager = AlertManager()
            result = manager.update(
                person_id=f"person_{fall_type}",
                is_fallen=True,
                confidence=0.3,
                fall_duration=0.05,
                fall_type=fall_type,
            )
            assert result["state"] == AlertState.DANGER.value, (
                f"{fall_type} should reach DANGER immediately"
            )
            assert manager.get_state_for_frontend() == "danger"

    def test_high_confidence_still_goes_warning_not_danger(self):
        """Test that high confidence (>=0.8) without actual fall_type goes to WARNING, not DANGER."""
        manager = AlertManager()
        result = manager.update(
            person_id="person_high",
            is_fallen=True,
            confidence=0.9,
            fall_duration=0.3,
            fall_type="unknown",
        )
        # High confidence bypasses MONITORING → WARNING, but NOT directly to DANGER
        assert result["state"] == AlertState.WARNING.value
