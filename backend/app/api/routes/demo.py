"""
데모 모드 API 라우트

발표 시연용: 데이터셋의 실제 낙상 영상을 선택하여 재생하고,
실시간으로 낙상 감지 파이프라인을 시연할 수 있습니다.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.config import settings
from app.core.auth import require_auth
from app.core.logging_config import get_logger
from app.services.camera_service import camera_service

logger = get_logger("app.api.demo")

router = APIRouter()


class DemoSelectRequest(BaseModel):
    path: str


@router.get("", dependencies=[Depends(require_auth)])
async def demo_status():
    """데모 모드 상태 확인"""
    return {
        "demo_mode": camera_service.demo_mode,
        "current_source": camera_service.current_source,
        "is_active": camera_service.is_active,
        "demo_dir": settings.DEMO_VIDEO_DIR or None,
        "available": bool(settings.DEMO_VIDEO_DIR),
    }


@router.get("/videos", dependencies=[Depends(require_auth)])
async def list_demo_videos():
    """데모 영상 목록"""
    if not settings.DEMO_VIDEO_DIR:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="DEMO_VIDEO_DIR이 설정되지 않았습니다. .env에 DEMO_VIDEO_DIR 경로를 설정하세요.",
        )

    videos = camera_service.list_demo_videos()
    return {"videos": videos, "demo_dir": settings.DEMO_VIDEO_DIR}


@router.post("/select", dependencies=[Depends(require_auth)])
async def select_demo_video(req: DemoSelectRequest):
    """데모 영상 선택 및 재생 시작"""
    path = req.path

    if camera_service.demo_mode and camera_service.is_active:
        # 이미 데모 모드 → 영상 전환
        ok = camera_service.switch_demo(path)
        if not ok:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"영상 전환 실패: {path}",
            )
        return {"status": "switched", "path": path}
    else:
        # 새로 데모 시작
        ok = camera_service.start_demo(path)
        if not ok:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"영상 재생 실패: {path}",
            )
        return {"status": "started", "path": path}


@router.post("/stop", dependencies=[Depends(require_auth)])
async def stop_demo():
    """데모 모드 중지"""
    camera_service.stop()
    return {"status": "stopped"}
