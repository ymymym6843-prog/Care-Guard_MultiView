"""
푸시 알림 API 라우터

VAPID 공개 키 조회 및 구독 관리 엔드포인트
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import require_auth
from app.core.database import get_db
from app.models.push_subscription import PushSubscription
from app.services.push_service import push_service

router = APIRouter()


class SubscribeRequest(BaseModel):
    endpoint: str
    p256dh_key: str
    auth_key: str


class UnsubscribeRequest(BaseModel):
    endpoint: str


@router.get("/vapid-key")
async def get_vapid_key():
    """VAPID 공개 키 조회"""
    if not push_service.enabled:
        raise HTTPException(status_code=404, detail="Push 서비스가 비활성화되어 있습니다")
    return {"public_key": push_service.vapid_public_key}


@router.post("/subscribe")
async def subscribe(
    req: SubscribeRequest,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_auth),
):
    """푸시 구독 등록"""
    if not push_service.enabled:
        raise HTTPException(status_code=404, detail="Push 서비스가 비활성화되어 있습니다")

    # 기존 구독 확인
    result = await db.execute(
        select(PushSubscription).where(PushSubscription.endpoint == req.endpoint)
    )
    existing = result.scalar_one_or_none()

    if existing:
        existing.p256dh_key = req.p256dh_key  # type: ignore[assignment]
        existing.auth_key = req.auth_key  # type: ignore[assignment]
        existing.is_active = True  # type: ignore[assignment]
        existing.user_id = str(user.id)  # type: ignore[assignment]
    else:
        sub = PushSubscription(
            endpoint=req.endpoint,
            p256dh_key=req.p256dh_key,
            auth_key=req.auth_key,
            user_id=str(user.id),
            is_active=True,
        )
        db.add(sub)

    await db.commit()
    return {"status": "subscribed"}


@router.post("/unsubscribe")
async def unsubscribe(
    req: UnsubscribeRequest,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_auth),
):
    """구독 해제"""
    await db.execute(
        delete(PushSubscription).where(PushSubscription.endpoint == req.endpoint)
    )
    await db.commit()
    return {"status": "unsubscribed"}
