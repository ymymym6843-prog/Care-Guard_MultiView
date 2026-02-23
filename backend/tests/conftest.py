import os
import sys
import pytest
from httpx import AsyncClient, ASGITransport
from typing import AsyncGenerator, Generator

# 1. Set environment variables BEFORE importing app
# This ensures the app uses the in-memory DB and test settings
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///"
os.environ["JWT_SECRET_KEY"] = "test-secret-key-for-testing"
os.environ["DEBUG"] = "false"
os.environ["DEV_AUTO_LOGIN"] = "false"

# Add backend to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.main import app
from app.config import settings
from app.core.database import engine, Base
from app.api.routes.auth import _login_attempts

@pytest.fixture(scope="function")
async def async_client() -> AsyncGenerator[AsyncClient, None]:
    """
    Setup and teardown for each test.
    Creates a fresh in-memory database and returns an async client.
    """
    # Reset state
    _login_attempts.clear()

    # Create tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Create client
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    # Drop tables (cleanup)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

@pytest.fixture()
def mock_landmarks_standing():
    """Normal standing pose with 33 MediaPipe-format landmarks."""
    return [
        {"x": 0.5, "y": 0.15, "z": 0.0, "visibility": 0.9},  # 0: NOSE
        {"x": 0.49, "y": 0.13, "z": 0.0, "visibility": 0.9},  # 1: LEFT_EYE_INNER
        {"x": 0.48, "y": 0.13, "z": 0.0, "visibility": 0.9},  # 2: LEFT_EYE
        {"x": 0.47, "y": 0.13, "z": 0.0, "visibility": 0.9},  # 3: LEFT_EYE_OUTER
        {"x": 0.51, "y": 0.13, "z": 0.0, "visibility": 0.9},  # 4: RIGHT_EYE_INNER
        {"x": 0.52, "y": 0.13, "z": 0.0, "visibility": 0.9},  # 5: RIGHT_EYE
        {"x": 0.53, "y": 0.13, "z": 0.0, "visibility": 0.9},  # 6: RIGHT_EYE_OUTER
        {"x": 0.47, "y": 0.14, "z": 0.0, "visibility": 0.9},  # 7: LEFT_EAR
        {"x": 0.53, "y": 0.14, "z": 0.0, "visibility": 0.9},  # 8: RIGHT_EAR
        {"x": 0.49, "y": 0.17, "z": 0.0, "visibility": 0.9},  # 9: MOUTH_LEFT
        {"x": 0.51, "y": 0.17, "z": 0.0, "visibility": 0.9},  # 10: MOUTH_RIGHT
        {"x": 0.43, "y": 0.30, "z": 0.0, "visibility": 0.9},  # 11: LEFT_SHOULDER
        {"x": 0.57, "y": 0.30, "z": 0.0, "visibility": 0.9},  # 12: RIGHT_SHOULDER
        {"x": 0.40, "y": 0.45, "z": 0.0, "visibility": 0.9},  # 13: LEFT_ELBOW
        {"x": 0.60, "y": 0.45, "z": 0.0, "visibility": 0.9},  # 14: RIGHT_ELBOW
        {"x": 0.38, "y": 0.55, "z": 0.0, "visibility": 0.9},  # 15: LEFT_WRIST
        {"x": 0.62, "y": 0.55, "z": 0.0, "visibility": 0.9},  # 16: RIGHT_WRIST
        {"x": 0.37, "y": 0.56, "z": 0.0, "visibility": 0.9},  # 17: LEFT_PINKY
        {"x": 0.63, "y": 0.56, "z": 0.0, "visibility": 0.9},  # 18: RIGHT_PINKY
        {"x": 0.36, "y": 0.56, "z": 0.0, "visibility": 0.9},  # 19: LEFT_INDEX
        {"x": 0.64, "y": 0.56, "z": 0.0, "visibility": 0.9},  # 20: RIGHT_INDEX
        {"x": 0.37, "y": 0.57, "z": 0.0, "visibility": 0.9},  # 21: LEFT_THUMB
        {"x": 0.63, "y": 0.57, "z": 0.0, "visibility": 0.9},  # 22: RIGHT_THUMB
        {"x": 0.45, "y": 0.55, "z": 0.0, "visibility": 0.9},  # 23: LEFT_HIP
        {"x": 0.55, "y": 0.55, "z": 0.0, "visibility": 0.9},  # 24: RIGHT_HIP
        {"x": 0.44, "y": 0.72, "z": 0.0, "visibility": 0.9},  # 25: LEFT_KNEE
        {"x": 0.56, "y": 0.72, "z": 0.0, "visibility": 0.9},  # 26: RIGHT_KNEE
        {"x": 0.43, "y": 0.90, "z": 0.0, "visibility": 0.9},  # 27: LEFT_ANKLE
        {"x": 0.57, "y": 0.90, "z": 0.0, "visibility": 0.9},  # 28: RIGHT_ANKLE
        {"x": 0.42, "y": 0.92, "z": 0.0, "visibility": 0.9},  # 29: LEFT_HEEL
        {"x": 0.58, "y": 0.92, "z": 0.0, "visibility": 0.9},  # 30: RIGHT_HEEL
        {"x": 0.41, "y": 0.94, "z": 0.0, "visibility": 0.9},  # 31: LEFT_FOOT_INDEX
        {"x": 0.59, "y": 0.94, "z": 0.0, "visibility": 0.9},  # 32: RIGHT_FOOT_INDEX
    ]


