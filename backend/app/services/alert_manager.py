"""
알림 상태 머신

States: normal → monitoring → warning → danger → acknowledged
  - 전조 감지 (score 0.3~0.5): 즉시 MONITORING 진입 (조기 경고)
  - MONITORING → WARNING: FALL_WARNING_SECONDS (기본 1.5초)
  - WARNING → DANGER: FALL_DANGER_SECONDS (기본 5.0초)
  - 고확신 낙상 (confidence >= 0.6): MONITORING 건너뛰고 바로 WARNING
  - 실제 낙상 (front/back/side_fall): 즉시 DANGER (대기 없음)
  - 전조 MONITORING 중 실제 낙상 → 즉시 WARNING (대기 불필요)
각 추적된 인물에 대해 독립적인 타이머를 관리합니다.
"""

import asyncio
import time
from dataclasses import dataclass
from enum import Enum

from app.config import settings
from app.core.logging_config import get_logger

logger = get_logger("app.services.alert_manager")


class AlertState(str, Enum):
    NORMAL = "normal"
    MONITORING = "monitoring"
    WARNING = "warning"
    DANGER = "danger"
    ACKNOWLEDGED = "acknowledged"


@dataclass
class PersonAlert:
    """개인별 알림 상태"""
    person_id: str
    state: AlertState = AlertState.NORMAL
    fall_start_time: float | None = None
    warning_time: float | None = None
    danger_time: float | None = None
    acknowledged_by: str | None = None
    pre_impact_warned: bool = False  # 전조 감지로 MONITORING 진입 여부
    walking_aid_warned: bool = False  # 보행도구 분실로 MONITORING 진입 여부
    recovery_start_time: float | None = None  # 회복 시작 시각 (DANGER 자동 리셋용)
    max_fall_confidence: float = 0.0  # WARNING 이후 관측된 최대 확신도


