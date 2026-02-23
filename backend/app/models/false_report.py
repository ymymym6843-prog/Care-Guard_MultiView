"""
오탐지/미탐지 보고 모델
"""

from datetime import datetime, timezone

from sqlalchemy import Integer, String, Text, DateTime
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class FalseReport(Base):
    __tablename__ = "false_reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    report_type: Mapped[str] = mapped_column(String(20), nullable=False)  # false_positive, false_negative
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    image_path: Mapped[str | None] = mapped_column(String(255), nullable=True)
    event_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    uploaded_by: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True
    )