@pytest.fixture()
def mock_landmarks_fallen():
    """Fallen pose: body horizontal on ground, head below hips.

    Triggers both C1 (head-hip inverted) and C3 (horizontal body angle)
    so composite rule_score >= 0.5 on a single frame.
    Body lies flat at y≈0.70, head at x=0.15 (left), hips at x=0.65 (right).
    """
    return [
        {"x": 0.15, "y": 0.72, "z": 0.0, "visibility": 0.9},  # 0: NOSE
        {"x": 0.14, "y": 0.71, "z": 0.0, "visibility": 0.9},  # 1
        {"x": 0.13, "y": 0.71, "z": 0.0, "visibility": 0.9},  # 2
        {"x": 0.12, "y": 0.71, "z": 0.0, "visibility": 0.9},  # 3
        {"x": 0.16, "y": 0.71, "z": 0.0, "visibility": 0.9},  # 4
        {"x": 0.17, "y": 0.71, "z": 0.0, "visibility": 0.9},  # 5
        {"x": 0.18, "y": 0.71, "z": 0.0, "visibility": 0.9},  # 6
        {"x": 0.12, "y": 0.72, "z": 0.0, "visibility": 0.9},  # 7
        {"x": 0.18, "y": 0.72, "z": 0.0, "visibility": 0.9},  # 8
        {"x": 0.14, "y": 0.73, "z": 0.0, "visibility": 0.9},  # 9
        {"x": 0.16, "y": 0.73, "z": 0.0, "visibility": 0.9},  # 10
        {"x": 0.30, "y": 0.70, "z": 0.0, "visibility": 0.9},  # 11: LEFT_SHOULDER
        {"x": 0.35, "y": 0.70, "z": 0.0, "visibility": 0.9},  # 12: RIGHT_SHOULDER
        {"x": 0.25, "y": 0.72, "z": 0.0, "visibility": 0.9},  # 13
        {"x": 0.40, "y": 0.72, "z": 0.0, "visibility": 0.9},  # 14
        {"x": 0.20, "y": 0.74, "z": 0.0, "visibility": 0.9},  # 15
        {"x": 0.45, "y": 0.74, "z": 0.0, "visibility": 0.9},  # 16
        {"x": 0.19, "y": 0.75, "z": 0.0, "visibility": 0.9},  # 17
        {"x": 0.46, "y": 0.75, "z": 0.0, "visibility": 0.9},  # 18
        {"x": 0.18, "y": 0.75, "z": 0.0, "visibility": 0.9},  # 19
        {"x": 0.47, "y": 0.75, "z": 0.0, "visibility": 0.9},  # 20
        {"x": 0.19, "y": 0.76, "z": 0.0, "visibility": 0.9},  # 21
        {"x": 0.46, "y": 0.76, "z": 0.0, "visibility": 0.9},  # 22
        {"x": 0.55, "y": 0.68, "z": 0.0, "visibility": 0.9},  # 23: LEFT_HIP
        {"x": 0.60, "y": 0.68, "z": 0.0, "visibility": 0.9},  # 24: RIGHT_HIP
        {"x": 0.65, "y": 0.70, "z": 0.0, "visibility": 0.9},  # 25
        {"x": 0.70, "y": 0.70, "z": 0.0, "visibility": 0.9},  # 26
        {"x": 0.75, "y": 0.72, "z": 0.0, "visibility": 0.9},  # 27
        {"x": 0.80, "y": 0.72, "z": 0.0, "visibility": 0.9},  # 28
        {"x": 0.77, "y": 0.73, "z": 0.0, "visibility": 0.9},  # 29
        {"x": 0.82, "y": 0.73, "z": 0.0, "visibility": 0.9},  # 30
        {"x": 0.79, "y": 0.74, "z": 0.0, "visibility": 0.9},  # 31
        {"x": 0.84, "y": 0.74, "z": 0.0, "visibility": 0.9},  # 32
    ]


@pytest.fixture(scope="function")
async def admin_token(async_client: AsyncClient) -> str:
    """
    Creates an admin user and returns a valid access token.
    """
    # Register admin user
    register_data = {
        "username": "admin",
        "password": "adminpassword",
        "full_name": "Admin User"
    }
    # Register (first user becomes admin automatically)
    await async_client.post("/api/auth/register", json=register_data)

    # Login
    login_data = {
        "username": "admin",
        "password": "adminpassword"
    }
    response = await async_client.post("/api/auth/login", data=login_data)
    
    if response.status_code == 200:
        # Extract token from cookies or response (depending on implementation)
        # Auth endpoints return cookies, but we might need the token string for headers if needed
        # But typically the client tracks cookies automatically.
        # This fixture returns the token string if found in cookies.
        cookies = response.cookies
        return cookies.get("access_token")
    return None
