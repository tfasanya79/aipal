import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.asyncio
async def test_session_events_post_export_and_recent():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        reg = await client.post("/api/v2/auth/register", json={"email": "sessions@example.com"})
        token = reg.json().get("dev_token")
        verify = await client.post("/api/v2/auth/verify", json={"token": token})
        headers = {"Authorization": f"Bearer {verify.json()['access_token']}"}

        session_id = "test-session-abc"
        post = await client.post(
            "/api/v2/sessions/events",
            headers=headers,
            json={
                "session_id": session_id,
                "phase_tag": "pytest",
                "events": [
                    {"event_type": "live_start", "payload": {"build": "39"}},
                    {"event_type": "segment_upload", "payload": {"bytes": 1200}},
                ],
            },
        )
        assert post.status_code == 200
        assert post.json()["recorded"] == 2

        recent = await client.get("/api/v2/sessions/recent", headers=headers)
        assert recent.status_code == 200
        items = recent.json()
        assert any(i["session_id"] == session_id for i in items)

        export = await client.get(f"/api/v2/sessions/{session_id}/export", headers=headers)
        assert export.status_code == 200
        body = export.json()
        assert body["session_id"] == session_id
        assert body["phase_tag"] == "pytest"
        assert len(body["events"]) == 2
        assert body["events"][0]["event_type"] == "live_start"

        missing = await client.get("/api/v2/sessions/no-such-session/export", headers=headers)
        assert missing.status_code == 404
