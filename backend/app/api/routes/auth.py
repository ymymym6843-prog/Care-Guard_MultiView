"""
인증 API 라우트
"""

import time
from collections import defaultdict
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, Field
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

# 로그인 시도 제한: IP별 최대 5회/60초
_LOGIN_MAX_ATTEMPTS = 5
_LOGIN_WINDOW_SECONDS = 60
_login_attempts: dict[str, list[float]] = defaultdict(list)

from app.config import settings
from app.core.database import get_db
from app.core.auth import (
    hash_password, verify_password, create_access_token,
    create_refresh_token, decode_token,
    require_auth, get_current_user,
    set_auth_cookies, clear_auth_cookies,
)
from app.models.user import User

router = APIRouter()


class RegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=50, pattern=r"^[a-zA-Z0-9_]+$")
    password: str = Field(min_length=8, max_length=128)
    full_name: str = Field(default="", max_length=100)
    role: Literal["staff", "admin"] = "staff"


def _check_rate_limit(client_ip: str) -> None:
    """IP 기반 로그인 시도 횟수 확인"""
    now = time.time()
    attempts = _login_attempts[client_ip]
    # 윈도우 밖의 시도 제거
    fresh = [t for t in attempts if now - t < _LOGIN_WINDOW_SECONDS]
    if fresh:
        _login_attempts[client_ip] = fresh
    elif client_ip in _login_attempts:
        # 빈 리스트는 키 자체를 삭제하여 메모리 누수 방지
        del _login_attempts[client_ip]
    if len(_login_attempts.get(client_ip, [])) >= _LOGIN_MAX_ATTEMPTS:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="로그인 시도 횟수를 초과했습니다. 잠시 후 다시 시도하세요.",
        )


@router.post("/dev-login")
async def dev_login(
    db: AsyncSession = Depends(get_db),
):
    """개발 모드 자동 로그인 (DEBUG=true & DEV_AUTO_LOGIN=true일 때만 작동)"""
    if not settings.DEBUG or not settings.DEV_AUTO_LOGIN:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Not found",
        )

    # 대상 사용자 결정
    username = settings.DEV_AUTO_LOGIN_USERNAME
    if username:
        result = await db.execute(select(User).where(User.username == username))
        user = result.scalar_one_or_none()
    else:
        # 설정이 없으면 첫 번째 admin 계정 사용
        result = await db.execute(
            select(User).where(User.role == "admin", User.is_active == True).order_by(User.id)
        )
        user = result.scalar_one_or_none()

    # 사용자가 없으면 개발용 admin 계정 자동 생성
    if not user:
        dev_user = User(
            username="dev_admin",
            hashed_password=hash_password("devadmin1234"),
            full_name="Dev Admin",
            role="admin",
            privacy_consented=True,
            privacy_consented_at=datetime.now(timezone.utc),
            privacy_consent_version=settings.PRIVACY_POLICY_VERSION,
        )
        db.add(dev_user)
        await db.commit()
        await db.refresh(dev_user)
        user = dev_user

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="비활성 계정입니다",
        )

    access_token = create_access_token({"sub": user.username, "role": user.role})
    refresh_token = create_refresh_token({"sub": user.username})

    response = JSONResponse(content={
        "status": "ok",
        "dev_auto_login": True,
        "user": {
            "username": user.username,
            "full_name": user.full_name,
            "role": user.role,
        },
    })
    set_auth_cookies(response, access_token, refresh_token)
    return response


@router.post("/login")
async def login(
    request: Request,
    form: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
):
    """로그인 (HttpOnly 쿠키로 JWT 토큰 발급)"""
    client_ip = request.client.host if request.client else "unknown"
    _check_rate_limit(client_ip)
    _login_attempts[client_ip].append(time.time())

    result = await db.execute(select(User).where(User.username == form.username))
    user = result.scalar_one_or_none()

    if not user or not verify_password(form.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="아이디 또는 비밀번호가 올바르지 않습니다",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="비활성 계정입니다",
        )

    access_token = create_access_token({"sub": user.username, "role": user.role})
    refresh_token = create_refresh_token({"sub": user.username})

    response = JSONResponse(content={
        "status": "ok",
        "user": {
            "username": user.username,
            "full_name": user.full_name,
            "role": user.role,
        },
    })
    set_auth_cookies(response, access_token, refresh_token)
    return response


