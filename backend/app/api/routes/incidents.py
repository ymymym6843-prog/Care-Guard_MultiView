"""
사건(Incident) API 라우트

Skeleton Blackbox에서 저장된 낙상 사건 데이터를 조회합니다.
모든 접근은 인증 + 감사 로깅이 적용됩니다.
"""

import re

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.auth import require_auth
from app.services.privacy_audit import privacy_audit
from app.services.skeleton_blackbox import skeleton_blackbox

router = APIRouter()

# incident_id 허용 패턴 (path traversal 방지)
_INCIDENT_ID_PATTERN = re.compile(r"^fall_\d{8}_\d{6}$")


@router.get("/")
async def list_incidents(user=Depends(require_auth)):
    """사건 목록 조회 (날짜, trigger_person, trigger_type)"""
    await privacy_audit.log_audit(user.username, "incident_list", "all_incidents")
    incidents = skeleton_blackbox.list_incidents()
    return {"incidents": incidents, "total": len(incidents)}


def _validate_incident_id(incident_id: str) -> None:
    """incident_id 형식 검증 (path traversal 방지)"""
    if not _INCIDENT_ID_PATTERN.match(incident_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="잘못된 사건 ID 형식입니다",
        )


@router.get("/{incident_id}")
async def get_incident(incident_id: str, user=Depends(require_auth)):
    """사건 상세 JSON (좌표 데이터)"""
    _validate_incident_id(incident_id)
    await privacy_audit.log_audit(user.username, "incident_access", incident_id)

    data = skeleton_blackbox.get_incident(incident_id)
    if data is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"사건을 찾을 수 없습니다: {incident_id}",
        )
    return data


@router.get("/{incident_id}/replay")
async def get_incident_replay(incident_id: str, user=Depends(require_auth)):
    """리플레이 데이터 (프론트엔드 SkeletonReplay용)

    프레임별 좌표 + 메타데이터를 프론트엔드 재생에 최적화된 형태로 반환합니다.
    """
    _validate_incident_id(incident_id)
    await privacy_audit.log_audit(user.username, "incident_replay", incident_id)

    data = skeleton_blackbox.get_incident(incident_id)
    if data is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"사건을 찾을 수 없습니다: {incident_id}",
        )

    # 프론트엔드 리플레이에 필요한 핵심 데이터만 추출
    replay = {
        "incident_id": data.get("incident_id", incident_id),
        "triggered_at": data.get("triggered_at", ""),
        "trigger_person": data.get("trigger_person", ""),
        "fps": data.get("fps", 30),
        "total_frames": data.get("total_frames", 0),
        "frames": data.get("frames", []),
        "privacy_notice": data.get("privacy_notice", ""),
    }
    return replay


@router.get("/stats/blackbox")
async def get_blackbox_stats(user=Depends(require_auth)):
    """블랙박스 버퍼 현재 상태"""
    await privacy_audit.log_audit(user.username, "blackbox_stats", "buffer_status")
    return skeleton_blackbox.get_buffer_stats()


@router.get("/stats/privacy")
async def get_privacy_report(user=Depends(require_auth)):
    """프라이버시 준수 보고서"""
    await privacy_audit.log_audit(user.username, "privacy_report", "compliance")
    report = await privacy_audit.generate_privacy_report()
    return report
