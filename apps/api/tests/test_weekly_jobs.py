import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.main import app
from app.shared.db import async_session
from app.shared.models import Job


@pytest.mark.asyncio
async def test_enqueue_weekly_summaries_requires_internal_secret():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post("/api/v2/jobs/enqueue-weekly-summaries")
        assert r.status_code == 401


@pytest.mark.asyncio
async def test_enqueue_weekly_summaries_queues_enabled_users():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        reg = await client.post("/api/v2/auth/register", json={"email": "weeklyjobs@example.com"})
        token = reg.json()["dev_token"]
        verify = await client.post("/api/v2/auth/verify", json={"token": token})
        access = verify.json()["access_token"]
        user_id = verify.json()["user_id"]
        headers = {"Authorization": f"Bearer {access}"}

        # First manual send acts as opt-in for scheduled weekly emails.
        send = await client.post("/api/v2/daily/weekly-summary/send", headers=headers)
        assert send.status_code == 200

        enqueue = await client.post(
            "/api/v2/jobs/enqueue-weekly-summaries",
            headers={"X-Internal-Secret": "test-internal-secret"},
        )
        assert enqueue.status_code == 200
        assert enqueue.json()["queued"] >= 1

    async with async_session() as db:
        result = await db.execute(
            select(Job).where(Job.job_type == "weekly_summary_email")
        )
        jobs = list(result.scalars().all())
        assert any((j.payload or {}).get("user_id") == user_id for j in jobs)
