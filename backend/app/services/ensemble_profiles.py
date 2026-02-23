"""
앙상블 프로필 시스템

4개 프로필로 GPU 없는 요양병원 PC에서의 최적 성능 조합을 제공합니다.
- fast: 규칙 100%, ML 0% — 최대 FPS, 기본 4조건만
- balanced: 규칙 70%, ML 30% — 속도+정확도 균형 (기본 권장)
- precise: 규칙 50%, ML 50% — ML 최대 활용
- rule-enhanced: 규칙 100%, ML 0%, 확장규칙 ON — 10조건, ML 없이 고정확도
"""

from dataclasses import dataclass

from app.core.logging_config import get_logger

logger = get_logger("app.services.ensemble_profiles")


@dataclass(frozen=True)
class EnsembleProfile:
    name: str
    label: str           # 한글 이름
    rule_weight: float
    ml_weight: float
    enhanced_rules: bool  # N1-N6 활성화 여부
    description: str


# 프로필 정의
PROFILES: dict[str, EnsembleProfile] = {
    "fast": EnsembleProfile(
        name="fast",
        label="빠른 감지",
        rule_weight=1.0,
        ml_weight=0.0,
        enhanced_rules=False,
        description="규칙 기반 4조건만 사용. 최대 FPS, GPU 불필요.",
    ),
    "balanced": EnsembleProfile(
        name="balanced",
        label="균형 모드",
        rule_weight=0.7,
        ml_weight=0.3,
        enhanced_rules=False,
        description="규칙 70% + ML 30%. 속도와 정확도의 균형 (기본 권장).",
    ),
    "precise": EnsembleProfile(
        name="precise",
        label="정밀 감지",
        rule_weight=0.5,
        ml_weight=0.5,
        enhanced_rules=False,
        description="규칙 50% + ML 50%. ML 분류기 최대 활용.",
    ),
    "rule-enhanced": EnsembleProfile(
        name="rule-enhanced",
        label="확장 규칙",
        rule_weight=1.0,
        ml_weight=0.0,
        enhanced_rules=True,
        description="규칙 기반 10조건 (C1-C4 + N1-N6). ML 없이 고정확도, GPU 불필요.",
    ),
}

# 현재 활성 프로필 (Phase 26: rule-enhanced 기본값으로 변경)
_current_profile_name: str = "rule-enhanced"


def get_current_profile() -> EnsembleProfile:
    """현재 활성 프로필 반환"""
    return PROFILES.get(_current_profile_name, PROFILES["balanced"])


def get_current_profile_name() -> str:
    """현재 활성 프로필 이름 반환"""
    return _current_profile_name


def apply_profile(name: str) -> EnsembleProfile:
    """프로필 적용: fall_detector 가중치 + enhanced_rules 설정

    Args:
        name: 프로필 이름 (fast/balanced/precise/rule-enhanced)

    Returns:
        적용된 EnsembleProfile

    Raises:
        ValueError: 유효하지 않은 프로필 이름
    """
    global _current_profile_name

    if name not in PROFILES:
        raise ValueError(
            f"유효하지 않은 프로필: '{name}'. "
            f"사용 가능: {list(PROFILES.keys())}"
        )

    profile = PROFILES[name]

    # FallDetector 싱글턴에 적용
    from app.services.fall_detector import fall_detector

    fall_detector.rule_weight = profile.rule_weight
    # rule_weight setter가 ml_weight를 자동 계산하므로 별도 설정 불필요
    fall_detector.enhanced_rules = profile.enhanced_rules

    _current_profile_name = name

    logger.info(
        "앙상블 프로필 적용: %s (%s) | rule=%.0f%% ml=%.0f%% enhanced=%s",
        name, profile.label,
        profile.rule_weight * 100, profile.ml_weight * 100,
        profile.enhanced_rules,
    )

    return profile


def list_profiles() -> list[dict]:
    """모든 프로필 목록을 dict 리스트로 반환"""
    result = []
    for name, p in PROFILES.items():
        result.append({
            "name": p.name,
            "label": p.label,
            "rule_weight": p.rule_weight,
            "ml_weight": p.ml_weight,
            "enhanced_rules": p.enhanced_rules,
            "description": p.description,
            "active": name == _current_profile_name,
        })
    return result
