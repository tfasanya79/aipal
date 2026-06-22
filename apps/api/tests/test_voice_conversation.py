from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app

_NOW = datetime(2026, 6, 11, 10, 0, tzinfo=timezone.utc)


@pytest.mark.asyncio
async def test_text_turn_follow_up_includes_prior_turn_in_messages():
    with (
        patch("app.routers.turn.llm_chat", new_callable=AsyncMock) as mock_llm,
        patch("app.routers.turn.plan_extractor.needs_plan_extraction", return_value=False),
        patch("app.modules.brain.context_builder.memory_search", return_value=[]),
        patch("app.routers.turn.remember_turn"),
        patch("app.routers.turn.draft_svc.get_draft", new_callable=AsyncMock) as mock_draft,
        patch("app.routers.turn.task_svc.today_view", new_callable=AsyncMock) as mock_view,
        patch("app.routers.turn.task_svc.apply_task_tools_from_text", new_callable=AsyncMock) as mock_tools,
        patch("app.routers.turn.conv_svc.load_history", new_callable=AsyncMock) as mock_history,
        patch("app.routers.turn.conv_svc.append_turn", new_callable=AsyncMock),
    ):
        from app.schemas import TaskSummary, TodaySections, TodayViewResponse

        mock_tools.return_value = []
        mock_draft.return_value = None
        mock_view.return_value = TodayViewResponse(
            summary=TaskSummary(date="2026-06-11", total=0, done=0, open=0, deferred=0, streak_days=0),
            up_next=None,
            sections=TodaySections(now=[], upcoming=[], completed=[]),
        )
        mock_history.return_value = [
            {"role": "user", "content": "meeting at 4"},
            {"role": "assistant", "content": "Got it — meeting at 4."},
        ]
        mock_llm.return_value = "Sure, adding that."

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            reg = await client.post("/api/v2/auth/register", json={"email": "follow@example.com"})
            verify = await client.post("/api/v2/auth/verify", json={"token": reg.json()["dev_token"]})
            headers = {"Authorization": f"Bearer {verify.json()['access_token']}"}
            sid = "voice-session-abc"
            r = await client.post(
                "/api/v2/turn/text",
                headers=headers,
                json={"text": "yes add it", "session_id": sid},
            )
            assert r.status_code == 200
            messages = mock_llm.call_args[0][0]
            assert messages[0]["content"] == "meeting at 4"
            assert "[State:" in messages[-1]["content"]


@pytest.mark.asyncio
async def test_audio_turn_accepts_session_id():
    with (
        patch("app.routers.turn.transcribe_path", return_value="hello there"),
        patch("app.routers.turn._reply_for_text", new_callable=AsyncMock) as mock_reply,
        patch("app.routers.turn.synthesize", new_callable=AsyncMock) as mock_tts,
    ):
        mock_reply.return_value = ("Hi!", False, [], "sess-123", None)
        mock_tts.return_value = (b"audio", "audio/mpeg")

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            reg = await client.post("/api/v2/auth/register", json={"email": "audio@example.com"})
            verify = await client.post("/api/v2/auth/verify", json={"token": reg.json()["dev_token"]})
            headers = {"Authorization": f"Bearer {verify.json()['access_token']}"}
            r = await client.post(
                "/api/v2/turn/audio",
                headers=headers,
                files={"file": ("turn.m4a", b"fake", "audio/mp4")},
                data={"session_id": "sess-123"},
            )
            assert r.status_code == 200
            body = r.json()
            assert body["session_id"] == "sess-123"
            mock_reply.assert_awaited_once()
            assert mock_reply.await_args.args[3] == "sess-123"


@pytest.mark.asyncio
async def test_complete_task_intent_marks_task_done():
    with (
        patch("app.routers.turn.llm_chat", new_callable=AsyncMock) as mock_llm,
        patch("app.routers.turn.plan_extractor.needs_plan_extraction", return_value=True),
        patch("app.routers.turn.plan_extractor.extract_plan", new_callable=AsyncMock) as mock_extract,
        patch("app.modules.brain.context_builder.memory_search", return_value=[]),
        patch("app.routers.turn.remember_turn"),
        patch("app.routers.turn.draft_svc.get_draft", new_callable=AsyncMock) as mock_draft,
        patch("app.routers.turn.draft_svc.save_draft", new_callable=AsyncMock),
        patch("app.routers.turn.conv_svc.load_history", new_callable=AsyncMock, return_value=[]),
        patch("app.routers.turn.conv_svc.append_turn", new_callable=AsyncMock),
        patch("app.routers.turn.task_svc.apply_task_tools_from_text", new_callable=AsyncMock) as mock_tools,
        patch("app.routers.turn.task_svc.complete_tasks_from_extraction", new_callable=AsyncMock) as mock_complete,
        patch("app.routers.turn.task_svc.today_view", new_callable=AsyncMock) as mock_view,
    ):
        from app.schemas import TaskSummary, TodaySections, TodayViewResponse

        mock_tools.return_value = []
        mock_draft.return_value = None
        mock_extract.return_value = {
            "intent": "complete_task",
            "proposed_tasks": [{"title": "Swim"}],
            "clarifying_question": None,
        }
        mock_complete.return_value = ["Completed: Swim"]
        mock_view.return_value = TodayViewResponse(
            summary=TaskSummary(date="2026-06-11", total=1, done=1, open=0, deferred=0, streak_days=0),
            up_next=None,
            sections=TodaySections(now=[], upcoming=[], completed=[]),
        )
        mock_llm.return_value = "Nice work on swimming!"

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            reg = await client.post("/api/v2/auth/register", json={"email": "done@example.com"})
            verify = await client.post("/api/v2/auth/verify", json={"token": reg.json()["dev_token"]})
            headers = {"Authorization": f"Bearer {verify.json()['access_token']}"}
            r = await client.post(
                "/api/v2/turn/text",
                headers=headers,
                json={"text": "I finished swimming"},
            )
            assert r.status_code == 200
            mock_complete.assert_awaited_once()
            first_user_msg = mock_llm.call_args[0][0][0]["content"]
            assert "Completed: Swim" in first_user_msg or "Tool results" in first_user_msg


@pytest.mark.asyncio
async def test_live_greeting_in_live_short_resume_after_chat():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        reg = await client.post("/api/v2/auth/register", json={"email": "resume@example.com"})
        verify = await client.post("/api/v2/auth/verify", json={"token": reg.json()["dev_token"]})
        headers = {"Authorization": f"Bearer {verify.json()['access_token']}"}

        with patch("app.routers.daily.conv_svc.has_chatted_today", new_callable=AsyncMock) as chatted:
            chatted.return_value = True
            r = await client.get("/api/v2/daily/live-greeting?in_live=true", headers=headers)
            assert r.status_code == 200
            text = r.json()["text"].lower()
            assert "listening" in text
            assert "plan waiting" not in text
            assert "next up" not in text


@pytest.mark.asyncio
async def test_needs_plan_extraction_skips_casual_chat():
    from app.services.plan_extractor import needs_plan_extraction

    assert not needs_plan_extraction("how are you feeling today?")
    assert needs_plan_extraction("remind me to swim at 6pm")
    assert needs_plan_extraction("I finished swimming")
