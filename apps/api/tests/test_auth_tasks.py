import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.asyncio
async def test_register_verify_and_task_flow():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        reg = await client.post("/api/v2/auth/register", json={"email": "test@example.com"})
        assert reg.status_code == 200
        token = reg.json().get("dev_token")
        assert token

        verify = await client.post("/api/v2/auth/verify", json={"token": token})
        assert verify.status_code == 200
        access = verify.json()["access_token"]
        headers = {"Authorization": f"Bearer {access}"}

        prof = await client.put(
            "/api/v2/profile",
            headers=headers,
            json={"wake_name": "James", "display_name": "James"},
        )
        assert prof.status_code == 200

        task = await client.post(
            "/api/v2/tasks",
            headers=headers,
            json={"title": "Call mom", "source": "text"},
        )
        assert task.status_code == 201

        summary = await client.get("/api/v2/tasks/summary", headers=headers)
        assert summary.status_code == 200
        assert summary.json()["total"] >= 1