class AlertManager:
    # 실제 낙상 유형 (빠른 에스컬레이션 대상)
    ACTUAL_FALL_TYPES = frozenset({"front_fall", "back_fall", "side_fall"})

    # DANGER 상태 자동 리셋 대기 시간 (초)
    # fall_detector 쿨다운(3초) 이후 추가 대기 → 총 ~8초 후 자동 해제
    _DANGER_AUTO_RESET_SECONDS = 5.0

    def __init__(self):
        self._person_alerts: dict[str, PersonAlert] = {}
        self._global_state: AlertState = AlertState.NORMAL
        self._warning_seconds = settings.FALL_WARNING_SECONDS
        self._danger_seconds = settings.FALL_DANGER_SECONDS
        self._danger_seconds_actual = settings.FALL_DANGER_SECONDS_ACTUAL
        self._danger_confidence = settings.FALL_DANGER_CONFIDENCE
        self._callbacks: list = []
        self._event_callbacks: list = []

    def reset_camera(self, camera_id: str):
        """특정 카메라의 알림 상태만 리셋 (다른 카메라 보존)"""
        prefix = f"{camera_id}_"
        to_remove = [pid for pid in self._person_alerts if pid.startswith(prefix)]
        for pid in to_remove:
            del self._person_alerts[pid]
        # 글로벌 상태 재계산: 남은 person 중 가장 높은 알림 수준 유지
        if self._person_alerts:
            max_state = max(p.state for p in self._person_alerts.values())
            self._global_state = max_state
        else:
            self._global_state = AlertState.NORMAL
        if to_remove:
            logger.info("[%s] 카메라별 알림 리셋: %d명", camera_id, len(to_remove))

    def reset_all(self):
        """모든 인물의 알림 상태 리셋 (데모 영상 반복/카메라 전환 시)"""
        self._person_alerts.clear()
        self._global_state = AlertState.NORMAL
        logger.info("모든 알림 상태 리셋")

    # --- Public setters for settings_route ---
    @property
    def warning_seconds(self) -> float:
        return self._warning_seconds

    @warning_seconds.setter
    def warning_seconds(self, value: float) -> None:
        self._warning_seconds = value
        logger.info("warning_seconds 변경: %s", value)

    @property
    def danger_seconds(self) -> float:
        return self._danger_seconds

    @danger_seconds.setter
    def danger_seconds(self, value: float) -> None:
        self._danger_seconds = value
        logger.info("danger_seconds 변경: %s", value)

    @property
    def global_state(self) -> AlertState:
        return self._global_state

    @property
    def alert_duration(self) -> float:
        """현재 알림 지속 시간"""
        for alert in self._person_alerts.values():
            if alert.fall_start_time and alert.state in (AlertState.WARNING, AlertState.DANGER):
                return time.time() - alert.fall_start_time
        return 0.0

    def on_alert_change(self, callback):
        """알림 상태 변경 콜백 등록"""
        self._callbacks.append(callback)

    def on_event(self, callback):
        """이벤트 기록 콜백 등록"""
        self._event_callbacks.append(callback)

    def update(self, person_id: str, is_fallen: bool, confidence: float, fall_duration: float, fall_type: str = "unknown", is_pre_impact: bool = False) -> dict:
        """
        낙상 감지 결과에 따라 알림 상태 업데이트

        Args:
            fall_type: 낙상 유형 (front_fall, back_fall, side_fall, pre_impact, unknown)
            is_pre_impact: 전조 감지 여부 (낙상 전 이상 징후)

        Returns:
            {"state": str, "duration": float, "person_id": str, "changed": bool}
        """
        alert = self._get_or_create(person_id)
        old_state = alert.state
        now = time.time()

        if alert.state == AlertState.ACKNOWLEDGED:
            # acknowledge 상태에서는 정상 포즈가 돌아와야 리셋
            if not is_fallen:
                alert.state = AlertState.NORMAL
                alert.fall_start_time = None
                alert.warning_time = None
                alert.danger_time = None
                alert.acknowledged_by = None

        elif is_fallen:
            # 낙상 재감지 시 회복 타이머 리셋
            alert.recovery_start_time = None
            # 최대 확신도 추적 (프레임별 변동 대비)
            alert.max_fall_confidence = max(alert.max_fall_confidence, confidence)

            if alert.state == AlertState.NORMAL:
                actual_fall = fall_type in self.ACTUAL_FALL_TYPES
                if actual_fall:
                    # 실제 낙상 → 즉시 DANGER (WARNING 건너뜀)
                    alert.state = AlertState.DANGER
                    alert.fall_start_time = now
                    alert.warning_time = now
                    alert.danger_time = now
                    logger.info(
                        "실제 낙상(%s) → DANGER 즉시 전환: person=%s, confidence=%.2f",
                        fall_type, person_id, confidence,
                    )
                elif confidence >= 0.5:
                    # 낙상 감지 → WARNING 즉시
                    alert.state = AlertState.WARNING
                    alert.fall_start_time = now
                    alert.warning_time = now
                    logger.info(
                        "낙상 감지 → WARNING 전환: person=%s, confidence=%.2f",
                        person_id, confidence,
                    )
                else:
                    # pre_impact 등 전조 → MONITORING
                    alert.state = AlertState.MONITORING
                    alert.fall_start_time = now

            # MONITORING → WARNING
            if alert.state == AlertState.MONITORING:
                if alert.pre_impact_warned:
                    # 전조 감지에서 이미 MONITORING → 즉시 WARNING 에스컬레이션
                    alert.state = AlertState.WARNING
                    alert.warning_time = now
                    logger.info(
                        "전조→실제 낙상: MONITORING→WARNING 즉시 전환: person=%s",
                        person_id,
                    )
                elif fall_duration >= self._warning_seconds:
                    # 일반 MONITORING → 타이머 기반 전환 (1.5초)
                    alert.state = AlertState.WARNING
                    alert.warning_time = now

            # WARNING → DANGER: 확률 기반 분리
            # - 실제 낙상(front/back/side): 즉시 DANGER
            # - max_confidence >= 0.70: 0.5초 후 DANGER (빠른 전환)
            # - max_confidence 0.50~0.69: WARNING 유지 (DANGER 전환 안 함)
            actual_fall = fall_type in self.ACTUAL_FALL_TYPES
            if actual_fall:
                threshold = self._danger_seconds_actual  # 0.0초 (즉시)
                can_danger = True
            elif alert.max_fall_confidence >= self._danger_confidence:
                # 고확신 낙상(>=0.70): 0.5초 후 DANGER
                threshold = 0.5
                can_danger = True
            else:
                # 저확신(0.50~0.69): WARNING 유지, DANGER 전환 안 함
                can_danger = False
                threshold = self._danger_seconds

            if (
                can_danger
                and alert.state == AlertState.WARNING
                and fall_duration >= threshold
            ):
                alert.state = AlertState.DANGER
                alert.danger_time = now
                logger.info(
                    "WARNING→DANGER: person=%s, max_conf=%.2f, duration=%.1fs",
                    person_id, alert.max_fall_confidence, fall_duration,
                )

        elif is_pre_impact:
            # 전조 증상 감지 → MONITORING 조기 진입 (주의 표시)
            if alert.state == AlertState.NORMAL:
                alert.state = AlertState.MONITORING
                alert.fall_start_time = now
                alert.pre_impact_warned = True
                logger.info(
                    "전조 감지 → MONITORING 조기 진입: person=%s, confidence=%.2f",
                    person_id, confidence,
                )
            elif alert.state == AlertState.MONITORING and alert.pre_impact_warned:
                # 전조 감지 지속 → 타이머 갱신 (마지막 신호 기준 유지)
                alert.fall_start_time = now

        else:
            # 정상 포즈 (쿨다운은 fall_detector에서 처리)
            # 회복 시 recovery_start_time 리셋 불필요 상태 초기화
            if alert.state in (AlertState.MONITORING,):
                # 전조 감지 MONITORING은 최소 3초 유지 (마지막 전조 신호 기준)
                if alert.pre_impact_warned and alert.fall_start_time:
                    if now - alert.fall_start_time < 3.0:
                        pass  # 최소 유지 시간 미충족 → MONITORING 유지
                    else:
                        alert.state = AlertState.NORMAL
                        alert.fall_start_time = None
                        alert.pre_impact_warned = False
                else:
                    # 비전조 MONITORING도 최소 2초 유지 (단일 프레임 미감지로 즉시 리셋 방지)
                    if alert.fall_start_time and (now - alert.fall_start_time) < 2.0:
                        pass  # 최소 유지 시간 미충족 → MONITORING 유지
                    else:
                        alert.state = AlertState.NORMAL
                        alert.fall_start_time = None

            elif alert.state == AlertState.WARNING:
                # WARNING 상태에서 회복: 최소 유지 시간 체크
                # track_id 변경이나 일시적 감지 중단으로 WARNING이 너무 빨리 풀리는 것 방지
                # DANGER threshold(1.5초) 이상 유지하여 에스컬레이션 기회 보장
                _min_warning_hold = max(self._warning_seconds + 1.0, 3.0)  # 최소 3초
                if alert.warning_time and (now - alert.warning_time) < _min_warning_hold:
                    pass  # 최소 WARNING 유지 시간 미충족 → 유지
                else:
                    alert.state = AlertState.NORMAL
                    alert.fall_start_time = None
                    alert.warning_time = None
                    alert.pre_impact_warned = False
                    alert.recovery_start_time = None
                    logger.info("WARNING 자동 해제: person=%s (회복 감지)", person_id)

            elif alert.state == AlertState.DANGER:
                # DANGER 상태에서 회복 → 일정 시간 후 자동 리셋
                # (fall_detector 쿨다운 3초 + 여기서 5초 = 총 ~8초 후 해제)
                if alert.recovery_start_time is None:
                    alert.recovery_start_time = now
                    logger.info("DANGER 회복 시작: person=%s (%.0f초 후 자동 해제)", person_id, self._DANGER_AUTO_RESET_SECONDS)
                elif now - alert.recovery_start_time >= self._DANGER_AUTO_RESET_SECONDS:
                    alert.state = AlertState.NORMAL
                    alert.fall_start_time = None
                    alert.warning_time = None
                    alert.danger_time = None
                    alert.pre_impact_warned = False
                    alert.recovery_start_time = None
                    logger.info("DANGER 자동 해제: person=%s (회복 후 자동 리셋)", person_id)

        # 글로벌 상태 업데이트 (가장 심각한 상태)
        self._update_global_state()

        changed = old_state != alert.state

        # person_id에서 camera_id 추출 (형식: "cam0_person_1" → "cam0")
        camera_id = person_id.rsplit("_person_", 1)[0] if "_person_" in person_id else "default"

        result = {
            "state": alert.state.value,
            "duration": fall_duration,
            "person_id": person_id,
            "changed": changed,
            "confidence": confidence,
            "camera_id": camera_id,
        }

        if changed:
            logger.info(
                "알림 상태 변경: person=%s, %s -> %s",
                person_id, old_state.value, alert.state.value,
            )
            self._notify_change(result)
            if alert.state in (AlertState.WARNING, AlertState.DANGER):
                self._notify_event(result)

        return result

    def acknowledge(self, person_id: str | None = None, acknowledged_by: str = "staff") -> bool:  # noqa: C901
        """알림 확인"""
        if person_id:
            alert = self._person_alerts.get(person_id)
            if alert and alert.state in (AlertState.WARNING, AlertState.DANGER):
                alert.state = AlertState.ACKNOWLEDGED
                alert.acknowledged_by = acknowledged_by
                self._update_global_state()
                self._notify_change({
                    "state": AlertState.ACKNOWLEDGED.value,
                    "person_id": person_id,
                    "changed": True,
                    "acknowledged_by": acknowledged_by,
                })
                return True
            return False
        else:
            # 모든 활성 알림 확인
            any_acknowledged = False
            for alert in self._person_alerts.values():
                if alert.state in (AlertState.WARNING, AlertState.DANGER):
                    alert.state = AlertState.ACKNOWLEDGED
                    alert.acknowledged_by = acknowledged_by
                    any_acknowledged = True
            if any_acknowledged:
                self._update_global_state()
                self._notify_change({
                    "state": AlertState.ACKNOWLEDGED.value,
                    "person_id": "all",
                    "changed": True,
                    "acknowledged_by": acknowledged_by,
                })
            return any_acknowledged

    def _get_or_create(self, person_id: str) -> PersonAlert:
        if person_id not in self._person_alerts:
            self._person_alerts[person_id] = PersonAlert(person_id=person_id)
        return self._person_alerts[person_id]

    def _update_global_state(self):
        """가장 심각한 개인 상태를 글로벌 상태로"""
        severity = {
            AlertState.NORMAL: 0,
            AlertState.ACKNOWLEDGED: 1,
            AlertState.MONITORING: 2,
            AlertState.WARNING: 3,
            AlertState.DANGER: 4,
        }
        max_severity = 0
        for alert in self._person_alerts.values():
            s = severity.get(alert.state, 0)
            if s > max_severity:
                max_severity = s

        for state, sev in severity.items():
            if sev == max_severity:
                self._global_state = state
                break

    def _notify_change(self, data: dict):
        for cb in self._callbacks:
            try:
                if asyncio.iscoroutinefunction(cb):
                    task = asyncio.create_task(cb(data))
                    task.add_done_callback(self._task_done_callback)
                else:
                    cb(data)
            except Exception as e:
                logger.error("알림 콜백 실패: %s", e, exc_info=True)

    def _notify_event(self, data: dict):
        for cb in self._event_callbacks:
            try:
                if asyncio.iscoroutinefunction(cb):
                    task = asyncio.create_task(cb(data))
                    task.add_done_callback(self._task_done_callback)
                else:
                    cb(data)
            except Exception as e:
                logger.error("이벤트 콜백 실패: %s", e, exc_info=True)

    @staticmethod
    def _task_done_callback(task: asyncio.Task):
        if task.cancelled():
            return
        exc = task.exception()
        if exc:
            logger.error("비동기 콜백 실패: %s", exc)

    def update_walking_aid_alert(self, person_id: str, aid_state) -> dict:
        """보행도구 분실 정보 알림 (알림 레벨 변경 없음).

        - 보행도구 분실은 프론트엔드 배지/정보로만 표시
        - 알림 상태(MONITORING/WARNING/DANGER)를 변경하지 않음 (알람 피로 방지)
        - WebSocket alert_update 메시지로 프론트엔드에 통지만 수행

        Args:
            person_id: 인물 ID
            aid_state: WalkingAidState 객체

        Returns:
            {"state": str, "person_id": str, "changed": bool, "walking_aid_missing": bool}
        """
        alert = self._get_or_create(person_id)
        is_missing = aid_state.established and aid_state.is_missing
        was_missing = alert.walking_aid_warned

        alert.walking_aid_warned = is_missing

        # 분실 상태 변경 시에만 로그 + 프론트엔드 통지
        changed = is_missing != was_missing
        if changed and is_missing:
            logger.info(
                "보행도구 분실 감지 (정보): person=%s, aid_type=%s",
                person_id, aid_state.aid_type,
            )

        result = {
            "state": alert.state.value,
            "person_id": person_id,
            "changed": changed,
            "walking_aid_missing": is_missing,
        }

        if changed:
            self._notify_change(result)

        return result

    def get_state_for_frontend(self) -> str:
        """프론트엔드 AlertLevel에 맞는 문자열 반환
        MONITORING은 내부 추적용 → 프론트엔드에는 "safe" 표시
        WARNING(1.5초 지속) 이상만 "warning"으로 표시하여 알람 피로 방지
        """
        state = self._global_state
        if state == AlertState.DANGER:
            return "danger"
        elif state == AlertState.WARNING:
            return "warning"
        return "safe"


# 싱글턴
alert_manager = AlertManager()
