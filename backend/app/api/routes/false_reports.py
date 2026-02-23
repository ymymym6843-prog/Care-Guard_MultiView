"""
오탐지/미탐지 보고 CRUD API
"""

import shutil
import time
from pathlib import Path

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import select, func, desc

from app.core.auth import require_auth
from app.core.database import get_db, AsyncSession
from app.models.false_report import FalseReport
from app.models.user import User

router = APIRouter()

UPLOAD_DIR = Path("incidents/false_reports")
ATTENTION_THRESHOLD = 10


class FalseReportOut(BaseModel):
    id: int
    report_type: str
    notes: str | None
    image_path: str | None
    event_id: int | None
    uploaded_by: str
    created_at: str

    model_config = {"from_attributes": True}


class FalseReportListOut(BaseModel):
    items: list[FalseReportOut]
    total: int
    page: int
    size: int


class FalseReportSummary(BaseModel):
    total: int
    false_positive: int
    false_negative: int
    this_week: int
    needs_attention: bool


@router.get("/summary", response_model=FalseReportSummary)
async def get_false_report_summary(
    current_user: User = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    """오탐지/미탐지 보고 현황 요약"""
    total_result = await db.execute(select(func.count(FalseReport.id)))
    total = total_result.scalar() or 0

    fp_result = await db.execute(
        select(func.count(FalseReport.id)).where(FalseReport.report_type == "false_positive")
    )
    false_positive = fp_result.scalar() or 0

    fn_result = await db.execute(
        select(func.count(FalseReport.id)).where(FalseReport.report_type == "false_negative")
    )
    false_negative = fn_result.scalar() or 0

    week_ago = datetime.now(timezone.utc) - timedelta(days=7)
    week_result = await db.execute(
        select(func.count(FalseReport.id)).where(FalseReport.created_at >= week_ago)
    )
    this_week = week_result.scalar() or 0

    return FalseReportSummary(
        total=total,
        false_positive=false_positive,
        false_negative=false_negative,
        this_week=this_week,
        needs_attention=total >= ATTENTION_THRESHOLD,
    )


@router.post("/")
async def create_false_report(
    report_type: str = Form(...),
    notes: str = Form(""),
    event_id: int | None = Form(None),
    file: UploadFile | None = File(None),
    current_user: User = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    """오탐지/미탐지 보고 생성"""
    if report_type not in ("false_positive", "false_negative"):
        raise HTTPException(status_code=400, detail="report_type은 false_positive 또는 false_negative만 가능합니다")

    image_path = None
    if file and file.filename:
        UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        timestamp = int(time.time())
        # basename only to prevent path traversal
        clean_name = Path(file.filename).name
        safe_filename = f"{timestamp}_{clean_name}"
        dest = UPLOAD_DIR / safe_filename
        try:
            with dest.open("wb") as buf:
                shutil.copyfileobj(file.file, buf)
        finally:
            file.file.close()
        image_path = str(dest)

    report = FalseReport(
        report_type=report_type,
        notes=notes or None,
        image_path=image_path,
        event_id=event_id,
        uploaded_by=current_user.username,
    )
    db.add(report)
    await db.commit()
    await db.refresh(report)

    # Check total count for alert
    total_result = await db.execute(select(func.count(FalseReport.id)))
    total_reports = total_result.scalar() or 0

    response = {
        "id": report.id,
        "report_type": report.report_type,
        "notes": report.notes,
        "image_path": report.image_path,
        "event_id": report.event_id,
        "uploaded_by": report.uploaded_by,
        "created_at": report.created_at.isoformat(),
        "total_reports": total_reports,
    }

    if total_reports >= ATTENTION_THRESHOLD:
        response["alert"] = f"보고가 {total_reports}건 누적되었습니다. 모델 개선을 검토해주세요."

    return response


@router.get("/", response_model=FalseReportListOut)
async def list_false_reports(
    page: int = 1,
    size: int = 10,  # max 50 enforced below
    report_type: str | None = None,
    current_user: User = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    """오탐지/미탐지 보고 목록 조회"""
    page = max(1, page)
    size = max(1, min(50, size))

    query = select(FalseReport)
    count_query = select(func.count(FalseReport.id))

    if report_type:
        query = query.where(FalseReport.report_type == report_type)
        count_query = count_query.where(FalseReport.report_type == report_type)

    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    query = query.order_by(desc(FalseReport.created_at))
    query = query.offset((page - 1) * size).limit(size)

    result = await db.execute(query)
    reports = result.scalars().all()

    return FalseReportListOut(
        items=[
            FalseReportOut(
                id=r.id,
                report_type=r.report_type,
                notes=r.notes,
                image_path=r.image_path,
                event_id=r.event_id,
                uploaded_by=r.uploaded_by,
                created_at=r.created_at.isoformat(),
            )
            for r in reports
        ],
        total=total,
        page=page,
        size=size,
    )


@router.get("/{report_id}/image")
async def get_false_report_image(
    report_id: int,
    current_user: User = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    """보고에 첨부된 이미지 조회"""
    result = await db.execute(select(FalseReport).where(FalseReport.id == report_id))
    report = result.scalar_one_or_none()

    if not report:
        raise HTTPException(status_code=404, detail="보고를 찾을 수 없습니다")

    if not report.image_path:
        raise HTTPException(status_code=404, detail="이미지가 없습니다")

    p = Path(report.image_path)
    if not p.exists():
        raise HTTPException(status_code=404, detail="이미지 파일을 찾을 수 없습니다")

    return FileResponse(p, media_type="image/png")


@router.delete("/{report_id}")
async def delete_false_report(
    report_id: int,
    current_user: User = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    """오탐지/미탐지 보고 삭제 (admin only)"""
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="관리자 권한이 필요합니다")

    result = await db.execute(select(FalseReport).where(FalseReport.id == report_id))
    report = result.scalar_one_or_none()

    if not report:
        raise HTTPException(status_code=404, detail="보고를 찾을 수 없습니다")

    # 이미지 파일 삭제
    if report.image_path:
        p = Path(report.image_path)
        if p.exists():
            p.unlink()

    await db.delete(report)
    await db.commit()

    return {"status": "success", "message": "보고가 삭제되었습니다"}
