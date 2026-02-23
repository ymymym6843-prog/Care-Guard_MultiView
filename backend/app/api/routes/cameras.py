"""
카메라 API 라우트

모든 엔드포인트는 JWT 인증이 필요합니다.
인증되지 않은 요청은 401 Unauthorized를 반환합니다.
"""

import asyncio

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.config import settings
from app.core.auth import require_auth
from app.services.camera_service import camera_service

router = APIRouter()


class CameraSwitchRequest(BaseModel):
    camera_index: int = Field(..., ge=0, le=10, description="카메라 디바이스 인덱스 (0-10)")


class CameraAddRequest(BaseModel):
    camera_id: str = Field(..., min_length=1, max_length=32, description="카메라 고유 ID (예: cam1)")
    name: str = Field("", max_length=64, description="카메라 이름 (예: 측면 카메라)")
    source: str = Field(..., description="카메라 소스 (인덱스 또는 RTSP URL)")


class CameraUpdateRequest(BaseModel):
    name: str | None = Field(None, max_length=64, description="변경할 카메라 이름")
    # 추후 source 변경 등 확장 가능


@router.get("", dependencies=[Depends(require_auth)])
async def list_cameras():
    """카메라 목록 (인증 필수)

    다중 카메라 모드 시 모든 카메라 정보 반환.
    """
    cameras_list = []
    for cid, cam in camera_service.all_cameras().items():
        cameras_list.append({
            "id": cid,
            "name": cam.name,
            "source": cam.current_source,
            "is_active": cam.is_active,
            "resolution": f"{cam.frame_width}x{cam.frame_height}",
            "fps": round(cam.fps, 1),
            "demo_mode": cam.demo_mode,
        })

    return {
        "cameras": cameras_list,
        "multi_camera_enabled": settings.MULTI_CAMERA_ENABLED,
        "camera_index": camera_service.current_camera_index,
    }


@router.get("/available", dependencies=[Depends(require_auth)])
async def list_available_cameras():
    """시스템에서 사용 가능한 카메라 목록 탐색 (OpenCV 블로킹 → 스레드 위임)"""
    cameras = await asyncio.to_thread(camera_service.list_available_cameras)
    return {
        "cameras": cameras,
        "current_index": camera_service.current_camera_index,
        "is_active": camera_service.is_active,
    }


@router.post("/switch", dependencies=[Depends(require_auth)])
async def switch_camera(req: CameraSwitchRequest):
    """카메라 전환 (OpenCV 블로킹 → 스레드 위임)"""
    success = await asyncio.to_thread(camera_service.switch_camera, req.camera_index)
    if not success:
        raise HTTPException(400, f"Camera {req.camera_index} 열기 실패")
    return {
        "success": True,
        "camera_index": req.camera_index,
        "resolution": f"{camera_service.frame_width}x{camera_service.frame_height}",
    }


@router.post("/add", dependencies=[Depends(require_auth)])
async def add_camera(req: CameraAddRequest):
    """런타임 카메라 추가 (다중 카메라 모드)"""
    if not settings.MULTI_CAMERA_ENABLED:
        raise HTTPException(400, "다중 카메라 모드가 비활성화되어 있습니다 (MULTI_CAMERA_ENABLED=False)")

    existing = camera_service.get(req.camera_id)
    if existing and existing.is_active:
        raise HTTPException(409, f"Camera '{req.camera_id}' already exists and is active")

    cam = camera_service.add_camera(req.camera_id, req.name, req.source)

    # 소스가 숫자이면 int로 변환
    source = int(req.source) if req.source.isdigit() else req.source
    await asyncio.to_thread(cam.start, source)

    return {
        "success": cam.is_active,
        "camera_id": req.camera_id,
        "name": cam.name,
        "is_active": cam.is_active,
        "resolution": f"{cam.frame_width}x{cam.frame_height}",
    }


@router.patch("/{camera_id}", dependencies=[Depends(require_auth)])
async def update_camera(camera_id: str, req: CameraUpdateRequest):
    """카메라 정보 수정 (이름 등)"""
    cam = camera_service.get(camera_id)
    if not cam:
        raise HTTPException(404, f"Camera '{camera_id}' not found")

    if req.name is not None:
        cam.name = req.name

    return {
        "success": True,
        "camera_id": camera_id,
        "name": cam.name,
    }


@router.post("/{camera_id}/update", dependencies=[Depends(require_auth)])
async def update_camera_post(camera_id: str, req: CameraUpdateRequest):
    """카메라 정보 수정 (POST 방식 - PATCH 405 에러 회피용)"""
    return await update_camera(camera_id, req)


@router.delete("/{camera_id}", dependencies=[Depends(require_auth)])
async def remove_camera(camera_id: str):
    """카메라 제거 (다중 카메라 모드)"""
    if not settings.MULTI_CAMERA_ENABLED:
        raise HTTPException(400, "다중 카메라 모드가 비활성화되어 있습니다")

    success = camera_service.remove_camera(camera_id)
    if not success:
        raise HTTPException(404, f"Camera '{camera_id}' not found or cannot be removed")

    return {"success": True, "camera_id": camera_id}


@router.post("/{camera_id}/start", dependencies=[Depends(require_auth)])
async def start_camera(camera_id: str):
    """카메라 시작 (인증 필수)"""
    cam = camera_service.get(camera_id)
    if cam:
        await asyncio.to_thread(cam.start)
        return {"status": "started", "camera_id": camera_id, "is_active": cam.is_active}
    # 하위 호환: 기본 카메라 시작
    camera_service.start()
    return {"status": "started", "camera_id": camera_id}


@router.post("/{camera_id}/stop", dependencies=[Depends(require_auth)])
async def stop_camera(camera_id: str):
    """카메라 중지 (인증 필수)"""
    cam = camera_service.get(camera_id)
    if cam:
        cam.stop()
        return {"status": "stopped", "camera_id": camera_id}
    # 하위 호환
    camera_service.stop()
    return {"status": "stopped", "camera_id": camera_id}
