"""
공간(Room) 모델

다중 공간 관리를 위한 Room 및 Room-Camera 매핑 모델입니다.
"""

from datetime import datetime, timezone

from sqlalchemy import Integer, String, Boolean, DateTime, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Room(Base):
    __tablename__ = "rooms"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class RoomCameraMapping(Base):
    __tablename__ = "room_camera_mappings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    room_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    camera_id: Mapped[str] = mapped_column(String(50), nullable=False)

    __table_args__ = (
        UniqueConstraint("room_id", "camera_id", name="uq_room_camera"),
    )
