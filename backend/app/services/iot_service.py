"""
IoT 디바이스 연동 서비스

외부 IoT 디바이스(경광등, 스마트 알림장치 등)에 Webhook으로
알림 상태를 전달합니다. IOT_WEBHOOK_URL 설정 시에만 활성화됩니다.
"""

import hashlib
import hmac
import json
import time

import httpx

from app.core.logging_config import get_logger

logger = get_logger("app.services.iot_service")


class IoTService:
    """IoT Webhook 기반 디바이스 알림 서비스"""

    def __init__(self):
        self._client: httpx.AsyncClient | None = None
        self._enabled = False
        self._webhook_url: str = ""
        self._webhook_secret: str = ""

    def configure(self, webhook_url: str, webhook_secret: str = ""):
        """IoT Webhook URL 설정"""
        if not webhook_url:
            logger.info("IoT 서비스 비활성화 (IOT_WEBHOOK_URL 미설정)")
            return

        self._client = httpx.AsyncClient(
            timeout=5.0,
            limits=httpx.Limits(max_connections=3, max_keepalive_connections=1),
        )
        self._enabled = True
        self._webhook_url = webhook_url
        self._webhook_secret = webhook_secret
        logger.info("IoT 서비스 활성화: %s", webhook_url)

    @property
    def enabled(self) -> bool:
        return self._enabled

    async def shutdown(self):
        """클라이언트 리소스 정리"""
        if self._client:
            await self._client.aclose()
            self._client = None
            logger.info("IoT 클라이언트 종료됨")

    def _sign_payload(self, payload: str) -> str:
        """HMAC-SHA256으로 페이로드 서명"""
        if not self._webhook_secret:
            return ""
        return hmac.new(
            self._webhook_secret.encode(),
            payload.encode(),
            hashlib.sha256,
        ).hexdigest()

    async def notify(self, alert_state: str, person_id: str, confidence: float = 0.0):
        """
        IoT 디바이스에 알림 상태 전송

        Args:
            alert_state: "warning" | "danger" | "acknowledged" | "normal"
            person_id: 감지된 인물 ID
            confidence: 감지 신뢰도
        """
        if not self._enabled or not self._client:
            return

        payload = {
            "event": "fall_alert",
            "state": alert_state,
            "person_id": person_id,
            "confidence": confidence,
            "timestamp": int(time.time()),
            "source": "sentio",
        }

        # 경광등 색상 매핑
        color_map = {
            "warning": "yellow",
            "danger": "red",
            "acknowledged": "blue",
            "normal": "off",
        }
        payload["color"] = color_map.get(alert_state, "off")
        payload["siren"] = alert_state == "danger"

        body = json.dumps(payload)
        headers = {"Content-Type": "application/json"}

        signature = self._sign_payload(body)
        if signature:
            headers["X-Webhook-Signature"] = f"sha256={signature}"

        try:
            response = await self._client.post(
                self._webhook_url, content=body, headers=headers,
            )
            if response.status_code < 300:
                logger.debug("IoT 알림 전송 성공: state=%s, person=%s", alert_state, person_id)
            else:
                logger.warning(
                    "IoT 알림 전송 실패: HTTP %d, %s",
                    response.status_code, response.text[:200],
                )
        except Exception as e:
            logger.warning("IoT Webhook 호출 실패: %s", e)

    async def on_alert_change(self, data: dict):
        """AlertManager 콜백 - 알림 상태 변경 시 IoT 디바이스 알림"""
        state = data.get("state", "")
        if state in ("warning", "danger", "acknowledged", "normal"):
            await self.notify(
                alert_state=state,
                person_id=data.get("person_id", ""),
                confidence=data.get("confidence", 0.0),
            )


# 싱글턴
iot_service = IoTService()
