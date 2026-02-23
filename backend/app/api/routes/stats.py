"""
통계 API

일별/시간대별/인원별 낙상 이벤트 통계를 제공합니다.
"""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func, extract, case, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db, _is_sqlite
from app.core.auth import require_auth
from app.models.user import User
from app.models.event import Event
from app.api.routes.rooms import resolve_room_camera_ids

router = APIRouter()


@router.get("/daily")
async def daily_stats(
    days: int = Query(default=30, ge=1, le=365),
    room_id: int | None = Query(None),
    user: User = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    """일별 이벤트 통계

    최근 N일간 일별 warning/danger 이벤트 수를 반환합니다.
    """
    since = datetime.now(timezone.utc) - timedelta(days=days)

    camera_ids = await resolve_room_camera_ids(room_id, db)

    q = (
        select(
            func.date(Event.timestamp).label("date"),
            Event.alert_level,
            func.count().label("count"),
        )
        .where(Event.timestamp >= since)
    )
    if camera_ids is not None:
        q = q.where(Event.camera_id.in_(camera_ids))
    q = q.group_by(func.date(Event.timestamp), Event.alert_level).order_by(func.date(Event.timestamp))

    result = await db.execute(q)

    rows = result.all()
    stats = {}
    for row in rows:
        date_str = str(row.date)
        if date_str not in stats:
            stats[date_str] = {"date": date_str, "warning": 0, "danger": 0, "total": 0}
        stats[date_str][row.alert_level] = row.count
        stats[date_str]["total"] += row.count

    return list(stats.values())


@router.get("/hourly")
async def hourly_stats(
    days: int = Query(default=7, ge=1, le=30),
    room_id: int | None = Query(None),
    user: User = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    """시간대별 이벤트 통계

    최근 N일간 시간대(0~23시)별 이벤트 빈도를 반환합니다.
    히트맵 시각화에 사용됩니다.
    """
    since = datetime.now(timezone.utc) - timedelta(days=days)

    camera_ids = await resolve_room_camera_ids(room_id, db)

    q = (
        select(
            extract("hour", Event.timestamp).label("hour"),
            func.count().label("count"),
        )
        .where(Event.timestamp >= since)
    )
    if camera_ids is not None:
        q = q.where(Event.camera_id.in_(camera_ids))
    q = q.group_by(extract("hour", Event.timestamp)).order_by(extract("hour", Event.timestamp))

    result = await db.execute(q)

    rows = result.all()
    # 모든 시간대를 포함 (0~23)
    hourly: dict[int, int] = {h: 0 for h in range(24)}
    for row in rows:
        if row.hour is not None:
            hourly[int(row.hour)] = int(row[1])

    return [{"hour": h, "count": c} for h, c in hourly.items()]


@router.get("/by-person")
async def person_stats(
    days: int = Query(default=30, ge=1, le=365),
    room_id: int | None = Query(None),
    user: User = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    """인원별 이벤트 통계"""
    since = datetime.now(timezone.utc) - timedelta(days=days)

    camera_ids = await resolve_room_camera_ids(room_id, db)

    q = (
        select(
            Event.person_id,
            func.count().label("total_events"),
            func.sum(case((Event.alert_level == "danger", 1), else_=0)).label("danger_count"),
            func.avg(Event.duration).label("avg_duration"),
        )
        .where(Event.timestamp >= since)
        .where(Event.person_id.isnot(None))
    )
    if camera_ids is not None:
        q = q.where(Event.camera_id.in_(camera_ids))
    q = q.group_by(Event.person_id).order_by(func.count().desc())

    result = await db.execute(q)

    rows = result.all()
    return [
        {
            "person_id": row.person_id,
            "total_events": row.total_events,
            "danger_count": row.danger_count or 0,
            "avg_duration": round(float(row.avg_duration or 0), 1),
        }
        for row in rows
    ]


@router.get("/summary")
async def summary_stats(
    days: int = Query(default=30, ge=1, le=365),
    room_id: int | None = Query(None),
    user: User = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    """통계 요약 (대시보드 카드용)"""
    since = datetime.now(timezone.utc) - timedelta(days=days)

    camera_ids = await resolve_room_camera_ids(room_id, db)

    def _apply_camera_filter(q):
        if camera_ids is not None:
            return q.where(Event.camera_id.in_(camera_ids))
        return q

    # 총 이벤트 수
    total_result = await db.execute(
        _apply_camera_filter(
            select(func.count()).select_from(Event).where(Event.timestamp >= since)
        )
    )
    total = total_result.scalar() or 0

    # danger 수
    danger_result = await db.execute(
        _apply_camera_filter(
            select(func.count())
            .select_from(Event)
            .where(Event.timestamp >= since)
            .where(Event.alert_level == "danger")
        )
    )
    danger = danger_result.scalar() or 0

    # 확인된 이벤트 수
    ack_result = await db.execute(
        _apply_camera_filter(
            select(func.count())
            .select_from(Event)
            .where(Event.timestamp >= since)
            .where(Event.acknowledged.is_(True))
        )
    )
    acknowledged = ack_result.scalar() or 0

    # 평균 응답 시간 (이벤트 발생 → 확인까지 걸린 초)
    avg_response = 0.0
    if acknowledged > 0:
        if camera_ids is not None:
            camera_list = ",".join(f"'{c}'" for c in camera_ids)
            camera_filter = f" AND camera_id IN ({camera_list})"
        else:
            camera_filter = ""
        if _is_sqlite:
            avg_sql = (
                "SELECT AVG((julianday(acknowledged_at) - julianday(timestamp)) * 86400) "
                "FROM events "
                "WHERE timestamp >= :since AND acknowledged = 1 AND acknowledged_at IS NOT NULL"
                + camera_filter
            )
        else:
            avg_sql = (
                "SELECT AVG(EXTRACT(EPOCH FROM (acknowledged_at - timestamp))) "
                "FROM events "
                "WHERE timestamp >= :since AND acknowledged = true AND acknowledged_at IS NOT NULL"
                + camera_filter
            )
        avg_result = await db.execute(text(avg_sql), {"since": since})
        avg_secs = avg_result.scalar()
        if avg_secs:
            avg_response = float(avg_secs)

    return {
        "period_days": days,
        "total_events": total,
        "danger_events": danger,
        "warning_events": total - danger,
        "acknowledged": acknowledged,
        "unacknowledged": total - acknowledged,
        "avg_response_seconds": round(avg_response, 1),
        "acknowledgment_rate": round(acknowledged / total * 100, 1) if total > 0 else 0,
    }
