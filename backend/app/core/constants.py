"""
SENTIO 상수 정의

애플리케이션 전체에서 사용되는 매직 넘버와 상수를 중앙 관리합니다.
"""

# === 네트워크 타임아웃 (초) ===
DEFAULT_REQUEST_TIMEOUT = 5.0
AUTH_CHECK_TIMEOUT = 5.0
SETUP_CHECK_TIMEOUT = 5.0

# === 재시도 설정 ===
MAX_SETUP_CHECK_RETRIES = 5  # 10회에서 5회로 감소
RETRY_DELAY_BASE = 1.0  # Exponential backoff 기본 지연 (초)
RETRY_DELAY_MAX = 10.0  # 최대 재시도 지연 (초)

# === 카메라 갱신 간격 (밀리초) ===
CAMERA_REFRESH_INTERVAL_MS = 30000  # 30초

# === 데모 키보드 단축키 ===
DEMO_KEY_WARNING = "F1"
DEMO_KEY_WARNING_PERSIST = "F2"
DEMO_KEY_DANGER = "F3"
DEMO_KEY_RECOVERY = "F4"

# === HTTP 상태 코드 ===
HTTP_OK = 200
HTTP_UNAUTHORIZED = 401
HTTP_FORBIDDEN = 403
HTTP_NOT_FOUND = 404
HTTP_SERVER_ERROR = 500
