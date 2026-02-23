"""
Rooms API Tests

Tests for /api/rooms endpoints including CRUD, camera mapping,
and room_id filtering on events/stats.
"""

import os
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///"
os.environ["JWT_SECRET_KEY"] = "test-secret-key-for-testing"

import pytest
from datetime import datetime, timezone
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.core.database import engine, Base, async_session
from app.models.event import Event
from app.models.room import Room, RoomCameraMapping
from app.api.routes.auth import _login_attempts


@pytest.fixture(scope="function")
async def async_client():
    """Setup and teardown for each test."""
    _login_attempts.clear()

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


def _extract_cookies(response) -> dict[str, str]:
    cookies = {}
    for header_value in response.headers.get_list("set-cookie"):
        parts = header_value.split(";")[0]
        if "=" in parts:
            key, value = parts.split("=", 1)
            cookies[key.strip()] = value.strip()
    return cookies


async def create_user_and_login(client: AsyncClient) -> str:
    await client.post(
        "/api/auth/register",
        json={
            "username": "testuser",
            "password": "password123",
            "full_name": "Test User",
        },
    )
    login_response = await client.post(
        "/api/auth/login",
        data={"username": "testuser", "password": "password123"},
    )
    cookies = _extract_cookies(login_response)
    return cookies["access_token"]


# ---- Room CRUD Tests ----

