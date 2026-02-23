"""
Web Push 알림 서비스

VAPID 키가 설정되지 않으면 자동으로 비활성화됩니다.
"""

import asyncio
import json

from sqlalchemy import select, update

from app.config import settings
from app.core.database import async_session
from app.core.logging_config import get_logger
from app.models.push_subscription import PushSubscription

logger = get_logger("app.services.push")


class PushService:
    """Web Push 알림 서비스"""

    def __init__(self):
        self._enabled = bool(
            settings.VAPID_PRIVATE_KEY
            and settings.VAPID_PUBLIC_KEY
            and settings.VAPID_CLAIMS_EMAIL
        )
        if self._enabled:
            logger.info("Push 서비스 활성화됨")
        else:
            logger.info("Push 서비스 비활성화 (VAPID 키 미설정)")

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def vapid_public_key(self) -> str:
        return settings.VAPID_PUBLIC_KEY

    async def send_to_all(self, title: str, body: str, url: str = "/") -> int:
        """모든 활성 구독에 푸시 전송

        Returns:
            성공적으로 전송된 구독 수
        """
        if not self._enabled:
            return 0

        try:
            from pywebpush import webpush, WebPushException
        except ImportError:
            logger.warning("pywebpush 패키지 미설치")
            return 0

        async with async_session() as session:
            result = await session.execute(
                select(PushSubscription).where(PushSubscription.is_active == True)
            )
            subscriptions = result.scalars().all()

        if not subscriptions:
            return 0

        payload = json.dumps({
            "title": title,
            "body": body,
            "url": url,
            "icon": "/icon-192x192.png",
            "badge": "/icon-192x192.png",
        })

        vapid_claims = {
            "sub": f"mailto:{settings.VAPID_CLAIMS_EMAIL}",
        }

        sent = 0
        deactivate_ids = []

        for sub in subscriptions:
            subscription_info = {
                "endpoint": sub.endpoint,
                "keys": {
                    "p256dh": sub.p256dh_key,
                    "auth": sub.auth_key,
                },
            }

            try:
                await asyncio.to_thread(
                    webpush,
                    subscription_info=subscription_info,
                    data=payload,
                    vapid_private_key=settings.VAPID_PRIVATE_KEY,
                    vapid_claims=vapid_claims,  # type: ignore[arg-type]
                )
                sent += 1
            except WebPushException as e:
                status_code = getattr(e, "response", None)
                if status_code and hasattr(status_code, "status_code"):
                    code = status_code.status_code
                    if code in (404, 410):
                        deactivate_ids.append(sub.id)
                        logger.info("만료된 구독 비활성화: %s", sub.endpoint[:50])
                    else:
                        logger.warning("푸시 전송 실패 (HTTP %s): %s", code, sub.endpoint[:50])
                else:
                    logger.warning("푸시 전송 실패: %s", str(e)[:100])
            except Exception as e:
                logger.warning("푸시 전송 오류: %s", str(e)[:100])

        # 만료된 구독 비활성화
        if deactivate_ids:
            async with async_session() as session:
                await session.execute(
                    update(PushSubscription)
                    .where(PushSubscription.id.in_(deactivate_ids))
                    .values(is_active=False)
                )
                await session.commit()

        logger.info("푸시 전송 완료: %d/%d 성공", sent, len(subscriptions))
        return sent

    async def on_alert_change(self, data: dict):
        """알림 상태 변경 콜백

        danger/warning 상태에서 푸시 알림을 전송합니다.
        alert_manager._notify_change()에서 dict를 전달합니다.
        """
        if not self._enabled:
            return

        alert_level = data.get("state", "")
        person_id = data.get("person_id", "")

        if alert_level == "danger":
            await self.send_to_all(
                title="낙상 감지!",
                body=f"낙상이 감지되었습니다 (ID: {person_id}). 즉시 확인해주세요.",
                url="/",
            )
        elif alert_level == "warning":
            await self.send_to_all(
                title="주의: 이상 자세 감지",
                body=f"이상 자세가 감지되었습니다 (ID: {person_id}). 모니터링을 확인해주세요.",
                url="/",
            )


# 싱글톤 인스턴스
push_service = PushService()
