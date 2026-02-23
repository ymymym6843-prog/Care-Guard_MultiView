
import pytest
from httpx import AsyncClient

# Uses global async_client fixture from conftest.py

def _extract_cookies(response) -> dict[str, str]:
    """응답에서 Set-Cookie 헤더의 쿠키 값을 추출합니다."""
    cookies = {}
    for header_value in response.headers.get_list("set-cookie"):
        parts = header_value.split(";")[0]
        if "=" in parts:
            key, value = parts.split("=", 1)
            cookies[key.strip()] = value.strip()
    return cookies


@pytest.mark.asyncio
async def test_check_setup_needs_setup_when_no_users(async_client: AsyncClient):
    """Test check-setup returns needs_setup=true when no users exist."""
    response = await async_client.get("/api/auth/check-setup")
    assert response.status_code == 200
    data = response.json()
    assert data["needs_setup"] is True


@pytest.mark.asyncio
async def test_register_first_user_auto_becomes_admin(async_client: AsyncClient):
    """Test first registered user automatically becomes admin."""
    response = await async_client.post(
        "/api/auth/register",
        json={
            "username": "admin_user",
            "password": "password123",
            "full_name": "Admin User",
            "role": "staff",  # Request staff but should become admin
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "created"
    assert data["username"] == "admin_user"
    assert data["role"] == "admin"  # First user becomes admin regardless


@pytest.mark.asyncio
async def test_login_sets_httponly_cookies(async_client: AsyncClient):
    """Test login returns HttpOnly cookies instead of JSON tokens."""
    # Register user
    await async_client.post(
        "/api/auth/register",
        json={
            "username": "testuser",
            "password": "password123",
            "full_name": "Test User",
        },
    )

    # Login
    response = await async_client.post(
        "/api/auth/login",
        data={
            "username": "testuser",
            "password": "password123",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["user"]["username"] == "testuser"
    assert data["user"]["full_name"] == "Test User"
    assert data["user"]["role"] == "admin"  # First user

    # Verify Set-Cookie headers
    cookies = _extract_cookies(response)
    assert "access_token" in cookies
    assert "refresh_token" in cookies

    # Verify HttpOnly is set
    set_cookie_headers = response.headers.get_list("set-cookie")
    for header in set_cookie_headers:
        header_lower = header.lower()
        if "access_token" in header_lower or "refresh_token" in header_lower:
            assert "httponly" in header_lower


@pytest.mark.asyncio
async def test_me_works_with_cookie_auth(async_client: AsyncClient):
    """Test /me endpoint works with cookie-based authentication."""
    # Register and login
    await async_client.post(
        "/api/auth/register",
        json={
            "username": "testuser",
            "password": "password123",
            "full_name": "Test User",
        },
    )

    login_response = await async_client.post(
        "/api/auth/login",
        data={
            "username": "testuser",
            "password": "password123",
        },
    )
    cookies = _extract_cookies(login_response)
    access_token = cookies["access_token"]

    # Get current user info using cookie
    response = await async_client.get(
        "/api/auth/me",
        cookies={"access_token": access_token},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["username"] == "testuser"
    assert data["full_name"] == "Test User"
    assert data["role"] == "admin"
    assert data["is_active"] is True


@pytest.mark.asyncio
async def test_me_works_with_bearer_header_fallback(async_client: AsyncClient):
    """Test /me endpoint still works with Bearer header (backward compat)."""
    # Register and login
    await async_client.post(
        "/api/auth/register",
        json={
            "username": "testuser",
            "password": "password123",
            "full_name": "Test User",
        },
    )

    login_response = await async_client.post(
        "/api/auth/login",
        data={
            "username": "testuser",
            "password": "password123",
        },
    )
    cookies = _extract_cookies(login_response)
    access_token = cookies["access_token"]

    # Get current user info using Authorization header
    response = await async_client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["username"] == "testuser"


@pytest.mark.asyncio
async def test_users_requires_admin_auth(async_client: AsyncClient):
    """Test /users endpoint requires admin authentication."""
    # Register first user (admin)
    await async_client.post(
        "/api/auth/register",
        json={
            "username": "admin",
            "password": "password123",
            "full_name": "Admin",
        },
    )

    login_response = await async_client.post(
        "/api/auth/login",
        data={"username": "admin", "password": "password123"},
    )
    cookies = _extract_cookies(login_response)

    # List users (should succeed with cookie)
    response = await async_client.get(
        "/api/auth/users",
        cookies={"access_token": cookies["access_token"]},
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["username"] == "admin"


@pytest.mark.asyncio
async def test_refresh_with_cookie(async_client: AsyncClient):
    """Test /refresh endpoint works with cookie-based refresh token."""
    # Register and login
    await async_client.post(
        "/api/auth/register",
        json={
            "username": "testuser",
            "password": "password123",
            "full_name": "Test User",
        },
    )

    login_response = await async_client.post(
        "/api/auth/login",
        data={"username": "testuser", "password": "password123"},
    )
    cookies = _extract_cookies(login_response)

    # Refresh tokens using cookie
    response = await async_client.post(
        "/api/auth/refresh",
        cookies={"refresh_token": cookies["refresh_token"]},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"

    # Verify new cookies are set
    new_cookies = _extract_cookies(response)
    assert "access_token" in new_cookies
    assert "refresh_token" in new_cookies


@pytest.mark.asyncio
async def test_logout_clears_cookies(async_client: AsyncClient):
    """Test /logout endpoint clears auth cookies."""
    response = await async_client.post("/api/auth/logout")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"

    # Verify cookies are deleted (max-age=0 or empty)
    set_cookie_headers = response.headers.get_list("set-cookie")
    cookie_names_cleared = set()
    for header in set_cookie_headers:
        header_lower = header.lower()
        if "max-age=0" in header_lower or '=""' in header_lower:
            if "access_token" in header_lower:
                cookie_names_cleared.add("access_token")
            if "refresh_token" in header_lower:
                cookie_names_cleared.add("refresh_token")
    assert "access_token" in cookie_names_cleared
    assert "refresh_token" in cookie_names_cleared


@pytest.mark.asyncio
async def test_register_second_user_requires_admin_auth(async_client: AsyncClient):
    """Test registering second user requires admin authentication."""
    # Register first user (admin)
    await async_client.post(
        "/api/auth/register",
        json={
            "username": "admin",
            "password": "password123",
            "full_name": "Admin",
        },
    )

    # Try to register second user without auth
    response = await async_client.post(
        "/api/auth/register",
        json={
            "username": "staff_user",
            "password": "password123",
            "full_name": "Staff User",
            "role": "staff",
        },
    )
    assert response.status_code == 401
    assert "인증이 필요합니다" in response.json()["detail"]

    # Login as admin
    login_response = await async_client.post(
        "/api/auth/login",
        data={"username": "admin", "password": "password123"},
    )
    cookies = _extract_cookies(login_response)

    # Register second user with admin cookie auth
    response = await async_client.post(
        "/api/auth/register",
        json={
            "username": "staff_user",
            "password": "password123",
            "full_name": "Staff User",
            "role": "staff",
        },
        cookies={"access_token": cookies["access_token"]},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "created"
    assert data["username"] == "staff_user"
    assert data["role"] == "staff"


@pytest.mark.asyncio
async def test_login_with_wrong_password_returns_401(async_client: AsyncClient):
    """Test login with wrong password returns 401 Unauthorized."""
    # Register user
    await async_client.post(
        "/api/auth/register",
        json={
            "username": "testuser",
            "password": "correct_password",
            "full_name": "Test User",
        },
    )

    # Try to login with wrong password
    response = await async_client.post(
        "/api/auth/login",
        data={
            "username": "testuser",
            "password": "wrong_password",
        },
    )
    assert response.status_code == 401
    assert "아이디 또는 비밀번호가 올바르지 않습니다" in response.json()["detail"]
