"""
SENTIO 환경 설정 관리 모듈

pydantic-settings를 사용하여 .env 파일이나 환경 변수에서
설정값을 자동으로 읽어옵니다.
"""

import secrets
import warnings
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_BACKEND_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """
    애플리케이션 설정

    .env 파일 또는 환경 변수에서 값을 가져옵니다.
    환경 변수가 없으면 기본값을 사용합니다.
    """

    model_config = SettingsConfigDict(
        env_file=str(_BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=True,
    )

    # 서버 설정
    HOST: str = "0.0.0.0"
    PORT: int = 8001
    DEBUG: bool = False  # 프로덕션: False (환경 변수로 활성화)
    LOG_LEVEL: str = "INFO"  # DEBUG, INFO, WARNING, ERROR

    # 카메라 설정
    CAMERA_INDEX: int = 0
    CAMERA_SOURCE: str = ""  # RTSP URL 또는 파일 경로 (빈 문자열이면 CAMERA_INDEX 사용)
    CAMERA_WIDTH: int = 1280   # 실시간 카메라 캡처 해상도 (높을수록 감지 정확도↑, 성능↓)
    CAMERA_HEIGHT: int = 720

    # 데이터베이스
    DATABASE_URL: str = "sqlite+aiosqlite:///./sentio.db"

    # CORS (프론트엔드 URL)
    FRONTEND_URL: str = "http://localhost:5173"
    # CORS 추가 허용 출처 (쉼표로 구분, 예: "http://localhost:3000,https://app.example.com")
    CORS_ALLOWED_ORIGINS: str = ""

    # JWT 인증
    JWT_SECRET_KEY: str = ""
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 480  # 8시간 (근무 시간)

    # HttpOnly 쿠키 설정
    COOKIE_SECURE: bool = False  # 운영: True (HTTPS 전용)
    COOKIE_SAMESITE: str = "lax"
    COOKIE_DOMAIN: str = ""  # 빈 문자열이면 자동 (현재 호스트)
    COOKIE_PATH: str = "/"

    # 낙상 감지 설정
    FALL_WARNING_SECONDS: float = 1.5
    FALL_DANGER_SECONDS: float = 5.0
    FALL_DANGER_SECONDS_ACTUAL: float = 0.0  # 실제 낙상(front/back/side)은 즉시 DANGER 전환 (대기 없음)
    FALL_DANGER_CONFIDENCE: float = 0.70  # DANGER 전환 최소 확신도 (0.50~0.69는 WARNING 유지)
    FALL_COOLDOWN_SECONDS: float = 3.0  # 고령자 회복 시간 고려 (DANGER=5.0초보다 짧게)
    FALL_HEAD_HIP_THRESHOLD: float = 0.05

    # 낙상 감지 알고리즘 상수
    FALL_RAPID_DESCENT_THRESHOLD: float = 0.15
    FALL_HORIZONTAL_ANGLE: float = 45.0
    FALL_COMPOSITE_THRESHOLD: float = 0.50  # 미탐 방지 위해 0.50 유지
    FALL_PRE_IMPACT_THRESHOLD: float = 0.35  # 전조 감지 임계값 (알람 피로 방지 위해 0.25→0.35 상향)
    FALL_PRE_IMPACT_ML_THRESHOLD: float = 0.4  # ML 단독 전조 감지 임계값 (규칙 무반응이어도 ML이 이상 감지)

    # 앙상블 가중치 (규칙 기반 + ML 분류기)
    FALL_RULE_WEIGHT: float = 0.0  # 규칙 0%
    FALL_ML_WEIGHT: float = 1.0    # ML 100% (GRU 모델, CPU 지원)

    # 앙상블 프로필 (fast/balanced/precise/ml-optimized)
    FALL_PROFILE: str = "ml-optimized"

    # Rule-enhanced 확장 조건 (N1-N6)
    FALL_ENHANCED_RULES_ENABLED: bool = True  # Phase 26: 기본 활성화
    FALL_N1_ACCEL_THRESHOLD: float = 0.02
    FALL_N1_VELOCITY_GATE: float = 0.05
    FALL_N2_ARM_SPREAD_VEL: float = 0.08
    FALL_N2_WRIST_DROP: float = 0.02
    FALL_N3_MIN_ANKLE_SPAN: float = 0.05
    FALL_N3_GROWING_FRAMES: int = 2
    FALL_N4_ANGLE_RATE: float = 15.0
    FALL_N4_ANGLE_LIMIT: float = 130.0
    FALL_N5_STANDING_TILT: float = 0.30
    FALL_N6_ACCEL_RATIO: float = 1.3

    # 오탐 방지: 구부리기/제어된 눕기 감지
    FALL_BENDING_MAX_ANKLE_VARIANCE: float = 0.015  # 발목 위치 변화량 임계값 (구부리기: 발목 고정)
    FALL_BENDING_MAX_DESCENT_ACCEL: float = 0.005   # 구부리기 최대 하강 가속도 (느린 동작)
    FALL_CONTROLLED_LYING_DECEL_THRESHOLD: float = -0.002  # 제어된 눕기 감속 임계값 (음수=감속)
    FALL_CONTROLLED_LYING_MIN_FRAMES: int = 15      # 제어된 눕기 최소 프레임 (천천히)

    # 오탐 방지 설정
    FALL_MIN_VISIBILITY: float = 0.5         # 랜드마크 최소 가시성 (이하이면 감지 건너뜀)
    FALL_GRACE_FRAMES: int = 5               # 새 인물 진입 후 감지 유예 프레임 (8→5, 빠른 낙상 대응)
    FALL_CONSECUTIVE_FRAMES: int = 3         # 낙상 판정 전 연속 확인 프레임 수 (1→3: 오탐 방지)
    # 다중 프레임 누적 감지 (저가시성 시나리오용, AIHub C1/C4/C8 카메라)
    FALL_LOW_VIS_MIN: float = 0.3            # 저가시성 최소 임계값 (이하면 완전 건너뜀)
    FALL_LOW_VIS_ACCUM_FRAMES: int = 3       # 저가시성 누적 프레임 수
    FALL_LOW_VIS_ACCUM_THRESHOLD: float = 0.35  # 저가시성 누적 점수 임계값
    # 동작 지속성 체크 (오탐 방지: 낙상 후 제어된 움직임으로 취소)
    FALL_POST_FALL_CHECK_FRAMES: int = 10    # 낙상 후 움직임 체크 프레임 수
    FALL_POST_FALL_MAX_VARIANCE: float = 0.0005  # 제어된 움직임 최대 분산 (낮을수록 부드러운 움직임)
    FALL_LYING_STABLE_EXEMPT_FRAMES: int = 30  # 누워있음 안정 프레임 (60→30, 더 빠르게 면제)
    FALL_FAST_FALL_THRESHOLD: float = 0.85   # 이 점수 이상이면 grace period 무시 (빠른 낙상)

    # 자세 분류 설정
    POSTURE_KNEE_BEND_SITTING: float = 0.4   # 무릎 굽힘 비율 < 이 값이면 앉음 판정
    POSTURE_KNEE_BEND_STANDING: float = 0.6  # 무릎 굽힘 비율 > 이 값이면 서있음 판정
    POSTURE_LYING_ANGLE: float = 30.0        # 체형 각도 < 이 값이면 누워있음 판정
    POSTURE_STABILITY_FRAMES: int = 5        # 자세 안정화 프레임 수 (떨림 방지)

    # 착석 상태 낙상 감지 (의자/휠체어 환자용)
    FALL_SEATED_HEAD_HIP_THRESHOLD: float = 0.02     # 앉은 상태 머리-엉덩이 역전 (더 민감)
    FALL_SEATED_RAPID_DESCENT_THRESHOLD: float = 0.12  # 앉은 상태 하강 임계값 (0.08→0.12 완화, 자연스러운 고개 끄덕임 허용)
    FALL_SEATED_HORIZONTAL_ANGLE: float = 30.0       # 앉은 상태 수평 각도 (기대앉기 허용)
    FALL_SEATED_FORWARD_SLUMP_THRESHOLD: float = 0.25  # 머리가 무릎보다 아래로 (0.15→0.25 완화, 정상 숙임 허용)
    FALL_SEATED_LATERAL_TILT_THRESHOLD: float = 0.20  # 어깨 좌우 기울기 급변 (0.12→0.20 완화, 자연스러운 몸 기울임 허용)
    FALL_SEATED_HEIGHT_DROP_RATIO: float = 0.45       # 기준선 대비 머리 높이 45% 이상 하락 (0.3→0.45 완화)
    FALL_SEATED_BASELINE_MIN_FRAMES: int = 30         # 기준선 확립 최소 프레임 (이 전에는 착석 낙상 감지 비활성)

    # 개발 모드 자동 로그인 (DEBUG=true일 때만 작동)
    DEV_AUTO_LOGIN: bool = False  # 프로덕션: False (환경 변수로 활성화)
    DEV_AUTO_LOGIN_USERNAME: str = "admin"  # 자동 로그인할 사용자명

    # 데모 모드 (발표 시연용)
    DEMO_VIDEO_DIR: str = "demo_videos"  # 데모 영상 디렉터리 (상대 경로)

    # 내부 서비스 통신 키 (go2rtc → backend MJPEG 등)
    INTERNAL_STREAM_KEY: str = ""

    # FHIR EMR 연동 (비어있으면 비활성화)
    FHIR_BASE_URL: str = ""
    FHIR_API_KEY: str = ""

    # VAPID 푸시 알림 (비어있으면 푸시 비활성화)
    VAPID_PRIVATE_KEY: str = ""
    VAPID_PUBLIC_KEY: str = ""
    VAPID_CLAIMS_EMAIL: str = ""

    # IoT Webhook (경광등 등 외부 디바이스 연동, 비어있으면 비활성화)
    IOT_WEBHOOK_URL: str = ""
    IOT_WEBHOOK_SECRET: str = ""

    # 보행도구 인식 (Walking Aid Detection)
    WALKING_AID_MODEL: str = "models/walking_aid_yolo.onnx"  # ONNX 모델 경로
    WALKING_AID_CONFIDENCE: float = 0.45  # 감지 최소 신뢰도
    WALKING_AID_ESTABLISH_FRAMES: int = 15  # 보행도구 확인 프레임 수
    WALKING_AID_MISSING_FRAMES: int = 10  # 보행도구 분실 판정 프레임 수
    WALKING_AID_ASSOC_DIST: float = 0.42  # 인원-도구 매칭 최대 거리 (정규화)
    WALKING_AID_HEURISTIC_ENABLED: bool = True  # MediaPipe 휴리스틱 활성화

    # 얼굴 블러 (스냅샷 저장 시 자동 모자이크)
    FACE_BLUR_ENABLED: bool = False

    # 자동 리포트 스케줄 (cron-like, 비어있으면 비활성화)
    REPORT_SCHEDULE_DAILY: str = "08:00"  # 매일 이 시각에 일간 리포트 생성 (HH:MM, 빈 문자열이면 비활성화)
    REPORT_SCHEDULE_WEEKLY: str = "MON 08:00"  # 매주 이 요일/시각에 주간 리포트 생성 (빈 문자열이면 비활성화)
    REPORT_OUTPUT_DIR: str = "reports"  # 리포트 저장 디렉토리

    # GDPR/개인정보 동의
    PRIVACY_POLICY_VERSION: str = "1.0"

    # Privacy-First 파이프라인 (Phase 23)
    PRIVACY_NON_STORAGE: bool = True          # 원본 프레임 저장 금지
    PRIVACY_FRAME_RETENTION_MS: int = 0       # 프레임 메모리 보존 시간 (0=즉시 파기)
    PRIVACY_AUDIT_ENABLED: bool = True        # 프라이버시 감사 로그 활성화

    # Skeleton Blackbox (좌표 블랙박스)
    SKELETON_BLACKBOX_ENABLED: bool = True    # 좌표 블랙박스 활성화
    SKELETON_BLACKBOX_SECONDS: int = 20       # 블랙박스 버퍼 크기 (초)

    # 파이프라인 모드 (성능 최적화)
    YOLO_KEYPOINTS_ONLY: bool = True  # True: YOLO 17점만 사용 (빠름), False: MediaPipe 33점 추가 (정밀)
    YOLO_THRESHOLD_MULTIPLIER: float = 1.5  # YOLO-only 모드에서 임계값 상향 배수 (노이즈 대응)
    YOLO_USE_GPU: bool = True  # GPU 사용 (CUDA 필요)
    OVERLAY_ENABLED: bool = False  # False: bbox/skeleton 오버레이 비활성화 (성능 20-30% 향상)

    # 다중 카메라 설정
    MULTI_CAMERA_ENABLED: bool = False  # True: 다중 카메라 동시 운영, False: 기존 단일 카메라
    CAMERAS_CONFIG: str = ""  # JSON 배열, 예: '[{"id":"cam0","source":"0","name":"전면"},{"id":"cam1","source":"rtsp://...","name":"측면"}]'

    # 인프라 상수
    HEARTBEAT_INTERVAL: int = 30
    FRAME_QUEUE_SIZE: int = 2
    WS_PROCESS_INTERVAL: float = 0.033

    # AI 파이프라인 성능 튜닝
    AI_PROCESS_INTERVAL: float = 0.033        # AI 프레임 처리 간격 (0.033=30fps, 0.066=15fps)
    WS_POSE_BROADCAST_INTERVAL: float = 0.05  # 포즈 데이터 WebSocket 전송 간격 (0.05=20fps)
    WS_METRICS_BROADCAST_INTERVAL: float = 0.2  # 메트릭 WebSocket 전송 간격 (0.2=5fps)


# 설정 싱글턴 인스턴스 (앱 전체에서 공유)
settings = Settings()

# JWT_SECRET_KEY 안전성 검증
_INSECURE_DEFAULTS = {
    "",
    "sentio-secret-change-in-production",
    "change-this-to-a-secure-random-string-in-production",
}
if settings.JWT_SECRET_KEY in _INSECURE_DEFAULTS:
    _generated = secrets.token_urlsafe(32)
    warnings.warn(
        "JWT_SECRET_KEY가 설정되지 않았습니다. "
        "임시 랜덤 키를 생성합니다. "
        "프로덕션 환경에서는 반드시 .env에 JWT_SECRET_KEY를 설정하세요.",
        stacklevel=1,
    )
    settings.JWT_SECRET_KEY = _generated
