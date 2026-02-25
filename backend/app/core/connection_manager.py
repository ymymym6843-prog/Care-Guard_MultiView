"""
WebSocket 연결 관리자

클라이언트 연결 관리, 하트비트, 메시지 브로드캐스트를 담당합니다.
"""

import asyncio
import json
import time

from fastapi import WebSocket

from app.config import settings
from app.core.logging_config import get_logger

logger = get_logger("app.core.ws")


class ConnectionManager:
    # 연속 전송 실패 허용 횟수 (이 횟수 초과 시 연결 해제)
    _MAX_CONSECUTIVE_ERRORS = 3

    def __init__(self):
        self._connections: list[WebSocket] = []
        self._error_counts: dict[int, int] = {}  # ws id -> consecutive error count
        self._heartbeat_interval = settings.HEARTBEAT_INTERVAL
        self._last_metrics: dict | None = None
        self._last_broadcast_time: float = 0.0
        self._last_pose_broadcast_time: float = 0.0
        # 카메라별 브로드캐스트 스로틀
        self._last_cam_broadcast_time: dict[str, float] = {}
        self._last_cam_pose_time: dict[str, float] = {}

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self._connections.append(websocket)
        self._error_counts[id(websocket)] = 0
        logger.info("WebSocket 연결: 총 %d명", len(self._connections))
        try:
            await self._send_json(websocket, {
                "type": "connection_status",
                "data": {"status": "connected", "timestamp": time.time()},
            })
            # 캐시된 최신 메트릭 즉시 전송 (새 클라이언트가 빈 화면 보지 않도록)
            if self._last_metrics:
                await self._send_json(websocket, {
                    "type": "metrics_update",
                    "data": {**self._last_metrics, "timestamp": time.time()},
                })
        except Exception as e:
            logger.warning("초기 메시지 전송 실패: %s", e)

    def disconnect(self, websocket: WebSocket):
        if websocket in self._connections:
            self._connections.remove(websocket)
            self._error_counts.pop(id(websocket), None)
            logger.info("WebSocket 해제: 총 %d명", len(self._connections))

    @property
    def active_count(self) -> int:
        return len(self._connections)

    async def broadcast(self, message: dict):
        """모든 연결된 클라이언트에 메시지 병렬 브로드캐스트 (한 클라이언트 지연이 다른 클라이언트에 영향 없음)"""
        if not self._connections:
            return

        async def _send_to_one(ws: WebSocket):
            try:
                await asyncio.wait_for(self._send_json(ws, message), timeout=2.0)
                self._error_counts[id(ws)] = 0
            except Exception as exc:
                logger.warning("[BROADCAST-ERROR] type=%s, err=%s", type(exc).__name__, exc)
                ws_id = id(ws)
                count = self._error_counts.get(ws_id, 0) + 1
                self._error_counts[ws_id] = count
                if count >= self._MAX_CONSECUTIVE_ERRORS:
                    logger.warning("WebSocket 연속 %d회 전송 실패 → 연결 해제", count)
                    return ws  # 연결 해제 대상
            return None

        results = await asyncio.gather(
            *[_send_to_one(ws) for ws in list(self._connections)],
            return_exceptions=True,
        )

        for result in results:
            if isinstance(result, WebSocket):
                self.disconnect(result)

    async def broadcast_pose_data(self, poses: list[dict], fps: float, camera_id: str = "cam0"):
        """포즈 데이터 브로드캐스트 (카메라별 스로틀 적용, 고빈도)"""
        if not self._connections:
            return
        now = time.time()
        last_time = self._last_cam_pose_time.get(camera_id, 0.0)
        if now - last_time < settings.WS_POSE_BROADCAST_INTERVAL:
            return
        self._last_cam_pose_time[camera_id] = now
        self._last_pose_broadcast_time = now
        await self.broadcast({
            "type": "pose_data",
            "data": {
                "poses": poses,
                "fps": round(fps, 1),
                "camera_id": camera_id,
                "timestamp": now,
            },
        })

    async def broadcast_alert_update(self, alert_data: dict):
        """알림 상태 변경 브로드캐스트 (스로틀 미적용 - 즉시 전달)"""
        await self.broadcast({
            "type": "alert_update",
            "data": alert_data,
        })

    async def broadcast_metrics(self, metrics: dict):
        """메트릭 업데이트 브로드캐스트 (항상 캐시 저장, 카메라별 주파수 제한)"""
        self._last_metrics = metrics
        now = time.time()
        camera_id = metrics.get("camera_id", "cam0")
        last_time = self._last_cam_broadcast_time.get(camera_id, 0.0)
        if now - last_time < settings.WS_METRICS_BROADCAST_INTERVAL:
            return  # 스로틀: 메트릭은 낮은 빈도로 충분
        self._last_cam_broadcast_time[camera_id] = now
        self._last_broadcast_time = now
        await self.broadcast({
            "type": "metrics_update",
            "data": {**metrics, "timestamp": now},
        })

    async def _send_json(self, ws: WebSocket, data: dict):
        await ws.send_text(json.dumps(data, default=self._json_default))

    @staticmethod
    def _json_default(obj):
        """numpy 타입 등 JSON 직렬화 불가 객체를 Python 네이티브로 변환"""
        import numpy as np
        if isinstance(obj, (np.integer,)):
            return int(obj)
        if isinstance(obj, (np.floating,)):
            return float(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")

    async def heartbeat_loop(self):
        """하트비트 루프 - ping 전송 실패 시 에러 카운트 증가, 전송 성공만으로는 리셋하지 않음"""
        while True:
            await asyncio.sleep(self._heartbeat_interval)
            disconnected = []
            for ws in list(self._connections):
                try:
                    await asyncio.wait_for(
                        ws.send_text(json.dumps({"type": "ping"})),
                        timeout=5.0,
                    )
                    # 전송 성공 시 에러 카운트 감소 (즉시 리셋 대신 점진적 회복)
                    ws_id = id(ws)
                    if self._error_counts.get(ws_id, 0) > 0:
                        self._error_counts[ws_id] = max(0, self._error_counts[ws_id] - 1)
                except Exception:
                    ws_id = id(ws)
                    count = self._error_counts.get(ws_id, 0) + 1
                    self._error_counts[ws_id] = count
                    if count >= self._MAX_CONSECUTIVE_ERRORS:
                        disconnected.append(ws)
            for ws in disconnected:
                self.disconnect(ws)


# 싱글턴
connection_manager = ConnectionManager()
