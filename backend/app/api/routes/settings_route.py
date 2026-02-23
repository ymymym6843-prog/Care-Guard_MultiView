"""
설정 API 라우트
"""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.config import settings
from app.core.auth import require_auth
from app.models.user import User

router = APIRouter()


class SettingsUpdate(BaseModel):
    fall_warning_seconds: float | None = Field(None, ge=0.5, le=30.0)
    fall_danger_seconds: float | None = Field(None, ge=1.0, le=120.0)
    fall_cooldown_seconds: float | None = Field(None, ge=0.5, le=30.0)
    fall_head_hip_threshold: float | None = Field(None, ge=0.01, le=0.5)
    fall_rule_weight: float | None = Field(None, ge=0.0, le=1.0)
    fall_ml_weight: float | None = Field(None, ge=0.0, le=1.0)
    sound_enabled: bool | None = None
    sensitivity: float | None = Field(None, ge=0.0, le=1.0)


# 런타임 설정 (인메모리)
_runtime_settings = {
    "fall_warning_seconds": settings.FALL_WARNING_SECONDS,
    "fall_danger_seconds": settings.FALL_DANGER_SECONDS,
    "fall_cooldown_seconds": settings.FALL_COOLDOWN_SECONDS,
    "fall_head_hip_threshold": settings.FALL_HEAD_HIP_THRESHOLD,
    "fall_rule_weight": settings.FALL_RULE_WEIGHT,
    "fall_ml_weight": settings.FALL_ML_WEIGHT,
    "sound_enabled": True,
    "sensitivity": 0.5,
    "overlay_enabled": settings.OVERLAY_ENABLED,  # 스켈레톤/bbox 오버레이 토글
}


def _apply_to_services():
    """런타임 설정을 실제 서비스 싱글턴에 반영 (public setter 사용)"""
    from app.services.fall_detector import fall_detector
    from app.services.alert_manager import alert_manager

    fall_detector.head_hip_threshold = _runtime_settings["fall_head_hip_threshold"]
    fall_detector.cooldown_seconds = _runtime_settings["fall_cooldown_seconds"]
    fall_detector.rule_weight = _runtime_settings["fall_rule_weight"]
    # rule_weight setter가 ml_weight를 자동 계산하므로, 런타임 설정도 동기화
    _runtime_settings["fall_ml_weight"] = fall_detector.ml_weight
    alert_manager.warning_seconds = _runtime_settings["fall_warning_seconds"]
    alert_manager.danger_seconds = _runtime_settings["fall_danger_seconds"]


@router.get("", dependencies=[Depends(require_auth)])
async def get_settings():
    """현재 설정 조회 (인증 필수)"""
    return _runtime_settings


@router.put("")
async def update_settings(
    update: SettingsUpdate,
    user: User = Depends(require_auth),
):
    """설정 업데이트 (관리자 전용)"""
    if user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="관리자만 설정을 변경할 수 있습니다",
        )

    updates = update.model_dump(exclude_none=True)

    # rule_weight와 ml_weight는 상호 보완적 (합계 = 1.0)
    has_rule = "fall_rule_weight" in updates
    has_ml = "fall_ml_weight" in updates
    if has_rule and has_ml:
        # 둘 다 제공된 경우 합계 검증
        if abs(updates["fall_rule_weight"] + updates["fall_ml_weight"] - 1.0) > 0.001:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="fall_rule_weight + fall_ml_weight의 합은 1.0이어야 합니다",
            )
    elif has_rule and not has_ml:
        updates["fall_ml_weight"] = round(1.0 - updates["fall_rule_weight"], 4)
    elif has_ml and not has_rule:
        updates["fall_rule_weight"] = round(1.0 - updates["fall_ml_weight"], 4)

    for key, value in updates.items():
        if key in _runtime_settings:
            _runtime_settings[key] = value

    _apply_to_services()
    return _runtime_settings


# === 프로필 API ===


class ProfileUpdate(BaseModel):
    name: str = Field(..., pattern=r"^(fast|balanced|precise|rule-enhanced)$")


@router.get("/profiles", dependencies=[Depends(require_auth)])
async def get_profiles():
    """앙상블 프로필 목록 + 현재 활성 프로필"""
    from app.services.ensemble_profiles import list_profiles, get_current_profile_name
    return {
        "profiles": list_profiles(),
        "current": get_current_profile_name(),
    }


@router.put("/profiles")
async def update_profile(
    body: ProfileUpdate,
    user: User = Depends(require_auth),
):
    """앙상블 프로필 전환 (관리자 전용)"""
    if user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="관리자만 프로필을 변경할 수 있습니다",
        )

    from app.services.ensemble_profiles import apply_profile

    try:
        profile = apply_profile(body.name)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e),
        )

    # 런타임 설정도 동기화
    _runtime_settings["fall_rule_weight"] = profile.rule_weight
    _runtime_settings["fall_ml_weight"] = profile.ml_weight

    return {
        "name": profile.name,
        "label": profile.label,
        "rule_weight": profile.rule_weight,
        "ml_weight": profile.ml_weight,
        "enhanced_rules": profile.enhanced_rules,
    }


# === 오버레이 토글 API ===


class OverlayToggle(BaseModel):
    enabled: bool


@router.get("/overlay", dependencies=[Depends(require_auth)])
async def get_overlay_status():
    """오버레이(스켈레톤/bbox) 표시 상태 조회"""
    return {"overlay_enabled": _runtime_settings["overlay_enabled"]}


@router.put("/overlay")
async def toggle_overlay(
    body: OverlayToggle,
    user: User = Depends(require_auth),
):
    """오버레이 on/off 토글 (관리자 전용, 발표용)"""
    if user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="관리자만 오버레이 설정을 변경할 수 있습니다",
        )

    _runtime_settings["overlay_enabled"] = body.enabled
    return {"overlay_enabled": body.enabled}


def is_overlay_enabled() -> bool:
    """오버레이 활성화 여부 (orchestrator에서 사용)"""
    return _runtime_settings.get("overlay_enabled", True)
