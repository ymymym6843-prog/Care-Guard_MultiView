"""
이벤트 기록 서비스

알림 상태 변경 시 이벤트를 데이터베이스에 저장합니다.
통계 및 리포트 생성에 사용됩니다.
"""

from datetime import datetime, timezone

from sqlalchemy import select

from app.core.database import async_session
from app.core.logging_config import get_logger
from app.models.event import Event
from app.models.room import RoomCameraMapping

logger = get_logger("app.services.event_recorder")


class EventRecorder:
    """이벤트 DB 기록 서비스"""

    async def on_alert_change(self, data: dict):
        """알림 상태 변경 콜백

        warning 또는 danger 상태로 변경될 때 이벤트를 DB에 저장합니다.

        Args:
            data: {
                "state": "normal" | "monitoring" | "warning" | "danger",
                "person_id": str,
                "duration": float,
                "confidence": float,
                ...
            }
        """
        alert_level = data.get("state", "")

        # warning 또는 danger일 때만 저장
        if alert_level not in ("warning", "danger"):
            return

        try:
            async with async_session() as session:
                camera_id = data.get("camera_id", "default")

                # camera_id로 room_id 역매핑
                room_id = None
                mapping_result = await session.execute(
                    select(RoomCameraMapping.room_id)
                    .where(RoomCameraMapping.camera_id == camera_id)
                    .limit(1)
                )
                row = mapping_result.first()
                if row:
                    room_id = row[0]

                event = Event(
                    timestamp=datetime.now(timezone.utc),
                    alert_level=alert_level,
                    duration=data.get("duration", 0.0),
                    camera_id=camera_id,
                    person_id=data.get("person_id", ""),
                    confidence=data.get("confidence", 0.0),
                    snapshot_path=data.get("snapshot_path"),
                    room_id=room_id,
                )
                session.add(event)
                await session.commit()
                logger.info(
                    "이벤트 저장: level=%s, person=%s, confidence=%.2f",
                    alert_level,
                    data.get("person_id"),
                    data.get("confidence", 0.0),
                )
        except Exception as e:
            logger.error("이벤트 저장 실패: %s", e)


# 싱글톤 인스턴스
event_recorder = EventRecorder()
