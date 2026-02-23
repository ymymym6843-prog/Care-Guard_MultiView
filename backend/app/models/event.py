"""
낙상 감지 이벤트 모델
"""

from datetime import datetime, timezone

from sqlalchemy import Integer, String, Float, Boolean, DateTime
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Event(Base):
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)
    alert_level: Mapped[str] = mapped_column(String(20), nullable=False)  # warning, danger
    duration: Mapped[float] = mapped_column(Float, default=0.0)  # 지속 시간 (초)
    camera_id: Mapped[str] = mapped_column(String(50), default="default")
    snapshot_path: Mapped[str | None] = mapped_column(String(255), nullable=True)
    person_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    acknowledged: Mapped[bool] = mapped_column(Boolean, default=False)
    acknowledged_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    room_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
