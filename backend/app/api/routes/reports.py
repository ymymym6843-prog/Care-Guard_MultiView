"""
리포트 API 라우트

생성된 리포트 파일 목록 조회, 다운로드, 수동 생성 기능을 제공합니다.
"""

import os
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse

from app.config import settings
from app.core.auth import require_auth
from app.models.user import User

router = APIRouter()


@router.get("")
async def list_reports(
    user: User = Depends(require_auth),
):
    """생성된 리포트 파일 목록 조회

    REPORT_OUTPUT_DIR 내의 모든 리포트 파일(json, pdf)을 반환합니다.
    """
    output_dir = settings.REPORT_OUTPUT_DIR

    if not os.path.isdir(output_dir):
        return []

    reports = []
    for filename in sorted(os.listdir(output_dir), reverse=True):
        # 리포트 파일만 필터링 (json, pdf)
        if not filename.endswith((".json", ".pdf")):
            continue

        filepath = os.path.join(output_dir, filename)
        stat = os.stat(filepath)

        # 파일명에서 타입 추출 (daily_, weekly_, manual_)
        report_type = "unknown"
        if filename.startswith("daily_"):
            report_type = "daily"
        elif filename.startswith("weekly_"):
            report_type = "weekly"
        elif filename.startswith("manual_"):
            report_type = "manual"

        reports.append({
            "filename": filename,
            "type": report_type,
            "format": filename.rsplit(".", 1)[-1],
            "size_bytes": stat.st_size,
            "created_at": datetime.fromtimestamp(stat.st_ctime, tz=timezone.utc).isoformat(),
        })

    return reports


@router.get("/{filename}")
async def download_report(
    filename: str,
    user: User = Depends(require_auth),
):
    """리포트 파일 다운로드

    지정된 파일명의 리포트를 다운로드합니다.
    경로 조작 공격 방지를 위해 파일명에 디렉토리 구분자를 허용하지 않습니다.
    """
    # 경로 순회(traversal) 공격 방지
    if "/" in filename or "\\" in filename or ".." in filename:
        raise HTTPException(status_code=400, detail="잘못된 파일명입니다")

    filepath = os.path.join(settings.REPORT_OUTPUT_DIR, filename)

    if not os.path.isfile(filepath):
        raise HTTPException(status_code=404, detail="리포트 파일을 찾을 수 없습니다")

    # 파일 확장자에 따른 미디어 타입
    if filename.endswith(".pdf"):
        media_type = "application/pdf"
    elif filename.endswith(".json"):
        media_type = "application/json"
    else:
        media_type = "application/octet-stream"

    return FileResponse(
        path=filepath,
        filename=filename,
        media_type=media_type,
    )


@router.post("/generate")
async def generate_report(
    days: int = Query(30, ge=1, le=365),
    room_id: int | None = Query(None),
    user: User = Depends(require_auth),
):
    """리포트 수동 생성

    지정된 기간의 통계를 기반으로 리포트를 즉시 생성합니다.
    관리자 및 일반 스태프 모두 사용 가능합니다.
    """
    from app.services.report_scheduler import report_scheduler

    try:
        filename = await report_scheduler.generate_manual_report(days=days, room_id=room_id)
        return {
            "status": "generated",
            "filename": filename,
            "days": days,
        }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"리포트 생성 실패: {str(e)}",
        )
