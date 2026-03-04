"""
공간(Room) API 라우트

공간 CRUD 및 카메라 매핑 관리 엔드포인트입니다.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select, func, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import require_auth, require_admin
from app.core.database import get_db
from app.models.room import Room, RoomCameraMapping

router = APIRouter()


class RoomCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: str = Field("", max_length=500)


class RoomUpdateRequest(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=100)
    description: str | None = Field(None, max_length=500)
    is_active: bool | None = None


class CameraAssignRequest(BaseModel):
    camera_ids: list[str] = Field(..., description="배정할 카메라 ID 목록")


def _room_to_dict(room: Room, camera_count: int = 0) -> dict:
    return {
        "id": room.id,
        "name": room.name,
        "description": room.description,
        "is_active": room.is_active,
        "camera_count": camera_count,
        "created_at": room.created_at.isoformat() if room.created_at else None,
    }


@router.get("")
async def list_rooms(
    is_active: bool | None = Query(None),
    db: AsyncSession = Depends(get_db),
    _user=Depends(require_auth),
):
    """공간 목록 조회 (카메라 수 포함)"""
    query = select(Room).order_by(Room.id)
    if is_active is not None:
        query = query.where(Room.is_active == is_active)

    result = await db.execute(query)
    rooms = result.scalars().all()

    # 각 공간의 카메라 수 조회
    items = []
    for room in rooms:
        count_result = await db.execute(
            select(func.count()).select_from(RoomCameraMapping)
            .where(RoomCameraMapping.room_id == room.id)
        )
        camera_count = count_result.scalar() or 0
        items.append(_room_to_dict(room, camera_count))

    return {"items": items, "total": len(items)}


@router.post("", status_code=201)
async def create_room(
    req: RoomCreateRequest,
    db: AsyncSession = Depends(get_db),
    _user=Depends(require_admin),
):
    """공간 생성 (관리자 전용)"""
    room = Room(name=req.name, description=req.description)
    db.add(room)
    await db.commit()
    await db.refresh(room)
    return _room_to_dict(room)


@router.patch("/{room_id}")
async def update_room(
    room_id: int,
    req: RoomUpdateRequest,
    db: AsyncSession = Depends(get_db),
    _user=Depends(require_admin),
):
    """공간 수정 (관리자 전용)"""
    result = await db.execute(select(Room).where(Room.id == room_id))
    room = result.scalar_one_or_none()
    if not room:
        raise HTTPException(404, "공간을 찾을 수 없습니다")

    if req.name is not None:
        room.name = req.name
    if req.description is not None:
        room.description = req.description
    if req.is_active is not None:
        room.is_active = req.is_active

    await db.commit()
    await db.refresh(room)
    return _room_to_dict(room)


@router.delete("/{room_id}")
async def delete_room(
    room_id: int,
    db: AsyncSession = Depends(get_db),
    _user=Depends(require_admin),
):
    """공간 삭제 (관리자 전용, 매핑도 삭제)"""
    result = await db.execute(select(Room).where(Room.id == room_id))
    room = result.scalar_one_or_none()
    if not room:
        raise HTTPException(404, "공간을 찾을 수 없습니다")

    # 매핑 삭제
    await db.execute(
        delete(RoomCameraMapping).where(RoomCameraMapping.room_id == room_id)
    )
    await db.delete(room)
    await db.commit()
    return {"success": True, "room_id": room_id}


@router.get("/{room_id}/cameras")
async def get_room_cameras(
    room_id: int,
    db: AsyncSession = Depends(get_db),
    _user=Depends(require_auth),
):
    """공간에 배정된 카메라 목록"""
    result = await db.execute(select(Room).where(Room.id == room_id))
    room = result.scalar_one_or_none()
    if not room:
        raise HTTPException(404, "공간을 찾을 수 없습니다")

    mapping_result = await db.execute(
        select(RoomCameraMapping.camera_id)
        .where(RoomCameraMapping.room_id == room_id)
    )
    camera_ids = [row[0] for row in mapping_result.all()]
    return {"room_id": room_id, "camera_ids": camera_ids}


@router.put("/{room_id}/cameras")
async def assign_cameras(
    room_id: int,
    req: CameraAssignRequest,
    db: AsyncSession = Depends(get_db),
    _user=Depends(require_admin),
):
    """카메라 배정 (전체 교체, 관리자 전용)"""
    result = await db.execute(select(Room).where(Room.id == room_id))
    room = result.scalar_one_or_none()
    if not room:
        raise HTTPException(404, "공간을 찾을 수 없습니다")

    # 기존 매핑 삭제
    await db.execute(
        delete(RoomCameraMapping).where(RoomCameraMapping.room_id == room_id)
    )

    # 새 매핑 생성
    for camera_id in req.camera_ids:
        db.add(RoomCameraMapping(room_id=room_id, camera_id=camera_id))

    await db.commit()
    return {"room_id": room_id, "camera_ids": req.camera_ids}


# --- 헬퍼: room_id → camera_ids 변환 ---

async def resolve_room_camera_ids(
    room_id: int | None,
    db: AsyncSession,
) -> list[str] | None:
    """room_id를 camera_ids 리스트로 변환. None이면 None 반환 (전체)."""
    if room_id is None:
        return None

    result = await db.execute(
        select(RoomCameraMapping.camera_id)
        .where(RoomCameraMapping.room_id == room_id)
    )
    return [row[0] for row in result.all()]
