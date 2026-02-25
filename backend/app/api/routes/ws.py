"""
WebSocket 엔드포인트

실시간 포즈 데이터 및 알림 메시지를 스트리밍합니다.
메타데이터 전용 (비디오는 MJPEG 별도 엔드포인트)

모니터링 파이프라인은 앱 lifespan에서 단일 인스턴스로 실행됩니다.
이 모듈은 순수 WebSocket I/O (클라이언트 메시지 수신)만 담당합니다.
"""

import json
from datetime import datetime, timezone

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy import select, desc

from app.core.auth import decode_token
from app.core.connection_manager import connection_manager
from app.core.database import async_session
from app.core.logging_config import get_logger
from app.models.event import Event
from app.services.alert_manager import alert_manager

logger = get_logger("app.api.ws")

router = APIRouter()


@router.websocket("/monitoring")
async def monitoring_websocket(websocket: WebSocket):
    """모니터링 WebSocket 엔드포인트 (쿠키 우선, query param 폴백)"""
    # 1. 쿠키에서 토큰 추출
    token = websocket.cookies.get("access_token")

    # 2. query parameter 폴백
    if not token:
        token = websocket.query_params.get("token", "")

    payload = decode_token(token) if token else None
    if not token or not payload or payload.get("type") != "access":
        await websocket.accept()
        await websocket.close(code=4001, reason="인증이 필요합니다")
        logger.warning("WebSocket 인증 실패: 유효하지 않은 토큰")
        return

    # 토큰에서 사용자명 추출
    username = payload.get("sub", "unknown")

    await connection_manager.connect(websocket)

    try:
        await _client_message_loop(websocket, username)
    except WebSocketDisconnect:
        logger.info("WebSocket 클라이언트 연결 해제")
    except Exception as e:
        logger.error("WebSocket 오류: %s", e)
    finally:
        connection_manager.disconnect(websocket)


async def _client_message_loop(websocket: WebSocket, username: str = "unknown"):
    """클라이언트 메시지 수신 (acknowledge 등)"""
    while True:
        try:
            data = await websocket.receive_text()
            msg = json.loads(data)

            if msg.get("type") == "acknowledge":
                person_id = msg.get("person_id")
                alert_manager.acknowledge(person_id=person_id)
                await connection_manager.broadcast_alert_update({
                    "alert_level": "safe",
                    "state": "acknowledged",
                    "duration": 0,
                    "person_id": person_id or "all",
                })

                # DB 이벤트도 acknowledged 업데이트 (통계 확인률/응답시간 반영)
                await _acknowledge_latest_event(person_id, username)

                logger.info("알림 확인: person=%s, user=%s", person_id or "all", username)

            elif msg.get("type") == "pong":
                pass  # 하트비트 응답

            elif msg.get("type") == "settings_update":
                pass  # 실시간 설정 변경

        except WebSocketDisconnect:
            break
        except Exception as e:
            logger.warning("클라이언트 메시지 처리 오류: %s", e)
            break


async def _acknowledge_latest_event(person_id: str | None, username: str):
    """최신 미확인 이벤트를 DB에서 찾아 acknowledged 업데이트"""
    try:
        async with async_session() as session:
            query = (
                select(Event)
                .where(Event.acknowledged.is_(False))
                .where(Event.alert_level.in_(["warning", "danger"]))
            )
            if person_id:
                query = query.where(Event.person_id == person_id)
            query = query.order_by(desc(Event.timestamp)).limit(1)

            result = await session.execute(query)
            event = result.scalar_one_or_none()

            if event:
                event.acknowledged = True
                event.acknowledged_by = username
                event.acknowledged_at = datetime.now(timezone.utc)
                await session.commit()
                logger.info(
                    "이벤트 DB 확인 완료: event_id=%d, user=%s",
                    event.id, username,
                )
    except Exception as e:
        logger.error("이벤트 DB 확인 실패: %s", e)
