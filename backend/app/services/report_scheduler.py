"""
리포트 자동 생성 스케줄러

설정된 시각에 일간/주간 리포트를 자동으로 생성합니다.
asyncio 기반 sleep 루프로 스케줄을 확인하며,
리포트 파일은 REPORT_OUTPUT_DIR 에 타임스탬프 파일명으로 저장됩니다.
"""

import asyncio
import json
import os
from datetime import datetime, timedelta, timezone

from app.config import settings
from app.core.logging_config import get_logger

logger = get_logger("app.services.report_scheduler")

# 요일 이름 매핑 (영문 약자 → weekday 번호)
_DAY_MAP = {
    "MON": 0, "TUE": 1, "WED": 2, "THU": 3,
    "FRI": 4, "SAT": 5, "SUN": 6,
}


class ReportScheduler:
    """일간/주간 리포트 자동 생성 스케줄러"""

    def __init__(self):
        self._running: bool = False
        self._last_daily: str = ""   # 마지막 일간 리포트 생성 날짜 (YYYY-MM-DD)
        self._last_weekly: str = ""  # 마지막 주간 리포트 생성 날짜 (YYYY-MM-DD)

    def _parse_daily_schedule(self) -> tuple[int, int] | None:
        """일간 스케줄 파싱 (HH:MM → (hour, minute))"""
        schedule = settings.REPORT_SCHEDULE_DAILY.strip()
        if not schedule:
            return None
        try:
            parts = schedule.split(":")
            return int(parts[0]), int(parts[1])
        except (ValueError, IndexError):
            logger.warning("잘못된 일간 리포트 스케줄 형식: %s (예: 08:00)", schedule)
            return None

    def _parse_weekly_schedule(self) -> tuple[int, int, int] | None:
        """주간 스케줄 파싱 (DAY HH:MM → (weekday, hour, minute))"""
        schedule = settings.REPORT_SCHEDULE_WEEKLY.strip()
        if not schedule:
            return None
        try:
            parts = schedule.split()
            day_str = parts[0].upper()
            time_parts = parts[1].split(":")
            weekday = _DAY_MAP.get(day_str)
            if weekday is None:
                logger.warning("잘못된 요일: %s (MON~SUN)", day_str)
                return None
            return weekday, int(time_parts[0]), int(time_parts[1])
        except (ValueError, IndexError):
            logger.warning("잘못된 주간 리포트 스케줄 형식: %s (예: MON 08:00)", schedule)
            return None

    async def run_loop(self) -> None:
        """스케줄러 메인 루프 (매 30초마다 시각 확인)"""
        self._running = True
        logger.info(
            "리포트 스케줄러 시작 (daily=%s, weekly=%s)",
            settings.REPORT_SCHEDULE_DAILY or "비활성화",
            settings.REPORT_SCHEDULE_WEEKLY or "비활성화",
        )

        daily_schedule = self._parse_daily_schedule()
        weekly_schedule = self._parse_weekly_schedule()

        while self._running:
            try:
                now = datetime.now(timezone.utc)
                today_str = now.strftime("%Y-%m-%d")

                # 일간 리포트 확인
                if daily_schedule and self._last_daily != today_str:
                    hour, minute = daily_schedule
                    if now.hour == hour and now.minute >= minute:
                        await self._generate_daily_report(now)
                        self._last_daily = today_str

                # 주간 리포트 확인
                if weekly_schedule and self._last_weekly != today_str:
                    weekday, hour, minute = weekly_schedule
                    if now.weekday() == weekday and now.hour == hour and now.minute >= minute:
                        await self._generate_weekly_report(now)
                        self._last_weekly = today_str

            except asyncio.CancelledError:
                logger.info("리포트 스케줄러 종료됨")
                raise
            except Exception as e:
                logger.error("리포트 스케줄러 오류: %s", e, exc_info=True)

            # 30초마다 확인
            await asyncio.sleep(30)

    async def _generate_daily_report(self, now: datetime) -> None:
        """일간 리포트 생성"""
        logger.info("일간 리포트 생성 시작...")
        try:
            summary, daily_stats = await self._fetch_stats(days=1)
            await self._save_report(
                summary=summary,
                daily_stats=daily_stats,
                filename=f"daily_{now.strftime('%Y-%m-%d')}.json",
                title="SENTIO 일간 리포트",
            )
            logger.info("일간 리포트 생성 완료: daily_%s.json", now.strftime("%Y-%m-%d"))
        except Exception as e:
            logger.error("일간 리포트 생성 실패: %s", e, exc_info=True)

    async def _generate_weekly_report(self, now: datetime) -> None:
        """주간 리포트 생성"""
        logger.info("주간 리포트 생성 시작...")
        try:
            summary, daily_stats = await self._fetch_stats(days=7)
            await self._save_report(
                summary=summary,
                daily_stats=daily_stats,
                filename=f"weekly_{now.strftime('%Y-%m-%d')}.json",
                title="SENTIO 주간 리포트",
            )
            logger.info("주간 리포트 생성 완료: weekly_%s.json", now.strftime("%Y-%m-%d"))
        except Exception as e:
            logger.error("주간 리포트 생성 실패: %s", e, exc_info=True)

    async def generate_manual_report(self, days: int = 30, room_id: int | None = None) -> str:
        """수동 리포트 생성 (API에서 호출)

        Returns:
            생성된 파일명
        """
        now = datetime.now(timezone.utc)
        summary, daily_stats = await self._fetch_stats(days=days, room_id=room_id)

        room_label = f"_room{room_id}" if room_id is not None else ""
        filename = f"manual_{now.strftime('%Y-%m-%d_%H%M%S')}{room_label}.json"
        await self._save_report(
            summary=summary,
            daily_stats=daily_stats,
            filename=filename,
            title=f"SENTIO 수동 리포트 (최근 {days}일)",
        )
        logger.info("수동 리포트 생성 완료: %s", filename)
        return filename

    async def _resolve_camera_ids(self, room_id: int | None) -> list[str] | None:
        """room_id → camera_ids 변환"""
        if room_id is None:
            return None
        from app.core.database import async_session
        from app.models.room import RoomCameraMapping
        from sqlalchemy import select

        async with async_session() as db:
            result = await db.execute(
                select(RoomCameraMapping.camera_id)
                .where(RoomCameraMapping.room_id == room_id)
            )
            return [row[0] for row in result.all()]

    async def _fetch_stats(self, days: int, room_id: int | None = None) -> tuple[dict, list[dict]]:
        """DB에서 통계 데이터 조회"""
        from app.core.database import async_session
        from app.models.event import Event
        from sqlalchemy import select, func, case

        since = datetime.now(timezone.utc) - timedelta(days=days)
        camera_ids = await self._resolve_camera_ids(room_id)

        async with async_session() as db:
            # 공통 필터 조건 빌더
            def _base_filter(stmt):
                stmt = stmt.where(Event.timestamp >= since)
                if camera_ids is not None:
                    stmt = stmt.where(Event.camera_id.in_(camera_ids))
                return stmt

            # 요약 통계
            total_result = await db.execute(
                _base_filter(select(func.count()).select_from(Event))
            )
            total = total_result.scalar() or 0

            danger_result = await db.execute(
                _base_filter(
                    select(func.count()).select_from(Event)
                    .where(Event.alert_level == "danger")
                )
            )
            danger = danger_result.scalar() or 0

            ack_result = await db.execute(
                _base_filter(
                    select(func.count()).select_from(Event)
                    .where(Event.acknowledged.is_(True))
                )
            )
            acknowledged = ack_result.scalar() or 0

            avg_response = 0.0
            if acknowledged > 0:
                avg_result = await db.execute(
                    _base_filter(
                        select(func.avg(Event.duration))
                        .where(Event.acknowledged.is_(True))
                    )
                )
                avg_response = float(avg_result.scalar() or 0)

            summary = {
                "period_days": days,
                "total_events": total,
                "danger_events": danger,
                "warning_events": total - danger,
                "acknowledged": acknowledged,
                "acknowledgment_rate": round(acknowledged / total * 100, 1) if total > 0 else 0,
                "avg_response_seconds": round(avg_response, 1),
            }

            # 일별 통계
            daily_stmt = (
                select(
                    func.date(Event.timestamp).label("date"),
                    Event.alert_level,
                    func.count().label("count"),
                )
                .group_by(func.date(Event.timestamp), Event.alert_level)
                .order_by(func.date(Event.timestamp))
            )
            daily_result = await db.execute(_base_filter(daily_stmt))

            rows = daily_result.all()
            stats: dict[str, dict] = {}
            for row in rows:
                date_str = str(row.date)
                if date_str not in stats:
                    stats[date_str] = {"date": date_str, "warning": 0, "danger": 0, "total": 0}
                stats[date_str][row.alert_level] = row.count
                stats[date_str]["total"] += row.count

            daily_stats = list(stats.values())

        return summary, daily_stats

    async def _save_report(
        self,
        summary: dict,
        daily_stats: list[dict],
        filename: str,
        title: str,
    ) -> None:
        """리포트를 파일로 저장"""
        from app.services.report_service import report_service

        # 출력 디렉토리 생성
        output_dir = settings.REPORT_OUTPUT_DIR
        os.makedirs(output_dir, exist_ok=True)
        filepath = os.path.join(output_dir, filename)

        # PDF 가능 시 PDF로 저장, 아니면 JSON
        if report_service.pdf_available and filename.endswith(".json"):
            # PDF 버전도 함께 생성
            try:
                pdf_bytes = report_service.generate_pdf(summary, daily_stats, title=title)
                pdf_filename = filename.rsplit(".", 1)[0] + ".pdf"
                pdf_path = os.path.join(output_dir, pdf_filename)
                with open(pdf_path, "wb") as f:
                    f.write(pdf_bytes)
                logger.info("PDF 리포트 저장: %s", pdf_path)
            except Exception as e:
                logger.warning("PDF 리포트 생성 실패 (JSON만 저장): %s", e)

        # JSON 리포트 저장 (항상)
        json_report = report_service.generate_json_report(summary, daily_stats)
        json_report["title"] = title

        # asyncio.to_thread로 파일 I/O 처리 (이벤트 루프 블로킹 방지)
        def _write_json():
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(json_report, f, ensure_ascii=False, indent=2)

        await asyncio.to_thread(_write_json)
        logger.info("JSON 리포트 저장: %s", filepath)

    def stop(self) -> None:
        """스케줄러 정지"""
        self._running = False


# 싱글턴
report_scheduler = ReportScheduler()
