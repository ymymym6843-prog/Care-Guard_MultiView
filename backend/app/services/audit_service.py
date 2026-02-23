"""
감사 로깅 서비스

보안 관련 이벤트를 audit_logs 테이블에 INSERT-only로 기록합니다.
"""

from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging_config import get_logger
from app.models.audit_log import AuditLog

logger = get_logger("app.services.audit")


async def log_audit(
    db: AsyncSession,
    *,
    actor: str,
    action: str,
    resource: str = "",
    detail: str | None = None,
    ip_address: str | None = None,
    metadata: dict | None = None,
) -> None:
    """감사 로그 기록

    Args:
        db: 데이터베이스 세션
        actor: 행위자 (사용자명 또는 "system")
        action: 행위 유형 (login, logout, register, acknowledge, settings_change 등)
        resource: 대상 리소스
        detail: 추가 설명
        ip_address: 요청 IP
        metadata: 구조화된 추가 데이터
    """
    try:
        entry = AuditLog(
            timestamp=datetime.now(timezone.utc),
            actor=actor,
            action=action,
            resource=resource,
            detail=detail,
            ip_address=ip_address,
            metadata_json=metadata,
        )
        db.add(entry)
        await db.commit()
    except Exception as e:
        logger.error("감사 로그 기록 실패: %s", e)
        # 감사 로그 실패가 비즈니스 로직에 영향을 주지 않도록 예외 무시
        await db.rollback()
