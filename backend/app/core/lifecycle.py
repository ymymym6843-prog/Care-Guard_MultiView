import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.config import settings
from app.core.database import init_db
from app.core.logging_config import get_logger
from app.services.camera_service import camera_service
from app.services.monitoring_orchestrator import monitoring_orchestrator
from app.core.connection_manager import connection_manager
from app.services.push_service import push_service
from app.services.alert_manager import alert_manager
from app.services.event_recorder import event_recorder
from app.services.report_scheduler import report_scheduler

logger = get_logger("app.core.lifecycle")

async def _ensure_demo_admin():
    """데모/개발용 기본 admin 계정 자동 생성 (유저 0명일 때만)"""
    from app.core.database import async_session
    from app.models.user import User
    from sqlalchemy import select, func
    from app.core.auth import hash_password

    async with async_session() as session:
        count_result = await session.execute(select(func.count()).select_from(User))
        if (count_result.scalar() or 0) > 0:
            return
        admin = User(
            username="admin",
            hashed_password=hash_password("admin1234"),
            full_name="관리자",
            role="admin",
        )
        session.add(admin)
        await session.commit()
        logger.info("  데모용 admin 계정 자동 생성 (admin)")

@asynccontextmanager
async def lifespan(app: FastAPI):
    """앱 라이프사이클 관리"""
    # Startup
    logger.info("=" * 50)
    logger.info("  SENTIO AI 서버 시작")
    logger.info("  Host: %s:%d", settings.HOST, settings.PORT)
    logger.info("  Debug: %s", settings.DEBUG)
    logger.info("=" * 50)

    await init_db()

    if settings.DEBUG:
        await _ensure_demo_admin()

    # 다중 카메라 모드
    if settings.MULTI_CAMERA_ENABLED and settings.CAMERAS_CONFIG:
        import json as _json
        try:
            cameras_cfg = _json.loads(settings.CAMERAS_CONFIG)
            for cfg in cameras_cfg:
                cam_id = cfg["id"]
                cam_name = cfg.get("name", "")
                cam_source = cfg.get("source", "0")
                cam_speed = cfg.get("speed", 1.0)
                cam = camera_service.add_camera(cam_id, cam_name)
                cam._speed = float(cam_speed)
                if cfg.get("enabled", True):
                    # 플레이리스트 모드: source가 리스트면 순차 재생
                    if isinstance(cam_source, list) and len(cam_source) > 1:
                        first_source = cam_source[0]
                        cam._playlist = cam_source
                        cam._playlist_index = 0
                        cam.start(first_source)
                        if cam.is_active:
                            speed_str = f" x{cam_speed}" if cam_speed != 1.0 else ""
                            logger.info("  다중 카메라 시작: %s (%s)%s - 플레이리스트 %d개",
                                        cam_id, cam_name, speed_str, len(cam_source))
                        else:
                            logger.warning("  다중 카메라 시작 실패: %s (source=%s)", cam_id, first_source)
                    else:
                        # 단일 소스 모드
                        single = cam_source[0] if isinstance(cam_source, list) else cam_source
                        source = int(single) if isinstance(single, str) and single.isdigit() else single
                        cam.start(source)
                        if cam.is_active:
                            speed_str = f" x{cam_speed}" if cam_speed != 1.0 else ""
                            logger.info("  다중 카메라 시작: %s (%s)%s - 활성", cam_id, cam_name, speed_str)
                        else:
                            logger.warning("  다중 카메라 시작 실패: %s (source=%s)", cam_id, single)
            active_count = len([c for c in camera_service.all_cameras().values() if c.is_active])
            logger.info("  다중 카메라 모드: %d대 설정, %d대 활성", len(cameras_cfg), active_count)
        except Exception as e:
            logger.error("  다중 카메라 설정 파싱 실패: %s", e)
            camera_service.start()
    elif settings.MULTI_CAMERA_ENABLED:
        # CAMERAS_CONFIG 비어있으면 자동 감지 (직접 시작 방식)
        logger.info("  다중 카메라 자동 감지 모드...")

        def _auto_detect_and_start():
            """카메라를 직접 시작하여 감지 (Windows 호환)"""
            import hashlib
            import time

            started = []
            frame_hashes: dict[str, str] = {}

            for i in range(5):
                cam_id = f"cam{i}"
                cam_name = f"카메라 {i}"

                if cam_id == "cam0":
                    cam = camera_service.default
                    cam.name = cam_name
                else:
                    cam = camera_service.add_camera(cam_id, cam_name)

                cam.start(i)

                if not cam.is_active:
                    # 열기 실패 → 더 이상 카메라 없음
                    if cam_id != "cam0":
                        camera_service.remove_camera(cam_id)
                    break

                # 첫 프레임 대기 후 중복 검사
                time.sleep(0.5)
                jpeg = cam.get_latest_jpeg()
                if jpeg:
                    frame_hash = hashlib.md5(jpeg).hexdigest()[:16]
                    if frame_hash in frame_hashes:
                        cam.stop()
                        if cam_id != "cam0":
                            camera_service.remove_camera(cam_id)
                        logger.info("  카메라 %d: 중복 디바이스 (hash=%s → %s), 건너뜀",
                                    i, frame_hash, frame_hashes[frame_hash])
                        continue
                    frame_hashes[frame_hash] = cam_id

                started.append((cam_id, cam_name, cam.frame_width, cam.frame_height))
                logger.info("  자동 감지 카메라: %s (%s) - %dx%d",
                            cam_id, cam_name, cam.frame_width, cam.frame_height)

            return started

        started_cams = await asyncio.to_thread(_auto_detect_and_start)
        if started_cams:
            logger.info("  자동 감지 완료: %d대 활성", len(started_cams))
        else:
            logger.warning("  사용 가능한 카메라를 찾지 못했습니다 - 대기 모드")
    else:
        camera_service.start()

    if camera_service.is_active:
        logger.info("  카메라 서비스 시작됨")
    else:
        logger.warning("  카메라 사용 불가 - 대기 모드")

    # 모니터링 파이프라인
    monitoring_task = asyncio.create_task(monitoring_orchestrator.run_loop())
    logger.info("  모니터링 파이프라인 시작됨")

    # WebSocket 하트비트
    heartbeat_task = asyncio.create_task(connection_manager.heartbeat_loop())
    logger.info("  WebSocket 하트비트 시작됨")

    # 푸시 알림
    if push_service.enabled:
        alert_manager.on_alert_change(push_service.on_alert_change)
        logger.info("  푸시 알림 서비스 연결됨")

    # 이벤트 기록
    alert_manager.on_alert_change(event_recorder.on_alert_change)
    logger.info("  이벤트 기록 서비스 연결됨")

    # FHIR 연동
    if settings.FHIR_BASE_URL:
        from app.services.fhir_service import fhir_service as fs
        fs.configure(settings.FHIR_BASE_URL, settings.FHIR_API_KEY)
        
        async def _fhir_on_event(data: dict):
            if data.get("state") != "danger": return
            from datetime import datetime, timezone
            obs = fs.create_fall_observation(
                event_id=0,
                timestamp=datetime.now(timezone.utc),
                alert_level=data.get("state", ""),
                duration=data.get("duration", 0.0),
                confidence=data.get("confidence", 0.0),
                person_id=data.get("person_id", ""),
            )
            await fs.send_observation(obs)
            
        alert_manager.on_event(_fhir_on_event)
        logger.info("  FHIR EMR 서비스 연결됨: %s", settings.FHIR_BASE_URL)

    # IoT 연동
    if settings.IOT_WEBHOOK_URL:
        from app.services.iot_service import iot_service as isvc
        isvc.configure(settings.IOT_WEBHOOK_URL, settings.IOT_WEBHOOK_SECRET)
        alert_manager.on_alert_change(isvc.on_alert_change)
        logger.info("  IoT 서비스 연결됨: %s", settings.IOT_WEBHOOK_URL)

    # 리포트 스케줄러
    scheduler_task = None
    if settings.REPORT_SCHEDULE_DAILY or settings.REPORT_SCHEDULE_WEEKLY:
        scheduler_task = asyncio.create_task(report_scheduler.run_loop())
        logger.info("  리포트 스케줄러 시작됨")

    yield

    # Shutdown
    monitoring_task.cancel()
    heartbeat_task.cancel()
    if scheduler_task:
        scheduler_task.cancel()

    await asyncio.gather(monitoring_task, heartbeat_task, return_exceptions=True)
    if scheduler_task:
        await asyncio.gather(scheduler_task, return_exceptions=True)

    if settings.IOT_WEBHOOK_URL:
        from app.services.iot_service import iot_service as isvc
        await isvc.shutdown()

    camera_service.stop_all()
    logger.info("SENTIO 서버를 종료합니다...")