@router.post("/register")
async def register(
    req: RegisterRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User | None = Depends(get_current_user),
):
    """사용자 등록 (첫 번째 사용자는 자유 등록, 이후 관리자 인증 필수)"""
    # 기존 사용자 수 확인
    count_result = await db.execute(select(func.count()).select_from(User))
    user_count = count_result.scalar() or 0

    # 첫 번째 사용자가 아니면 관리자 인증 필수
    if user_count > 0:
        if not current_user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="인증이 필요합니다",
            )
        if current_user.role != "admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="관리자만 사용자를 등록할 수 있습니다",
            )

    # 중복 체크
    existing = await db.execute(select(User).where(User.username == req.username))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="이미 존재하는 사용자명입니다")

    # 첫 번째 사용자는 자동으로 admin
    role = "admin" if user_count == 0 else req.role

    user = User(
        username=req.username,
        hashed_password=hash_password(req.password),
        full_name=req.full_name,
        role=role,
    )
    db.add(user)
    await db.commit()

    return {"status": "created", "username": user.username, "role": role}


@router.get("/check-setup")
async def check_setup(db: AsyncSession = Depends(get_db)):
    """초기 설정 필요 여부 확인 (공개 엔드포인트)"""
    count_result = await db.execute(select(func.count()).select_from(User))
    user_count = count_result.scalar() or 0
    dev_auto = settings.DEBUG and settings.DEV_AUTO_LOGIN
    return {
        "needs_setup": user_count == 0 and not dev_auto,
        "dev_auto_login": dev_auto,
    }


@router.get("/users")
async def list_users(
    current_user: User = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    """사용자 목록 (관리자 전용, 비밀번호 제외)"""
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="관리자만 사용자 목록을 조회할 수 있습니다",
        )

    result = await db.execute(select(User).order_by(User.created_at.desc()))
    users = result.scalars().all()

    return [
        {
            "id": u.id,
            "username": u.username,
            "full_name": u.full_name,
            "role": u.role,
            "is_active": u.is_active,
            "created_at": u.created_at.isoformat() if u.created_at else None,
        }
        for u in users
    ]


@router.get("/me")
async def get_me(user: User = Depends(require_auth)):
    """현재 사용자 정보"""
    return {
        "username": user.username,
        "full_name": user.full_name,
        "role": user.role,
        "is_active": user.is_active,
    }


@router.post("/consent")
async def accept_privacy_consent(
    user: User = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    """개인정보 수집 동의

    현재 PRIVACY_POLICY_VERSION에 대해 동의를 기록합니다.
    정책 버전이 변경되면 재동의가 필요합니다.
    """
    user.privacy_consented = True
    user.privacy_consented_at = datetime.now(timezone.utc)
    user.privacy_consent_version = settings.PRIVACY_POLICY_VERSION
    await db.commit()
    return {"status": "consented", "version": settings.PRIVACY_POLICY_VERSION}


@router.get("/consent-status")
async def get_consent_status(user: User = Depends(require_auth)):
    """개인정보 동의 상태 확인

    현재 사용자의 동의 여부와 재동의 필요 여부를 반환합니다.
    """
    return {
        "consented": user.privacy_consented,
        "version": user.privacy_consent_version,
        "required_version": settings.PRIVACY_POLICY_VERSION,
        "needs_consent": not user.privacy_consented or user.privacy_consent_version != settings.PRIVACY_POLICY_VERSION,
    }


@router.post("/refresh")
async def refresh(request: Request):
    """리프레시 토큰으로 새 액세스 토큰 발급 (쿠키에서 읽기, JSON body 폴백)"""
    # 1. 쿠키에서 리프레시 토큰 추출
    token = request.cookies.get("refresh_token")

    # 2. JSON body 폴백
    if not token:
        try:
            body = await request.json()
            token = body.get("refresh_token")
        except Exception:
            pass

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="리프레시 토큰이 없습니다",
        )

    payload = decode_token(token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="유효하지 않은 리프레시 토큰입니다",
        )

    if payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="리프레시 토큰이 아닙니다",
        )

    username = payload.get("sub")
    if not username:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="토큰에 사용자 정보가 없습니다",
        )

    user = None
    async for db in get_db():
        result = await db.execute(select(User).where(User.username == username))
        user = result.scalar_one_or_none()
        break

    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="사용자를 찾을 수 없거나 비활성 계정입니다",
        )

    new_access_token = create_access_token({"sub": user.username, "role": user.role})
    new_refresh_token = create_refresh_token({"sub": user.username})

    response = JSONResponse(content={
        "status": "ok",
    })
    set_auth_cookies(response, new_access_token, new_refresh_token)
    return response


@router.post("/logout")
async def logout():
    """로그아웃 (인증 쿠키 삭제)"""
    response = JSONResponse(content={"status": "ok"})
    clear_auth_cookies(response)
    return response
