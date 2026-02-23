"""
감사 로그 모델 (INSERT-only 설계)

모든 중요 이벤트를 기록합니다. 수정/삭제 불가.
"""

from datetime import datetime, timezone

from sqlalchemy import Integer, String, Text, DateTime, JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True,
    )
    actor: Mapped[str] = mapped_column(String(100), nullable=False)  # 사용자명 또는 "system"
    action: Mapped[str] = mapped_column(String(50), nullable=False)  # login, logout, register, acknowledge, settings_change
    resource: Mapped[str] = mapped_column(String(100), nullable=False, default="")  # 대상 리소스
    detail: Mapped[str] = mapped_column(Text, nullable=True)  # 추가 설명
    ip_address: Mapped[str] = mapped_column(String(45), nullable=True)  # IPv4/IPv6
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # 구조화된 추가 데이터