@pytest.mark.asyncio
async def test_list_rooms_empty(async_client: AsyncClient):
    """빈 공간 목록 조회"""
    token = await create_user_and_login(async_client)
    response = await async_client.get(
        "/api/rooms",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["items"] == []
    assert data["total"] == 0


@pytest.mark.asyncio
async def test_create_room(async_client: AsyncClient):
    """공간 생성"""
    token = await create_user_and_login(async_client)
    response = await async_client.post(
        "/api/rooms",
        json={"name": "대기실 A", "description": "1층 대기실"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "대기실 A"
    assert data["description"] == "1층 대기실"
    assert data["is_active"] is True
    assert data["camera_count"] == 0


@pytest.mark.asyncio
async def test_create_and_list_rooms(async_client: AsyncClient):
    """공간 생성 후 목록 조회"""
    token = await create_user_and_login(async_client)

    await async_client.post(
        "/api/rooms",
        json={"name": "대기실 A"},
        headers={"Authorization": f"Bearer {token}"},
    )
    await async_client.post(
        "/api/rooms",
        json={"name": "302호"},
        headers={"Authorization": f"Bearer {token}"},
    )

    response = await async_client.get(
        "/api/rooms",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 2
    names = [r["name"] for r in data["items"]]
    assert "대기실 A" in names
    assert "302호" in names


@pytest.mark.asyncio
async def test_update_room(async_client: AsyncClient):
    """공간 수정"""
    token = await create_user_and_login(async_client)

    create_res = await async_client.post(
        "/api/rooms",
        json={"name": "대기실 A"},
        headers={"Authorization": f"Bearer {token}"},
    )
    room_id = create_res.json()["id"]

    update_res = await async_client.patch(
        f"/api/rooms/{room_id}",
        json={"name": "대기실 B", "description": "2층"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert update_res.status_code == 200
    data = update_res.json()
    assert data["name"] == "대기실 B"
    assert data["description"] == "2층"


@pytest.mark.asyncio
async def test_delete_room(async_client: AsyncClient):
    """공간 삭제"""
    token = await create_user_and_login(async_client)

    create_res = await async_client.post(
        "/api/rooms",
        json={"name": "삭제용"},
        headers={"Authorization": f"Bearer {token}"},
    )
    room_id = create_res.json()["id"]

    delete_res = await async_client.delete(
        f"/api/rooms/{room_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert delete_res.status_code == 200
    assert delete_res.json()["success"] is True

    # 삭제 후 목록에 없어야 함
    list_res = await async_client.get(
        "/api/rooms",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert list_res.json()["total"] == 0


@pytest.mark.asyncio
async def test_delete_nonexistent_room_404(async_client: AsyncClient):
    """존재하지 않는 공간 삭제 → 404"""
    token = await create_user_and_login(async_client)
    response = await async_client.delete(
        "/api/rooms/999",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 404


# ---- Camera Mapping Tests ----

@pytest.mark.asyncio
async def test_assign_cameras_to_room(async_client: AsyncClient):
    """카메라 배정"""
    token = await create_user_and_login(async_client)

    create_res = await async_client.post(
        "/api/rooms",
        json={"name": "대기실 A"},
        headers={"Authorization": f"Bearer {token}"},
    )
    room_id = create_res.json()["id"]

    # 카메라 배정
    assign_res = await async_client.put(
        f"/api/rooms/{room_id}/cameras",
        json={"camera_ids": ["cam0", "cam1"]},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert assign_res.status_code == 200
    assert assign_res.json()["camera_ids"] == ["cam0", "cam1"]

    # 카메라 조회
    cameras_res = await async_client.get(
        f"/api/rooms/{room_id}/cameras",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert cameras_res.status_code == 200
    assert set(cameras_res.json()["camera_ids"]) == {"cam0", "cam1"}


@pytest.mark.asyncio
async def test_reassign_cameras_replaces(async_client: AsyncClient):
    """카메라 재배정 시 기존 매핑 교체"""
    token = await create_user_and_login(async_client)

    create_res = await async_client.post(
        "/api/rooms",
        json={"name": "대기실 A"},
        headers={"Authorization": f"Bearer {token}"},
    )
    room_id = create_res.json()["id"]

    # 첫 배정
    await async_client.put(
        f"/api/rooms/{room_id}/cameras",
        json={"camera_ids": ["cam0", "cam1"]},
        headers={"Authorization": f"Bearer {token}"},
    )

    # 재배정
    await async_client.put(
        f"/api/rooms/{room_id}/cameras",
        json={"camera_ids": ["cam2"]},
        headers={"Authorization": f"Bearer {token}"},
    )

    cameras_res = await async_client.get(
        f"/api/rooms/{room_id}/cameras",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert cameras_res.json()["camera_ids"] == ["cam2"]


@pytest.mark.asyncio
async def test_delete_room_removes_mappings(async_client: AsyncClient):
    """공간 삭제 시 카메라 매핑도 삭제"""
    token = await create_user_and_login(async_client)

    create_res = await async_client.post(
        "/api/rooms",
        json={"name": "대기실 A"},
        headers={"Authorization": f"Bearer {token}"},
    )
    room_id = create_res.json()["id"]

    await async_client.put(
        f"/api/rooms/{room_id}/cameras",
        json={"camera_ids": ["cam0", "cam1"]},
        headers={"Authorization": f"Bearer {token}"},
    )

    await async_client.delete(
        f"/api/rooms/{room_id}",
        headers={"Authorization": f"Bearer {token}"},
    )

    # DB에 매핑이 남아있지 않아야 함
    async with async_session() as session:
        from sqlalchemy import select, func
        count_result = await session.execute(
            select(func.count()).select_from(RoomCameraMapping)
            .where(RoomCameraMapping.room_id == room_id)
        )
        assert count_result.scalar() == 0


# ---- Room-based Event Filtering Tests ----

@pytest.mark.asyncio
async def test_events_filter_by_room_id(async_client: AsyncClient):
    """이벤트를 room_id로 필터링"""
    token = await create_user_and_login(async_client)

    # 공간 생성 + 카메라 배정
    create_res = await async_client.post(
        "/api/rooms",
        json={"name": "대기실 A"},
        headers={"Authorization": f"Bearer {token}"},
    )
    room_id = create_res.json()["id"]

    await async_client.put(
        f"/api/rooms/{room_id}/cameras",
        json={"camera_ids": ["cam0"]},
        headers={"Authorization": f"Bearer {token}"},
    )

    # 이벤트 생성 (cam0 = 대기실A, cam1 = 미배정)
    async with async_session() as session:
        session.add(Event(
            timestamp=datetime.now(timezone.utc),
            alert_level="warning", duration=3.0,
            camera_id="cam0", room_id=room_id,
        ))
        session.add(Event(
            timestamp=datetime.now(timezone.utc),
            alert_level="danger", duration=10.0,
            camera_id="cam1",
        ))
        await session.commit()

    # room_id 필터 → cam0 이벤트만
    response = await async_client.get(
        f"/api/events?room_id={room_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["items"][0]["camera_id"] == "cam0"

    # room_id 없으면 전체
    response_all = await async_client.get(
        "/api/events",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response_all.json()["total"] == 2


# ---- Room-based Stats Filtering Tests ----

@pytest.mark.asyncio
async def test_stats_summary_filter_by_room_id(async_client: AsyncClient):
    """통계 요약을 room_id로 필터링"""
    token = await create_user_and_login(async_client)

    # 공간 생성 + 카메라 배정
    create_res = await async_client.post(
        "/api/rooms",
        json={"name": "대기실 A"},
        headers={"Authorization": f"Bearer {token}"},
    )
    room_id = create_res.json()["id"]

    await async_client.put(
        f"/api/rooms/{room_id}/cameras",
        json={"camera_ids": ["cam0"]},
        headers={"Authorization": f"Bearer {token}"},
    )

    # 이벤트 생성
    async with async_session() as session:
        session.add(Event(
            timestamp=datetime.now(timezone.utc),
            alert_level="danger", duration=10.0,
            camera_id="cam0", room_id=room_id,
        ))
        session.add(Event(
            timestamp=datetime.now(timezone.utc),
            alert_level="warning", duration=3.0,
            camera_id="cam1",
        ))
        await session.commit()

    # room_id 필터 → cam0 이벤트만 카운트
    response = await async_client.get(
        f"/api/stats/summary?days=30&room_id={room_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total_events"] == 1
    assert data["danger_events"] == 1

    # 전체 → 2개
    response_all = await async_client.get(
        "/api/stats/summary?days=30",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response_all.json()["total_events"] == 2


@pytest.mark.asyncio
async def test_room_camera_count_in_list(async_client: AsyncClient):
    """공간 목록에 카메라 수 포함"""
    token = await create_user_and_login(async_client)

    create_res = await async_client.post(
        "/api/rooms",
        json={"name": "대기실 A"},
        headers={"Authorization": f"Bearer {token}"},
    )
    room_id = create_res.json()["id"]

    await async_client.put(
        f"/api/rooms/{room_id}/cameras",
        json={"camera_ids": ["cam0", "cam1", "cam2"]},
        headers={"Authorization": f"Bearer {token}"},
    )

    response = await async_client.get(
        "/api/rooms",
        headers={"Authorization": f"Bearer {token}"},
    )
    data = response.json()
    assert data["items"][0]["camera_count"] == 3


@pytest.mark.asyncio
async def test_rooms_require_auth(async_client: AsyncClient):
    """인증 없이 공간 API 접근 → 401"""
    response = await async_client.get("/api/rooms")
    assert response.status_code == 401

    response = await async_client.post(
        "/api/rooms", json={"name": "test"}
    )
    assert response.status_code == 401
