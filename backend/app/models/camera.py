"""
카메라 모델
"""

from sqlalchemy import Integer, String, Boolean
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Camera(Base):
    __tablename__ = "cameras"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    source: Mapped[str] = mapped_column(String(255), default="0")  # 카메라 인덱스 또는 RTSP URL
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    location: Mapped[str] = mapped_column(String(200), default="대기실")
    # RTSP 확장 필드
    rtsp_username: Mapped[str] = mapped_column(String(100), default="", server_default="")
    rtsp_password: Mapped[str] = mapped_column(String(255), default="", server_default="")
    stream_protocol: Mapped[str] = mapped_column(String(20), default="mjpeg", server_default="mjpeg")  # mjpeg | webrtc
