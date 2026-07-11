"""Round 8 regression coverage: the daily check-in prompt used to be a
static, context-free string every time it fired ("Just checking in -- how
are you feeling?"). It now references today's actual task progress, mirroring
the morning/evening payload pattern already used elsewhere in this router.
"""

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.asyncio
async def test_checkin_payload_with_no_tasks_offers_to_plan():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        reg = await client.post("/api/v2/auth/register", json={"email": "checkin-empty@example.com"})
        verify = await client.post("/api/v2/auth/verify", json={"token": reg.json()["dev_token"]})
        headers = {"Authorization": f"Bearer {verify.json()['access_token']}"}

        r = await client.get("/api/v2/daily/checkin-payload", headers=headers)
        assert r.status_code == 200
        body = r.json()
        assert "feeling" in body["prompt"].lower()
        assert "plan" in body["prompt"].lower()


@pytest.mark.asyncio
async def test_checkin_payload_with_open_tasks_references_progress():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        reg = await client.post("/api/v2/auth/register", json={"email": "checkin-tasks@example.com"})
        verify = await client.post("/api/v2/auth/verify", json={"token": reg.json()["dev_token"]})
        headers = {"Authorization": f"Bearer {verify.json()['access_token']}"}

        await client.post("/api/v2/tasks", headers=headers, json={"title": "Write report"})
        await client.post("/api/v2/tasks", headers=headers, json={"title": "Call dentist"})

        r = await client.get("/api/v2/daily/checkin-payload", headers=headers)
        assert r.status_code == 200
        prompt = r.json()["prompt"].lower()
        # No tasks are done yet -- should mention the open count, not a done/total split.
        assert "still open today" in prompt
        assert "2" in prompt
