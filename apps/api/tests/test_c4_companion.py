"""Phase C4 companion depth tests."""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.modules.brain.mood import tone_hint, tone_hint_instruction
from app.modules.integrations import calendar_service as cal_svc
from app.shared.models import CalendarEventCache


@pytest.mark.asyncio
async def test_tone_hint_gentle_for_negative():
    assert tone_hint("I feel awful and exhausted today") == "gentle"
    assert "gentle" in (tone_hint_instruction("gentle") or "")


@pytest.mark.asyncio
async def test_tone_hint_neutral_for_mixed():
    assert tone_hint("hello there") in ("neutral", None)


@pytest.mark.asyncio
async def test_calendar_format_block():
    ev = CalendarEventCache(
        user_id=uuid.uuid4(),
        external_id="e1",
        title="Standup",
        starts_at=datetime(2026, 6, 20, 10, 0, tzinfo=UTC),
        ends_at=datetime(2026, 6, 20, 10, 30, tzinfo=UTC),
    )
    block = cal_svc.format_calendar_block([ev], timezone="UTC")
    assert "Standup" in block
    assert "Calendar today" in block


@pytest.mark.asyncio
async def test_evening_payload_includes_companion_line():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        reg = await client.post("/api/v2/auth/register", json={"email": "c4@example.com"})
        token = reg.json()["dev_token"]
        verify = await client.post("/api/v2/auth/verify", json={"token": token})
        access = verify.json()["access_token"]
        headers = {"Authorization": f"Bearer {access}"}

        with patch(
            "app.modules.today.daily_router.reflection_svc.companion_line_for_day",
            new_callable=AsyncMock,
            return_value="Earlier you mentioned: swim",
        ):
            r = await client.get("/api/v2/daily/evening-payload", headers=headers)
        assert r.status_code == 200
        body = r.json()
        assert body.get("companion_line") == "Earlier you mentioned: swim"
        assert "swim" in body["prompt"]


@pytest.mark.asyncio
async def test_text_turn_includes_calendar_in_context():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        reg = await client.post("/api/v2/auth/register", json={"email": "calctx@example.com"})
        token = reg.json()["dev_token"]
        verify = await client.post("/api/v2/auth/verify", json={"token": token})
        access = verify.json()["access_token"]
        user_id = verify.json()["user_id"]
        headers = {"Authorization": f"Bearer {access}"}

        from app.db import async_session

        async with async_session() as db:
            db.add(
                CalendarEventCache(
                    user_id=uuid.UUID(user_id),
                    external_id="meet-1",
                    title="Team sync",
                    starts_at=datetime.now(UTC),
                    ends_at=None,
                )
            )
            await db.commit()

        captured: list[str] = []

        async def fake_llm(messages):
            for m in messages:
                if m["role"] == "user" and "Team sync" in m["content"]:
                    captured.append(m["content"])
            return "You have Team sync on your calendar."

        with (
            patch("app.modules.voice.router.llm_chat", side_effect=fake_llm),
            patch("app.modules.brain.context_builder.memory_search", return_value=[]),
            patch("app.modules.voice.router.remember_turn"),
        ):
            r = await client.post(
                "/api/v2/turn/text",
                headers=headers,
                json={"text": "what is on my calendar today?"},
            )
        assert r.status_code == 200
        assert captured
        assert "Team sync" in captured[0]
