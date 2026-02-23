
import pytest
from httpx import AsyncClient

@pytest.mark.asyncio
async def test_read_main(async_client: AsyncClient):
    response = await async_client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"

@pytest.mark.asyncio
async def test_login(async_client: AsyncClient):
    # Test login with form data (required by OAuth2PasswordRequestForm)
    # Note: The user must exist. Using 'admin' which is created if using admin_token, 
    # but here we might need to register first if we want independent test.
    # However, to keep it simple and since we want to test 'login' specifically:
    
    # 1. Register a user first
    register_data = {
        "username": "testlimit",
        "password": "password123",
        "full_name": "Test Limit"
    }
    await async_client.post("/api/auth/register", json=register_data)
    
    # 2. Try login
    login_data = {
        "username": "testlimit",
        "password": "password123"
    }
    # Use data= for form-urlencoded (FastAPI depends on python-multipart)
    response = await async_client.post("/api/auth/login", data=login_data)
    
    # 200 OK expected
    assert response.status_code == 200

@pytest.mark.asyncio
async def test_get_models(async_client: AsyncClient, admin_token: str):
    # The client is already authenticated because 'admin_token' fixture used it to login.
    # We must clear cookies to test unauthenticated access.
    async_client.cookies.clear()

    # 1. Test unauthenticated - Expect 401 Not Authenticated (or 307 if slash missing, but we fix slash now)
    # Note: Adding slash to avoid 307 Temporary Redirect
    response = await async_client.get("/api/models/") 
    
    # Check if it's 401
    assert response.status_code == 401

    # 2. Test authenticated
    # We can use the token string to set cookies again, or just re-login.
    # But admin_token fixture returned the token string.
    # Let's set the cookie manually.
    cookies = {"access_token": admin_token}
    response = await async_client.get("/api/models/", cookies=cookies)
    
    if response.status_code != 200:
         # Fallback check
         response = await async_client.get("/api/models/", headers={"Authorization": f"Bearer {admin_token}"})

    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    if len(data) > 0:
        model = data[0]
        assert "name" in model
        assert "size" in model
        assert "is_active" in model

@pytest.mark.asyncio
async def test_demo_status(async_client: AsyncClient, admin_token: str):
    # /api/demo likely requires auth
    # Pass cookie with token
    cookies = {"access_token": admin_token} if admin_token else {}
    
    # The fixture admin_token returns the token string if found.
    # logic in listener:
    response = await async_client.get("/api/demo", cookies=cookies)
    
    # It might still be 401 if admin_token failed to generate (e.g. login failed)
    # But with our fix it should work.
    if response.status_code == 401:
        # Fallback check if headers needed (though app uses cookies mostly)
        response = await async_client.get("/api/demo", headers={"Authorization": f"Bearer {admin_token}"})
        
    assert response.status_code == 200
    data = response.json()
    assert "demo_mode" in data
    assert "available" in data
