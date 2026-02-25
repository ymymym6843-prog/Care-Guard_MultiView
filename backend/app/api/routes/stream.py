"""
MJPEG 비디오 스트림 엔드포인트
"""

import asyncio
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse

from app.config import settings
from app.core.auth import decode_token, require_auth
from app.core.logging_config import get_logger
from app.services.camera_service import camera_service
from app.services.monitoring_orchestrator import monitoring_orchestrator

logger = get_logger("app.api.stream")

router = APIRouter()

# 동시 MJPEG 연결 제한 (asyncio.Semaphore로 정확한 async-safe 제한)
_MAX_MJPEG_CONNECTIONS = 12
_mjpeg_semaphore = asyncio.Semaphore(_MAX_MJPEG_CONNECTIONS)
_active_connections = 0


async def mjpeg_generator(cam_instance=None):
    """MJPEG 프레임 제너레이터 (semaphore release는 _guarded_stream에서 처리)"""
    global _active_connections
    _active_connections += 1
    logger.info("MJPEG 연결 시작 (활성: %d/%d)", _active_connections, _MAX_MJPEG_CONNECTIONS)
    _empty_count = 0
    _MAX_EMPTY = 3000  # ~100초간 프레임 없으면 연결 종료 (데모 영상 루프 전환 대비)
    _last_jpeg = None  # 마지막 성공 프레임 캐시 (빈 프레임 구간 대비)
    try:
        while True:
            if cam_instance is not None:
                jpeg = cam_instance.get_latest_jpeg()
            else:
                jpeg = camera_service.get_latest_jpeg()
            if jpeg:
                _empty_count = 0
                _last_jpeg = jpeg
                yield (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n\r\n" + jpeg + b"\r\n"
                )
            else:
                _empty_count += 1
                if _empty_count > _MAX_EMPTY:
                    logger.info("MJPEG 프레임 없음 타임아웃, 연결 종료")
                    break
                # 빈 프레임 구간에서도 마지막 프레임 재전송 (연결 유지)
                if _last_jpeg and _empty_count % 30 == 0:
                    yield (
                        b"--frame\r\n"
                        b"Content-Type: image/jpeg\r\n\r\n" + _last_jpeg + b"\r\n"
                    )
            await asyncio.sleep(settings.WS_PROCESS_INTERVAL)  # ~30fps
    finally:
        _active_connections -= 1
        logger.info("MJPEG 연결 종료 (활성: %d/%d)", _active_connections, _MAX_MJPEG_CONNECTIONS)


async def _guarded_stream(generator):
    """Semaphore acquire/release를 보장하는 래퍼 제너레이터"""
    try:
        async for chunk in generator:
            yield chunk
    finally:
        _mjpeg_semaphore.release()


async def _acquire_mjpeg_slot():
    """동시 MJPEG 연결 제한 확인 (non-blocking acquire)"""
    try:
        await asyncio.wait_for(_mjpeg_semaphore.acquire(), timeout=0.1)
    except asyncio.TimeoutError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="최대 동시 스트림 연결 수를 초과했습니다",
        )


@router.get("/mjpeg")
async def mjpeg_stream(
    request: Request,
    token: Optional[str] = Query(None, description="JWT 인증 토큰 (쿠키 폴백)"),
):
    """MJPEG 비디오 스트림 (쿠키 우선, query param 폴백)

    브라우저에서는 쿠키가 자동 전송됩니다.
    <img> 태그에서도 same-origin이면 쿠키가 전달됩니다.
    """
    # 1. 쿠키에서 토큰 추출
    effective_token = request.cookies.get("access_token")

    # 2. query param 폴백
    if not effective_token and token:
        effective_token = token

    if not effective_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="인증이 필요합니다",
        )

    payload = decode_token(effective_token)
    if not payload or payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="유효하지 않은 토큰입니다",
        )

    await _acquire_mjpeg_slot()

    return StreamingResponse(
        _guarded_stream(mjpeg_generator()),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )


@router.get("/mjpeg/{camera_id}")
async def mjpeg_stream_by_camera(
    camera_id: str,
    request: Request,
    token: Optional[str] = Query(None, description="JWT 인증 토큰 (쿠키 폴백)"),
):
    """카메라별 MJPEG 비디오 스트림"""
    effective_token = request.cookies.get("access_token")
    if not effective_token and token:
        effective_token = token
    if not effective_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="인증이 필요합니다")
    payload = decode_token(effective_token)
    if not payload or payload.get("type") != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="유효하지 않은 토큰입니다")

    cam = camera_service.get(camera_id)
    if not cam:
        raise HTTPException(status_code=404, detail=f"Camera '{camera_id}' not found")

    await _acquire_mjpeg_slot()
    return StreamingResponse(
        _guarded_stream(mjpeg_generator(cam_instance=cam)),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )


@router.get("/internal-mjpeg")
async def internal_mjpeg_stream(
    key: Optional[str] = Query(None, description="내부 서비스 인증 키"),
):
    """내부 서비스 전용 MJPEG 스트림 (go2rtc 등 Docker 내부 서비스용)

    INTERNAL_STREAM_KEY 환경변수와 매칭하여 인증합니다.
    """
    internal_key = settings.INTERNAL_STREAM_KEY
    if not internal_key:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="INTERNAL_STREAM_KEY가 설정되지 않았습니다",
        )

    if key != internal_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="유효하지 않은 내부 인증 키입니다",
        )

    await _acquire_mjpeg_slot()

    return StreamingResponse(
        _guarded_stream(mjpeg_generator()),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )


# === 파이프라인 제어 API (개발/데모용) ===


@router.post("/pipeline/pause")
async def pause_pipeline(user=Depends(require_auth)):
    """파이프라인 일시정지 (개발/데모용)

    프론트엔드에서 '전체 중지' 버튼 클릭 시 호출.
    카메라 start/stop은 개별 카메라 API로 관리 (다중 카메라 지원).
    """
    monitoring_orchestrator.pause()
    return {"status": "paused", "message": "파이프라인이 일시정지되었습니다"}


@router.post("/pipeline/resume")
async def resume_pipeline(user=Depends(require_auth)):
    """파이프라인 재개

    프론트엔드에서 '시작' 버튼 클릭 시 호출.
    카메라 start/stop은 개별 카메라 API로 관리 (다중 카메라 지원).
    """
    monitoring_orchestrator.resume()
    return {"status": "running", "message": "파이프라인이 재개되었습니다"}


@router.get("/pipeline/status")
async def get_pipeline_status(user=Depends(require_auth)):
    """파이프라인 상태 조회"""
    return {
        "is_paused": monitoring_orchestrator.is_paused,
        "is_camera_active": camera_service.is_active,
    }
