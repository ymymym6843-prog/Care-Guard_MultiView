"""
사용자 모델 (의료진 인증)
"""

from datetime import datetime, timezone

from sqlalchemy import Integer, String, Boolean, DateTime
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(100), default="")
    role: Mapped[str] = mapped_column(String(20), default="staff")  # admin, staff
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    # 개인정보 수집 동의 (GDPR/개인정보보호법 준수)
    privacy_consented: Mapped[bool] = mapped_column(Boolean, default=False)
    privacy_consented_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    privacy_consent_version: Mapped[str] = mapped_column(String(20), default="")
