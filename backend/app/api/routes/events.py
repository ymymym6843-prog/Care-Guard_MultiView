"""
이벤트 API 라우트
"""

import csv
import io
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select, desc, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import require_auth
from app.core.database import get_db
from app.models.event import Event
from app.models.user import User
from app.services.alert_manager import alert_manager
from app.api.routes.rooms import resolve_room_camera_ids

router = APIRouter()


@router.get("/export", dependencies=[Depends(require_auth)])
async def export_events(
    format: str = Query("csv", pattern="^(csv|xlsx)$"),
    level: str | None = Query(None),
    days: int = Query(30, ge=1, le=365),
    room_id: int | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """이벤트 내보내기 (CSV/XLSX)

    최근 N일간 이벤트를 CSV 또는 Excel 형식으로 다운로드합니다.
    """
    since = datetime.now(timezone.utc) - timedelta(days=days)

    query = select(Event).where(Event.timestamp >= since).order_by(desc(Event.timestamp))
    if level:
        query = query.where(Event.alert_level == level)

    camera_ids = await resolve_room_camera_ids(room_id, db)
    if camera_ids is not None:
        query = query.where(Event.camera_id.in_(camera_ids))

    result = await db.execute(query)
    events = result.scalars().all()

    # 내보내기 컬럼 정의
    columns = [
        "id", "timestamp", "alert_level", "duration", "camera_id",
        "person_id", "confidence", "acknowledged", "acknowledged_by", "acknowledged_at",
    ]

    # 이벤트 → 행 변환
    rows = []
    for e in events:
        rows.append([
            e.id,
            e.timestamp.isoformat() if e.timestamp else "",
            e.alert_level,
            e.duration,
            e.camera_id,
            e.person_id or "",
            round(e.confidence, 4) if e.confidence else 0.0,
            e.acknowledged,
            e.acknowledged_by or "",
            e.acknowledged_at.isoformat() if e.acknowledged_at else "",
        ])

    timestamp_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    if format == "xlsx":
        return _export_xlsx(columns, rows, timestamp_str)
    else:
        return _export_csv(columns, rows, timestamp_str)


def _export_csv(columns: list[str], rows: list[list], timestamp_str: str) -> StreamingResponse:
    """CSV 형식으로 내보내기"""
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(columns)
    writer.writerows(rows)
    output.seek(0)

    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="events_{timestamp_str}.csv"',
        },
    )


def _export_xlsx(columns: list[str], rows: list[list], timestamp_str: str) -> StreamingResponse:
    """XLSX 형식으로 내보내기 (openpyxl 필요, 미설치 시 CSV 폴백)"""
    try:
        from openpyxl import Workbook
    except ImportError:
        # openpyxl 미설치 시 CSV로 폴백
        return _export_csv(columns, rows, timestamp_str)

    wb = Workbook()
    ws = wb.active
    if ws is None:
        ws = wb.create_sheet("Events")
    else:
        ws.title = "Events"

    # 헤더 행
    ws.append(columns)

    # 데이터 행
    for row in rows:
        ws.append(row)

    # 컬럼 너비 자동 조정
    for col_idx, col_name in enumerate(columns, 1):
        ws.column_dimensions[chr(64 + col_idx)].width = max(len(col_name) + 2, 12)

    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)

    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f'attachment; filename="events_{timestamp_str}.xlsx"',
        },
    )


@router.get("", dependencies=[Depends(require_auth)])
async def list_events(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    level: str | None = Query(None),
    acknowledged: bool | None = Query(None),
    room_id: int | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """이벤트 목록 조회 (페이지네이션)"""
    query = select(Event).order_by(desc(Event.timestamp))

    if level:
        query = query.where(Event.alert_level == level)
    if acknowledged is not None:
        query = query.where(Event.acknowledged == acknowledged)

    camera_ids = await resolve_room_camera_ids(room_id, db)
    if camera_ids is not None:
        query = query.where(Event.camera_id.in_(camera_ids))

    # 전체 카운트
    count_query = select(func.count()).select_from(Event)
    if level:
        count_query = count_query.where(Event.alert_level == level)
    if acknowledged is not None:
        count_query = count_query.where(Event.acknowledged == acknowledged)
    if camera_ids is not None:
        count_query = count_query.where(Event.camera_id.in_(camera_ids))

    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # 페이지네이션
    offset = (page - 1) * size
    query = query.offset(offset).limit(size)

    result = await db.execute(query)
    events = result.scalars().all()

    return {
        "items": [_event_to_dict(e) for e in events],
        "total": total,
        "page": page,
        "size": size,
        "pages": (total + size - 1) // size if size > 0 else 0,
    }


@router.get("/{event_id}", dependencies=[Depends(require_auth)])
async def get_event(event_id: int, db: AsyncSession = Depends(get_db)):
    """이벤트 상세 조회"""
    result = await db.execute(select(Event).where(Event.id == event_id))
    event = result.scalar_one_or_none()
    if not event:
        raise HTTPException(status_code=404, detail="이벤트를 찾을 수 없습니다")
    return _event_to_dict(event)


@router.post("/{event_id}/acknowledge")
async def acknowledge_event(
    event_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_auth),
):
    """이벤트 확인 처리 (인증 필수)"""
    result = await db.execute(select(Event).where(Event.id == event_id))
    event = result.scalar_one_or_none()
    if not event:
        raise HTTPException(status_code=404, detail="이벤트를 찾을 수 없습니다")

    event.acknowledged = True
    event.acknowledged_by = user.username
    event.acknowledged_at = datetime.now(timezone.utc)
    await db.commit()

    # 알림 매니저도 acknowledge
    alert_manager.acknowledge()

    return {"status": "acknowledged", "event_id": event_id}


@router.post("/batch-acknowledge")
async def batch_acknowledge_events(
    room_id: int | None = Query(None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_auth),
):
    """미확인 이벤트 일괄 확인 처리"""
    query = select(Event).where(Event.acknowledged == False)

    camera_ids = await resolve_room_camera_ids(room_id, db)
    if camera_ids is not None:
        query = query.where(Event.camera_id.in_(camera_ids))

    result = await db.execute(query)
    events = result.scalars().all()

    now = datetime.now(timezone.utc)
    count = 0
    for event in events:
        event.acknowledged = True
        event.acknowledged_by = user.username
        event.acknowledged_at = now
        count += 1

    await db.commit()
    alert_manager.acknowledge()

    return {"status": "acknowledged", "count": count}


def _event_to_dict(event: Event) -> dict:
    return {
        "id": event.id,
        "timestamp": event.timestamp.isoformat() if event.timestamp else None,
        "alert_level": event.alert_level,
        "duration": event.duration,
        "camera_id": event.camera_id,
        "snapshot_path": event.snapshot_path,
        "person_id": event.person_id,
        "confidence": event.confidence,
        "acknowledged": event.acknowledged,
        "acknowledged_by": event.acknowledged_by,
        "acknowledged_at": event.acknowledged_at.isoformat() if event.acknowledged_at else None,
        "room_id": event.room_id,
    }
