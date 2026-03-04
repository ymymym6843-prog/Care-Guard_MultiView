"""
JWT 인증 유틸리티

HttpOnly 쿠키 기반 인증을 지원합니다.
하위 호환을 위해 Authorization Bearer 헤더 폴백도 유지합니다.
"""

from datetime import datetime, timedelta, timezone

import bcrypt
from fastapi import Depends, HTTPException, Request, Response, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.database import get_db
from app.models.user import User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))


def create_access_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire, "type": "access"})
    return jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def create_refresh_token(data: dict) -> str:
    """리프레시 토큰 생성 (7일 유효)"""
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(days=7)
    to_encode.update({"exp": expire, "type": "refresh"})
    return jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_token(token: str) -> dict | None:
    try:
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        return payload
    except JWTError:
        return None


def _extract_token_from_request(request: Request, bearer_token: str | None) -> str | None:
    """요청에서 JWT 토큰 추출 (쿠키 우선, Authorization 헤더 폴백)"""
    # 1. 쿠키에서 추출
    cookie_token = request.cookies.get("access_token")
    if cookie_token:
        return cookie_token

    # 2. Authorization Bearer 헤더 폴백
    if bearer_token:
        return bearer_token

    return None


def set_auth_cookies(response: Response, access_token: str, refresh_token: str) -> None:
    """응답에 인증 쿠키를 설정합니다."""
    cookie_kwargs = {
        "httponly": True,
        "samesite": settings.COOKIE_SAMESITE,
        "secure": settings.COOKIE_SECURE,
    }
    if settings.COOKIE_DOMAIN:
        cookie_kwargs["domain"] = settings.COOKIE_DOMAIN

    response.set_cookie(
        key="access_token",
        value=access_token,
        max_age=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        path=settings.COOKIE_PATH,
        **cookie_kwargs,
    )
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        max_age=7 * 24 * 60 * 60,  # 7일
        path="/api/auth",
        **cookie_kwargs,
    )


def clear_auth_cookies(response: Response) -> None:
    """응답에서 인증 쿠키를 삭제합니다."""
    cookie_kwargs = {
        "httponly": True,
        "samesite": settings.COOKIE_SAMESITE,
        "secure": settings.COOKIE_SECURE,
    }
    if settings.COOKIE_DOMAIN:
        cookie_kwargs["domain"] = settings.COOKIE_DOMAIN

    response.delete_cookie(key="access_token", path=settings.COOKIE_PATH, **cookie_kwargs)
    response.delete_cookie(key="refresh_token", path="/api/auth", **cookie_kwargs)


async def get_current_user(
    request: Request,
    token: str | None = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User | None:
    """현재 인증된 사용자 (선택적 - None이면 미인증)"""
    effective_token = _extract_token_from_request(request, token)
    if not effective_token:
        return None

    payload = decode_token(effective_token)
    if not payload:
        return None

    # refresh 토큰이 access 토큰으로 사용되는 것을 방지
    if payload.get("type") != "access":
        return None

    username = payload.get("sub")
    if not username:
        return None

    result = await db.execute(select(User).where(User.username == username))
    return result.scalar_one_or_none()


async def require_auth(
    user: User | None = Depends(get_current_user),
) -> User:
    """인증 필수 의존성"""
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="인증이 필요합니다",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


async def require_admin(
    user: User = Depends(require_auth),
) -> User:
    """관리자 권한 필수 의존성"""
    if user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="관리자 권한이 필요합니다",
        )
    return user
