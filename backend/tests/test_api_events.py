"""
Events API Tests

Tests for /api/events endpoints including listing, creating, acknowledging,
filtering, and pagination.
"""

import os
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///"
os.environ["JWT_SECRET_KEY"] = "test-secret-key-for-testing"

import pytest
from datetime import datetime, timezone
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.core.database import engine, Base, async_session
from app.models.user import User
from app.models.event import Event
from app.api.routes.auth import _login_attempts


@pytest.fixture(scope="function")
async def async_client():
    """Setup and teardown for each test."""
    # Reset rate limiter between tests
    _login_attempts.clear()

    # Create tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Yield client
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    # Drop tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


def _extract_cookies(response) -> dict[str, str]:
    """Extract cookie values from Set-Cookie headers."""
    cookies = {}
    for header_value in response.headers.get_list("set-cookie"):
        parts = header_value.split(";")[0]
        if "=" in parts:
            key, value = parts.split("=", 1)
            cookies[key.strip()] = value.strip()
    return cookies


async def create_user_and_login(client: AsyncClient) -> str:
    """Helper to create a user and return auth token."""
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


@pytest.mark.asyncio
async def test_list_events_returns_empty_initially(async_client: AsyncClient):
    """Test list events returns empty array when no events exist (requires auth)."""
    token = await create_user_and_login(async_client)

    response = await async_client.get(
        "/api/events",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["items"] == []
    assert data["total"] == 0
    assert data["page"] == 1


@pytest.mark.asyncio
async def test_list_events_without_auth_returns_401(async_client: AsyncClient):
    """Test list events without authentication returns 401."""
    response = await async_client.get("/api/events")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_create_event_in_db_then_list_returns_it(async_client: AsyncClient):
    """Test creating an event in DB and listing it through API."""
    token = await create_user_and_login(async_client)

    # Create event directly in database
    async with async_session() as session:
        event = Event(
            timestamp=datetime.now(timezone.utc),
            alert_level="warning",
            duration=5.5,
            camera_id="cam_001",
            snapshot_path="/snapshots/test.jpg",
            person_id="person_123",
            confidence=0.85,
            acknowledged=False,
        )
        session.add(event)
        await session.commit()

    # List events through API
    response = await async_client.get(
        "/api/events",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert len(data["items"]) == 1

    event_data = data["items"][0]
    assert event_data["alert_level"] == "warning"
    assert event_data["duration"] == 5.5
    assert event_data["camera_id"] == "cam_001"
    assert event_data["person_id"] == "person_123"
    assert event_data["confidence"] == 0.85
    assert event_data["acknowledged"] is False


@pytest.mark.asyncio
async def test_acknowledge_event(async_client: AsyncClient):
    """Test acknowledging an event."""
    token = await create_user_and_login(async_client)

    # Create event
    async with async_session() as session:
        event = Event(
            timestamp=datetime.now(timezone.utc),
            alert_level="danger",
            duration=15.0,
            camera_id="cam_001",
            acknowledged=False,
        )
        session.add(event)
        await session.commit()
        event_id = event.id

    # Acknowledge event
    response = await async_client.post(
        f"/api/events/{event_id}/acknowledge",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "acknowledged"
    assert data["event_id"] == event_id

    # Verify event is acknowledged
    response = await async_client.get(
        f"/api/events/{event_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    event_data = response.json()
    assert event_data["acknowledged"] is True
    assert event_data["acknowledged_by"] == "testuser"
    assert event_data["acknowledged_at"] is not None


@pytest.mark.asyncio
async def test_filter_events_by_level(async_client: AsyncClient):
    """Test filtering events by alert level."""
    token = await create_user_and_login(async_client)

    # Create multiple events with different levels
    async with async_session() as session:
        events = [
            Event(
                timestamp=datetime.now(timezone.utc),
                alert_level="warning",
                duration=3.0,
                camera_id="cam_001",
            ),
            Event(
                timestamp=datetime.now(timezone.utc),
                alert_level="danger",
                duration=12.0,
                camera_id="cam_001",
            ),
            Event(
                timestamp=datetime.now(timezone.utc),
                alert_level="warning",
                duration=5.0,
                camera_id="cam_002",
            ),
        ]
        for event in events:
            session.add(event)
        await session.commit()

    # Filter by warning level
    response = await async_client.get(
        "/api/events?level=warning",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 2
    assert all(item["alert_level"] == "warning" for item in data["items"])

    # Filter by danger level
    response = await async_client.get(
        "/api/events?level=danger",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["items"][0]["alert_level"] == "danger"


@pytest.mark.asyncio
async def test_pagination_works(async_client: AsyncClient):
    """Test pagination of events."""
    token = await create_user_and_login(async_client)

    # Create 25 events
    async with async_session() as session:
        for i in range(25):
            event = Event(
                timestamp=datetime.now(timezone.utc),
                alert_level="warning" if i % 2 == 0 else "danger",
                duration=float(i),
                camera_id=f"cam_{i:03d}",
            )
            session.add(event)
        await session.commit()

    # Get first page (default size 20)
    response = await async_client.get(
        "/api/events?page=1&size=10",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 25
    assert data["page"] == 1
    assert data["size"] == 10
    assert len(data["items"]) == 10
    assert data["pages"] == 3  # ceil(25 / 10)

    # Get second page
    response = await async_client.get(
        "/api/events?page=2&size=10",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["page"] == 2
    assert len(data["items"]) == 10

    # Get third page (partial)
    response = await async_client.get(
        "/api/events?page=3&size=10",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["page"] == 3
    assert len(data["items"]) == 5  # Only 5 items left
