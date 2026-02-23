"""
SENTIO 커스텀 예외 체계

모든 예외는 SentioError를 상속합니다.
"""

from fastapi import Request
from fastapi.responses import JSONResponse


class SentioError(Exception):
    """SENTIO 기본 예외"""

    def __init__(self, message: str = "내부 서버 오류", status_code: int = 500):
        self.message = message
        self.status_code = status_code
        super().__init__(self.message)


class CameraError(SentioError):
    """카메라 관련 오류"""

    def __init__(self, message: str = "카메라 오류가 발생했습니다"):
        super().__init__(message=message, status_code=503)


class DetectionError(SentioError):
    """포즈/낙상 감지 오류"""

    def __init__(self, message: str = "감지 처리 중 오류가 발생했습니다"):
        super().__init__(message=message, status_code=500)


class AuthenticationError(SentioError):
    """인증 오류"""

    def __init__(self, message: str = "인증에 실패했습니다"):
        super().__init__(message=message, status_code=401)


class DatabaseError(SentioError):
    """데이터베이스 오류"""

    def __init__(self, message: str = "데이터베이스 오류가 발생했습니다"):
        super().__init__(message=message, status_code=500)


# Backward compatibility aliases
CareGuardError = SentioError
careguard_exception_handler = None  # replaced below


async def sentio_exception_handler(request: Request, exc: SentioError) -> JSONResponse:
    """FastAPI 전역 예외 핸들러"""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": type(exc).__name__,
            "message": exc.message,
        },
    )

# Backward compat
careguard_exception_handler = sentio_exception_handler
