"""
SENTIO AI - FastAPI 앱 진입점

요양병원 대기실 낙상 감지 웹 애플리케이션의 백엔드 서버입니다.
이 파일이 FastAPI 앱의 시작점입니다.

실행 방법:
    uvicorn app.main:app --reload --host 0.0.0.0 --port 8001
"""

import os
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"
# Force reload trigger 1

import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.core.exceptions import SentioError, sentio_exception_handler
from app.core.logging_config import setup_logging
from app.core.lifecycle import lifespan

# 로깅 초기화 (앱 시작 전)
setup_logging(level=settings.LOG_LEVEL)
logger = logging.getLogger(__name__)


# FastAPI 앱 인스턴스 생성
app = FastAPI(
    title="SENTIO - Sense · Protect · Care",
    description="실시간 낙상 감지 및 AI 안전 모니터링 시스템 API",
    version="1.0.0",
    lifespan=lifespan,
)

# 커스텀 예외 핸들러 등록
app.add_exception_handler(SentioError, sentio_exception_handler)  # type: ignore[arg-type]

# CORS 미들웨어 설정
allowed_origins = [settings.FRONTEND_URL]
# 추가 허용 출처가 있으면 추가
if settings.CORS_ALLOWED_ORIGINS:
    allowed_origins.extend(
        [origin.strip() for origin in settings.CORS_ALLOWED_ORIGINS.split(",") if origin.strip()]
    )

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 디버그 미들웨어 (DEBUG 모드에서만 활성화)
if settings.DEBUG:
    @app.middleware("http")
    async def debug_request(request, call_next):
        logger.debug(f"{request.method} {request.url.path}")
        response = await call_next(request)
        logger.debug(f"Response: {response.status_code}")
        return response




@app.get("/health", tags=["system"])
async def health_check():
    """서버 상태 확인 엔드포인트"""
    return {
        "status": "healthy",
        "service": "SENTIO AI",
        "version": "1.0.0",
    }


# 라우터 등록
from app.api.routes import events, cameras, stream, ws, auth, settings_route, push, zones, stats, reports, demo, incidents, rooms  # noqa: E402

app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(events.router, prefix="/api/events", tags=["events"])
app.include_router(cameras.router, prefix="/api/cameras", tags=["cameras"])
app.include_router(settings_route.router, prefix="/api/settings", tags=["settings"])
app.include_router(stream.router, prefix="/api/stream", tags=["stream"])
app.include_router(ws.router, prefix="/ws", tags=["websocket"])
app.include_router(push.router, prefix="/api/push", tags=["push"])
app.include_router(zones.router, prefix="/api/zones", tags=["zones"])
app.include_router(stats.router, prefix="/api/stats", tags=["stats"])
app.include_router(reports.router, prefix="/api/reports", tags=["reports"])
app.include_router(demo.router, prefix="/api/demo", tags=["demo"])
app.include_router(incidents.router, prefix="/api/incidents", tags=["incidents"])
app.include_router(rooms.router, prefix="/api/rooms", tags=["rooms"])

from app.api.routes import models, false_reports
app.include_router(models.router, prefix="/api/models", tags=["models"])
app.include_router(false_reports.router, prefix="/api/false-reports", tags=["false-reports"])
