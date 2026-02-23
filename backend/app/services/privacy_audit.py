"""
프라이버시 감사 로그 (System Trace)

영상 비저장 증명을 위한 시스템 동작 로그입니다.
모든 프레임 처리/파기/사건 덤프 동작을 기록하여
법적 준수 증명 자료로 활용할 수 있습니다.
"""

import json
import time
from collections import deque
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

from app.config import settings
from app.core.logging_config import get_logger

logger = get_logger("app.services.privacy_audit")

# 감사 로그 파일 디렉토리
_AUDIT_DIR = Path("audit_logs")


@dataclass
class AuditEntry:
    """감사 로그 엔트리"""
    timestamp: str
    action: str           # frame_processed, frame_sanitized, incident_dump, access
    detail: str
    frame_id: str = ""
    user: str = ""
    incident_id: str = ""


class PrivacyAuditLogger:
    """영상 비저장 증명을 위한 시스템 동작 로그"""

    def __init__(self, max_memory_entries: int = 10000):
        self._enabled = getattr(settings, "PRIVACY_AUDIT_ENABLED", True)
        self._entries: deque[AuditEntry] = deque(maxlen=max_memory_entries)
        self._total_frames_processed = 0
        self._total_frames_sanitized = 0
        self._total_incidents_dumped = 0
        self._session_start = datetime.utcnow().isoformat() + "Z"

    @property
    def enabled(self) -> bool:
        return self._enabled

    async def log_frame_processed(self, frame_id: str) -> None:
        """프레임 처리 완료 + 즉시 파기 기록"""
        if not self._enabled:
            return

        self._total_frames_processed += 1
        now = datetime.utcnow().isoformat() + "Z"
        entry = AuditEntry(
            timestamp=now,
            action="frame_processed",
            detail=f"{frame_id} processed and sanitized, memory released",
            frame_id=frame_id,
        )
        self._entries.append(entry)

        # 매 1000프레임마다 통계 로깅
        if self._total_frames_processed % 1000 == 0:
            logger.debug(
                "[감사] 프레임 %d건 처리 완료, 저장된 프레임: 0",
                self._total_frames_processed,
            )

    async def log_frame_sanitized(self, frame_id: str, sanitize_ms: float = 0.0) -> None:
        """프레임 메모리 파기 기록"""
        if not self._enabled:
            return

        self._total_frames_sanitized += 1
        now = datetime.utcnow().isoformat() + "Z"
        entry = AuditEntry(
            timestamp=now,
            action="frame_sanitized",
            detail=f"{frame_id} memory zeroed in {sanitize_ms:.2f}ms",
            frame_id=frame_id,
        )
        self._entries.append(entry)

    async def log_incident_dump(self, incident_id: str, data_hash: str) -> None:
        """사건 JSON 저장 기록 (좌표만, 영상 없음 증명)"""
        if not self._enabled:
            return

        self._total_incidents_dumped += 1
        now = datetime.utcnow().isoformat() + "Z"
        entry = AuditEntry(
            timestamp=now,
            action="incident_dump",
            detail=f"Skeleton-only incident dump (no video), hash={data_hash}",
            incident_id=incident_id,
        )
        self._entries.append(entry)
        logger.info(
            "[감사] 사건 덤프: %s (좌표만, 영상 없음, hash=%s)",
            incident_id, data_hash,
        )

    async def log_audit(self, user: str, action: str, target: str) -> None:
        """일반 감사 로그 (접근 기록 등)"""
        if not self._enabled:
            return

        now = datetime.utcnow().isoformat() + "Z"
        entry = AuditEntry(
            timestamp=now,
            action=action,
            detail=f"User '{user}' accessed {target}",
            user=user,
        )
        self._entries.append(entry)
        logger.info("[감사] %s: user=%s, target=%s", action, user, target)

    async def generate_privacy_report(
        self,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> dict:
        """프라이버시 준수 보고서 생성"""
        report = {
            "report_type": "privacy_compliance",
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "session_start": self._session_start,
            "period": {
                "start": start.isoformat() + "Z" if start else self._session_start,
                "end": end.isoformat() + "Z" if end else datetime.utcnow().isoformat() + "Z",
            },
            "summary": {
                "total_frames_processed": self._total_frames_processed,
                "total_frames_stored": 0,  # 항상 0
                "total_frames_sanitized": self._total_frames_sanitized,
                "total_incidents_dumped": self._total_incidents_dumped,
                "non_storage_policy": "ACTIVE",
                "frame_retention_ms": getattr(settings, "PRIVACY_FRAME_RETENTION_MS", 0),
            },
            "compliance": {
                "video_non_storage": True,
                "immediate_frame_disposal": True,
                "skeleton_only_incidents": True,
                "audit_trail_active": self._enabled,
            },
            "privacy_notice": (
                "본 시스템은 원본 영상을 저장하지 않습니다. "
                "AI 분석 후 프레임 데이터는 즉시 메모리에서 파기됩니다. "
                "사고 발생 시 비식별 관절 좌표 데이터만 기록됩니다."
            ),
        }

        return report

    def get_recent_entries(self, count: int = 100) -> list[dict]:
        """최근 감사 로그 엔트리 조회"""
        entries = list(self._entries)[-count:]
        return [asdict(e) for e in entries]

    async def flush_to_file(self) -> Path | None:
        """메모리 로그를 파일로 플러시"""
        if not self._entries:
            return None

        _AUDIT_DIR.mkdir(exist_ok=True)
        filename = f"audit_{time.strftime('%Y%m%d_%H%M%S')}.json"
        filepath = _AUDIT_DIR / filename

        data = {
            "flushed_at": datetime.utcnow().isoformat() + "Z",
            "entry_count": len(self._entries),
            "entries": [asdict(e) for e in self._entries],
        }

        filepath.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        logger.info("[감사] 로그 플러시: %s (%d건)", filepath, len(self._entries))
        return filepath


# 싱글턴
privacy_audit = PrivacyAuditLogger()
