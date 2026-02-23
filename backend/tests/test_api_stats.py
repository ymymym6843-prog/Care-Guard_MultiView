"""
Statistics API Tests

Tests for /api/stats endpoints including summary, daily, hourly,
and by-person statistics.
"""

import os
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///"
os.environ["JWT_SECRET_KEY"] = "test-secret-key-for-testing"

import pytest
from datetime import datetime, timedelta, timezone
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
async def test_summary_returns_zeros_when_no_events(async_client: AsyncClient):
    """Test summary endpoint returns zeros when no events exist."""
    token = await create_user_and_login(async_client)

    response = await async_client.get(
        "/api/stats/summary",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total_events"] == 0
    assert data["danger_events"] == 0
    assert data["warning_events"] == 0
    assert data["acknowledged"] == 0
    assert data["unacknowledged"] == 0
    assert data["avg_response_seconds"] == 0.0
    assert data["acknowledgment_rate"] == 0.0


@pytest.mark.asyncio
async def test_daily_returns_empty_when_no_events(async_client: AsyncClient):
    """Test daily stats returns empty list when no events exist."""
    token = await create_user_and_login(async_client)

    response = await async_client.get(
        "/api/stats/daily",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data == []


@pytest.mark.asyncio
async def test_hourly_returns_24_entries_even_with_no_data(async_client: AsyncClient):
    """Test hourly stats returns 24 entries (0-23 hours) even with no events."""
    token = await create_user_and_login(async_client)

    response = await async_client.get(
        "/api/stats/hourly",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 24

    # Verify all hours 0-23 are present
    hours = {item["hour"] for item in data}
    assert hours == set(range(24))

    # All counts should be 0
    assert all(item["count"] == 0 for item in data)


@pytest.mark.asyncio
async def test_summary_reflects_correct_counts_with_events(async_client: AsyncClient):
    """Test summary stats reflect correct counts when events exist."""
    token = await create_user_and_login(async_client)

    # Create various events
    async with async_session() as session:
        now = datetime.now(timezone.utc)

        # 5 warning events
        for i in range(5):
            event = Event(
                timestamp=now - timedelta(days=i),
                alert_level="warning",
                duration=3.0 + i,
                camera_id="cam_001",
                acknowledged=(i < 2),  # First 2 acknowledged
                acknowledged_by="testuser" if i < 2 else None,
                acknowledged_at=now if i < 2 else None,
            )
            session.add(event)

        # 3 danger events
        for i in range(3):
            event = Event(
                timestamp=now - timedelta(days=i),
                alert_level="danger",
                duration=12.0 + i,
                camera_id="cam_001",
                acknowledged=(i < 1),  # First 1 acknowledged
                acknowledged_by="testuser" if i < 1 else None,
                acknowledged_at=now if i < 1 else None,
            )
            session.add(event)

        await session.commit()

    # Get summary
    response = await async_client.get(
        "/api/stats/summary?days=30",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()

    assert data["total_events"] == 8  # 5 warnings + 3 dangers
    assert data["danger_events"] == 3
    assert data["warning_events"] == 5
    assert data["acknowledged"] == 3  # 2 warnings + 1 danger
    assert data["unacknowledged"] == 5
    assert data["acknowledgment_rate"] == pytest.approx(37.5, rel=0.1)  # 3/8 * 100


@pytest.mark.asyncio
async def test_daily_stats_with_events(async_client: AsyncClient):
    """Test daily stats correctly aggregate events by date."""
    token = await create_user_and_login(async_client)

    # Create events on different days
    async with async_session() as session:
        now = datetime.now(timezone.utc)

        # Today: 2 warnings, 1 danger
        for _ in range(2):
            session.add(Event(
                timestamp=now,
                alert_level="warning",
                duration=3.0,
                camera_id="cam_001",
            ))
        session.add(Event(
            timestamp=now,
            alert_level="danger",
            duration=12.0,
            camera_id="cam_001",
        ))

        # Yesterday: 1 warning
        session.add(Event(
            timestamp=now - timedelta(days=1),
            alert_level="warning",
            duration=4.0,
            camera_id="cam_001",
        ))

        await session.commit()

    # Get daily stats
    response = await async_client.get(
        "/api/stats/daily?days=7",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()

    # Should have data for 2 days
    assert len(data) == 2

    # Find today's stats
    today_stats = None
    for day_stat in data:
        if "warning" in day_stat and day_stat.get("warning", 0) == 2:
            today_stats = day_stat
            break

    assert today_stats is not None
    assert today_stats["warning"] == 2
    assert today_stats["danger"] == 1
    assert today_stats["total"] == 3


@pytest.mark.asyncio
async def test_hourly_stats_with_events(async_client: AsyncClient):
    """Test hourly stats correctly aggregate events by hour."""
    token = await create_user_and_login(async_client)

    # Create events at specific hours
    async with async_session() as session:
        now = datetime.now(timezone.utc)

        # Create 3 events at hour 9 (9 AM)
        hour_9 = now.replace(hour=9, minute=0, second=0, microsecond=0)
        for _ in range(3):
            session.add(Event(
                timestamp=hour_9,
                alert_level="warning",
                duration=3.0,
                camera_id="cam_001",
            ))

        # Create 2 events at hour 14 (2 PM)
        hour_14 = now.replace(hour=14, minute=0, second=0, microsecond=0)
        for _ in range(2):
            session.add(Event(
                timestamp=hour_14,
                alert_level="danger",
                duration=12.0,
                camera_id="cam_001",
            ))

        await session.commit()

    # Get hourly stats
    response = await async_client.get(
        "/api/stats/hourly?days=7",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()

    assert len(data) == 24

    # Find hour 9 and 14
    hour_9_data = next(item for item in data if item["hour"] == 9)
    hour_14_data = next(item for item in data if item["hour"] == 14)

    assert hour_9_data["count"] == 3
    assert hour_14_data["count"] == 2

    # Other hours should have 0
    hour_0_data = next(item for item in data if item["hour"] == 0)
    assert hour_0_data["count"] == 0


@pytest.mark.asyncio
async def test_by_person_stats(async_client: AsyncClient):
    """Test by-person stats correctly aggregate events by person_id."""
    token = await create_user_and_login(async_client)

    # Create events for different people
    async with async_session() as session:
        now = datetime.now(timezone.utc)

        # Person A: 3 events (2 danger, 1 warning)
        for i in range(3):
            session.add(Event(
                timestamp=now - timedelta(hours=i),
                alert_level="danger" if i < 2 else "warning",
                duration=10.0 + i,
                camera_id="cam_001",
                person_id="person_A",
            ))

        # Person B: 2 events (both warning)
        for i in range(2):
            session.add(Event(
                timestamp=now - timedelta(hours=i),
                alert_level="warning",
                duration=5.0 + i,
                camera_id="cam_001",
                person_id="person_B",
            ))

        # Event without person_id (should be excluded)
        session.add(Event(
            timestamp=now,
            alert_level="warning",
            duration=3.0,
            camera_id="cam_001",
            person_id=None,
        ))

        await session.commit()

    # Get by-person stats
    response = await async_client.get(
        "/api/stats/by-person?days=30",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()

    # Should have 2 people (person_id=None is excluded)
    assert len(data) == 2

    # Find person A and B
    person_a = next(p for p in data if p["person_id"] == "person_A")
    person_b = next(p for p in data if p["person_id"] == "person_B")

    assert person_a["total_events"] == 3
    assert person_a["danger_count"] == 2
    assert person_a["avg_duration"] == pytest.approx(11.0, rel=0.1)  # (10+11+12)/3

    assert person_b["total_events"] == 2
    assert person_b["danger_count"] == 0
    assert person_b["avg_duration"] == pytest.approx(5.5, rel=0.1)  # (5+6)/2
