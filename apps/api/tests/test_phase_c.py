from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.timezone_util import user_local_today

_NOW = datetime(2026, 6, 11, 10, 0, tzinfo=timezone.utc)


def test_user_local_today_invalid_tz_falls_back_utc():
    day = user_local_today("Not/A_Real_Zone")
    assert day.year >= 2020


@pytest.mark.asyncio
async def test_live_greeting_in_live_no_push_to_talk():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        reg = await client.post("/api/v2/auth/register", json={"email": "live@example.com"})
        verify = await client.post("/api/v2/auth/verify", json={"token": reg.json()["dev_token"]})
        headers = {"Authorization": f"Bearer {verify.json()['access_token']}"}

        with patch("app.routers.daily.conv_svc.has_chatted_today", new_callable=AsyncMock) as chatted:
            chatted.return_value = True
            with patch("app.routers.daily.task_svc.today_view", new_callable=AsyncMock) as view:
                from app.schemas import TaskResponse, TaskSummary, TodaySections, TodayViewResponse

                view.return_value = TodayViewResponse(
                    summary=TaskSummary(date="2026-06-11", total=1, done=0, open=1, deferred=0, streak_days=0),
                    up_next=TaskResponse(
                        id=1,
                        title="Meeting",
                        notes=None,
                        due_at=None,
                        priority=1,
                        status="planned",
                        source="text",
                        parent_task_id=None,
                        estimated_minutes=None,
                        sort_order=0,
                        category=None,
                        created_at=_NOW,
                        completed_at=None,
                        subtasks=[],
                    ),
                    sections=TodaySections(now=[], upcoming=[], completed=[]),
                )
                r = await client.get("/api/v2/daily/live-greeting?in_live=true", headers=headers)
                assert r.status_code == 200
                text = r.json()["text"].lower()
                assert "tap to talk" not in text
                assert "press to talk" not in text
                assert "hold to talk" not in text
                assert "meeting" in text


@pytest.mark.asyncio
async def test_live_greeting_wake_intro_when_requested():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        reg = await client.post("/api/v2/auth/register", json={"email": "wake@example.com"})
        verify = await client.post("/api/v2/auth/verify", json={"token": reg.json()["dev_token"]})
        headers = {"Authorization": f"Bearer {verify.json()['access_token']}"}

        r = await client.get(
            "/api/v2/daily/live-greeting?in_live=true&wake_enabled=true&show_wake_intro=true",
            headers=headers,
        )
        assert r.status_code == 200
        body = r.json()
        assert "hi pal" in body["text"].lower()
        assert body.get("wake_word_hint") is not None
        assert "on screen" not in body["wake_word_hint"].lower()
        text = body["text"].lower()
        assert "tap to talk" not in text
        assert "press to talk" not in text
        assert "hold to talk" not in text


@pytest.mark.asyncio
async def test_text_turn_includes_today_snapshot():
    with (
        patch("app.routers.turn.llm_chat", new_callable=AsyncMock) as mock_llm,
        patch("app.routers.turn.plan_extractor.extract_plan", new_callable=AsyncMock) as mock_extract,
        patch("app.routers.turn.memory_search", return_value=[]),
        patch("app.routers.turn.memory_add"),
        patch("app.routers.turn.draft_svc.get_draft", new_callable=AsyncMock) as mock_draft,
        patch("app.routers.turn.task_svc.today_view", new_callable=AsyncMock) as mock_view,
    ):
        from app.schemas import TaskResponse, TaskSummary, TodaySections, TodayViewResponse

        mock_llm.return_value = "Sure."
        mock_extract.return_value = {"intent": "other", "proposed_tasks": [], "clarifying_question": None}
        mock_draft.return_value = None
        mock_view.return_value = TodayViewResponse(
            summary=TaskSummary(date="2026-06-11", total=2, done=0, open=2, deferred=0, streak_days=0),
            up_next=TaskResponse(
                id=2,
                title="Swim",
                notes=None,
                due_at=None,
                priority=1,
                status="planned",
                source="text",
                parent_task_id=None,
                estimated_minutes=None,
                sort_order=0,
                category=None,
                created_at=_NOW,
                completed_at=None,
                subtasks=[],
            ),
            sections=TodaySections(now=[], upcoming=[], completed=[]),
        )

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            reg = await client.post("/api/v2/auth/register", json={"email": "snap@example.com"})
            verify = await client.post("/api/v2/auth/verify", json={"token": reg.json()["dev_token"]})
            headers = {"Authorization": f"Bearer {verify.json()['access_token']}"}
            r = await client.post(
                "/api/v2/turn/text",
                headers=headers,
                json={"text": "what's next?"},
            )
            assert r.status_code == 200
            first_user_msg = mock_llm.call_args[0][0][0]["content"]
            assert "Swim" in first_user_msg or "open task" in first_user_msg.lower()
