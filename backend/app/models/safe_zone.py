"""
Safe-Zone 모델

카메라별 안전 영역/위험 영역을 폴리곤 좌표로 정의합니다.
"""

from datetime import datetime, timezone

from sqlalchemy import Integer, String, Boolean, DateTime, JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class SafeZone(Base):
    __tablename__ = "safe_zones"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    camera_id: Mapped[str] = mapped_column(String(50), nullable=False, default="default")
    zone_type: Mapped[str] = mapped_column(String(20), nullable=False, default="safe")  # safe | danger | exclusion
    # 폴리곤 좌표: [{x: float, y: float}, ...] (normalized 0~1)
    polygon: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
