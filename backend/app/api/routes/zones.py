"""
Safe-Zone CRUD API
"""

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.auth import require_auth
from app.models.user import User
from app.models.safe_zone import SafeZone
from app.services.zone_checker import zone_checker

router = APIRouter()


class PolygonPoint(BaseModel):
    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)


class ZoneCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    camera_id: str = Field(default="default", max_length=50)
    zone_type: Literal["safe", "danger", "exclusion"] = "safe"
    polygon: list[PolygonPoint] = Field(min_length=3)  # 최소 3개 꼭짓점
    is_active: bool = True


class ZoneUpdateRequest(BaseModel):
    name: str | None = None
    zone_type: Literal["safe", "danger", "exclusion"] | None = None
    polygon: list[PolygonPoint] | None = None
    is_active: bool | None = None


@router.get("/")
async def list_zones(
    camera_id: str = "default",
    user: User = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    """카메라별 Safe-Zone 목록 조회"""
    result = await db.execute(
        select(SafeZone)
        .where(SafeZone.camera_id == camera_id)
        .order_by(SafeZone.created_at.desc())
    )
    zones = result.scalars().all()

    return [
        {
            "id": z.id,
            "name": z.name,
            "camera_id": z.camera_id,
            "zone_type": z.zone_type,
            "polygon": z.polygon,
            "is_active": z.is_active,
        }
        for z in zones
    ]


@router.post("/", status_code=201)
async def create_zone(
    req: ZoneCreateRequest,
    user: User = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    """Safe-Zone 생성 (관리자 전용)"""
    if user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="관리자만 Safe-Zone을 생성할 수 있습니다",
        )

    zone = SafeZone(
        name=req.name,
        camera_id=req.camera_id,
        zone_type=req.zone_type,
        polygon=[{"x": p.x, "y": p.y} for p in req.polygon],
        is_active=req.is_active,
    )
    db.add(zone)
    await db.commit()
    await db.refresh(zone)
    zone_checker.invalidate_cache()

    return {
        "id": zone.id,
        "name": zone.name,
        "camera_id": zone.camera_id,
        "zone_type": zone.zone_type,
        "polygon": zone.polygon,
    }


@router.put("/{zone_id}")
async def update_zone(
    zone_id: int,
    req: ZoneUpdateRequest,
    user: User = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    """Safe-Zone 수정 (관리자 전용)"""
    if user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="관리자만 Safe-Zone을 수정할 수 있습니다",
        )

    result = await db.execute(select(SafeZone).where(SafeZone.id == zone_id))
    zone = result.scalar_one_or_none()

    if not zone:
        raise HTTPException(status_code=404, detail="Safe-Zone을 찾을 수 없습니다")

    if req.name is not None:
        zone.name = req.name
    if req.zone_type is not None:
        zone.zone_type = req.zone_type
    if req.polygon is not None:
        zone.polygon = [{"x": p.x, "y": p.y} for p in req.polygon]
    if req.is_active is not None:
        zone.is_active = req.is_active

    await db.commit()
    zone_checker.invalidate_cache()

    return {"status": "updated", "id": zone.id}


@router.delete("/{zone_id}")
async def delete_zone(
    zone_id: int,
    user: User = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    """Safe-Zone 삭제 (관리자 전용)"""
    if user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="관리자만 Safe-Zone을 삭제할 수 있습니다",
        )

    result = await db.execute(select(SafeZone).where(SafeZone.id == zone_id))
    zone = result.scalar_one_or_none()

    if not zone:
        raise HTTPException(status_code=404, detail="Safe-Zone을 찾을 수 없습니다")

    await db.delete(zone)
    await db.commit()
    zone_checker.invalidate_cache()

    return {"status": "deleted", "id": zone_id}
