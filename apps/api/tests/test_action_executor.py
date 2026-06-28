"""C5 action executor and edit/reschedule tests."""

from datetime import date, datetime
from unittest.mock import AsyncMock, patch
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.modules.brain import action_executor, plan_extractor, plan_intent, task_resolver
from app.modules.brain import context_builder
from app.shared.schemas import TaskResponse, TaskSummary, TodaySections, TodayViewResponse


def _snap_with_task(task_id: int, title: str, due_at: datetime) -> TodayViewResponse:
    task = TaskResponse(
        id=task_id,
        title=title,
        notes=None,
        due_at=due_at,
        priority=1,
        status="planned",
        source="plan_confirm",
        estimated_minutes=60,
        sort_order=0,
        category=None,
        created_at=datetime(2026, 6, 22, 15, 0, tzinfo=ZoneInfo("UTC")),
        completed_at=None,
    )
    return TodayViewResponse(
        summary=TaskSummary(date="2026-06-22", total=1, done=0, open=1, deferred=0, streak_days=0),
        up_next=task,
        sections=TodaySections(now=[], upcoming=[task], completed=[]),
    )


def test_schedule_block_includes_task_id():
    due = datetime(2026, 6, 22, 17, 0, tzinfo=ZoneInfo("UTC"))
    snap = _snap_with_task(99, "Sweden Open", due)
    block = context_builder.format_today_schedule_block(snap, "Europe/Stockholm")
    assert "id=99" in block
    assert "7:00 PM" in block


def test_regex_edit_fallback_parses_move_to_8pm():
    tz = ZoneInfo("Europe/Stockholm")
    result = plan_extractor._regex_edit_fallback(
        "move Sweden Open to 8pm",
        date(2026, 6, 22),
        tz,
    )
    assert result is not None
    assert result["intent"] == "edit_task"
    assert result["edits"][0]["match_title"] == "Sweden Open"
    hour = plan_extractor._local_hour_from_due_str(result["edits"][0]["new_due_at"], tz)
    assert hour == 20


def test_reply_claims_mutation_detects_update_lie():
    assert plan_intent.reply_claims_mutation("Sweden Open is now set for 8:00 PM tonight.")
    assert plan_intent.reply_claims_mutation("Done — I've moved Sweden Open to 8:00 PM.")


def test_is_clear_edit_title_without_pm():
    due = datetime(2026, 6, 22, 17, 0, tzinfo=ZoneInfo("UTC"))
    snap = _snap_with_task(99, "Sweden Open", due)
    resolved = [{"match_title": "Sweden Open", "new_due_at": "2026-06-22T20:00:00+02:00", "task_id": 99}]
    assert plan_intent.is_clear_edit(
        {"intent": "edit_task"},
        resolved,
        "move Sweden Open to 8",
        snap,
    )
    assert not plan_intent.is_clear_edit(
        {"intent": "edit_task"},
        resolved,
        "change it to 8",
        snap,
    )


@pytest.mark.asyncio
async def test_text_turn_regex_first_instant_edit():
    due = datetime(2026, 6, 22, 17, 0, tzinfo=ZoneInfo("UTC"))
    today_snap = _snap_with_task(99, "Sweden Open", due)
    new_due = datetime(2026, 6, 22, 20, 0, tzinfo=ZoneInfo("UTC"))
    mock_task = type("T", (), {"id": 99, "title": "Sweden Open", "due_at": new_due})()

    with (
        patch("app.routers.turn.llm_chat", new_callable=AsyncMock) as mock_llm,
        patch("app.routers.turn.plan_extractor.extract_plan", new_callable=AsyncMock) as mock_extract,
        patch("app.routers.turn.draft_svc.get_draft", new_callable=AsyncMock, return_value=None),
        patch("app.routers.turn.conv_svc.load_history", new_callable=AsyncMock, return_value=[]),
        patch("app.routers.turn.conv_svc.append_turn", new_callable=AsyncMock),
        patch("app.routers.turn.task_svc.apply_task_tools_from_text", new_callable=AsyncMock, return_value=[]),
        patch("app.routers.turn.task_svc.today_view", new_callable=AsyncMock, return_value=today_snap),
        patch("app.routers.turn.task_svc.update_task", new_callable=AsyncMock, return_value=mock_task),
        patch("app.routers.turn.ctx_svc.build_companion_context", new_callable=AsyncMock),
        patch("app.routers.turn.remember_turn"),
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            reg = await client.post("/api/v2/auth/register", json={"email": "regexedit@example.com"})
            verify = await client.post("/api/v2/auth/verify", json={"token": reg.json()["dev_token"]})
            headers = {"Authorization": f"Bearer {verify.json()['access_token']}"}
            r = await client.post(
                "/api/v2/turn/text",
                headers=headers,
                json={"text": "move Sweden Open to 8pm"},
            )
        assert r.status_code == 200
        body = r.json()
        mock_llm.assert_not_awaited()
        mock_extract.assert_not_awaited()
        assert any(a.startswith("Updated task:") for a in body["tool_actions"])
        assert "say yes" not in body["reply"].lower()


@pytest.mark.asyncio
async def test_audio_turn_empty_stt_skips_tts():
    with patch("app.routers.turn.transcribe_path", return_value=""):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            reg = await client.post("/api/v2/auth/register", json={"email": "emptystt@example.com"})
            verify = await client.post("/api/v2/auth/verify", json={"token": reg.json()["dev_token"]})
            headers = {"Authorization": f"Bearer {verify.json()['access_token']}"}
            r = await client.post(
                "/api/v2/turn/audio",
                headers=headers,
                files={"file": ("turn.m4a", b"\x00" * 128, "audio/mp4")},
            )
        assert r.status_code == 200
        body = r.json()
        assert body.get("skip_tts") is True
        assert not body.get("audio_base64")


@pytest.mark.asyncio
async def test_reschedule_sweden_open_instant():
    user_id = uuid4()
    due = datetime(2026, 6, 22, 17, 0, tzinfo=ZoneInfo("UTC"))
    snap = _snap_with_task(99, "Sweden Open", due)
    extracted = {
        "intent": "edit_task",
        "edits": [
            {
                "match_title": "Sweden Open",
                "new_due_at": "2026-06-22T20:00:00+02:00",
                "new_estimated_minutes": None,
            }
        ],
    }
    new_due = datetime(2026, 6, 22, 18, 0, tzinfo=ZoneInfo("UTC"))
    mock_task = type("T", (), {"id": 99, "title": "Sweden Open", "due_at": new_due})()

    with patch("app.modules.brain.action_executor.task_svc.update_task", new_callable=AsyncMock) as mock_update:
        mock_update.return_value = mock_task
        result = await action_executor.try_handle_edit_extraction(
            AsyncMock(),
            user_id,
            "move Sweden Open to 8pm",
            extracted,
            snap,
            timezone="Europe/Stockholm",
        )
    assert result is not None
    assert result.handled
    assert result.tool_actions
    assert result.tool_actions[0].startswith("Updated task:")
    mock_update.assert_awaited()


@pytest.mark.asyncio
async def test_reschedule_ambiguous_offers_confirm():
    user_id = uuid4()
    due = datetime(2026, 6, 22, 17, 0, tzinfo=ZoneInfo("UTC"))
    snap = _snap_with_task(99, "Sweden Open", due)
    extracted = {
        "intent": "edit_task",
        "edits": [{"match_title": "Sweden Open", "new_due_at": "2026-06-22T20:00:00+02:00"}],
    }

    with (
        patch("app.modules.brain.action_executor.draft_svc.save_draft", new_callable=AsyncMock) as mock_save,
        patch("app.modules.brain.action_executor.task_svc.update_task", new_callable=AsyncMock) as mock_update,
    ):
        mock_update.return_value = type(
            "T", (), {"id": 99, "title": "Sweden Open", "due_at": due}
        )()
        result = await action_executor.try_handle_edit_extraction(
            AsyncMock(),
            user_id,
            "change it to 8",
            extracted,
            snap,
            timezone="Europe/Stockholm",
        )
    assert result is not None
    assert result.handled
    assert not result.tool_actions
    assert "say yes" in (result.reply or "").lower()
    mock_save.assert_awaited()


@pytest.mark.asyncio
async def test_confirm_yes_after_update_offer_applies_edit():
    due = datetime(2026, 6, 22, 17, 0, tzinfo=ZoneInfo("UTC"))
    history = [
        {"role": "user", "content": "change Sweden Open to 8pm"},
        {
            "role": "assistant",
            "content": "I can move Sweden Open to 8:00 PM — say yes and I'll update it.",
        },
    ]
    extracted = {
        "intent": "edit_task",
        "edits": [{"match_title": "Sweden Open", "new_due_at": "2026-06-22T20:00:00+02:00"}],
    }
    today_snap = _snap_with_task(99, "Sweden Open", due)
    new_due = datetime(2026, 6, 22, 20, 0, tzinfo=ZoneInfo("UTC"))
    mock_task = type("T", (), {"id": 99, "title": "Sweden Open", "due_at": new_due})()

    with (
        patch("app.routers.turn.llm_chat", new_callable=AsyncMock) as mock_llm,
        patch(
            "app.routers.turn.plan_extractor.extract_plan",
            new_callable=AsyncMock,
            return_value=extracted,
        ),
        patch("app.routers.turn.plan_extractor.needs_plan_extraction", return_value=False),
        patch("app.routers.turn.draft_svc.get_draft", new_callable=AsyncMock, return_value=None),
        patch("app.routers.turn.draft_svc.clear_draft", new_callable=AsyncMock),
        patch("app.routers.turn.conv_svc.load_history", new_callable=AsyncMock, return_value=history),
        patch("app.routers.turn.conv_svc.append_turn", new_callable=AsyncMock),
        patch("app.routers.turn.task_svc.apply_task_tools_from_text", new_callable=AsyncMock, return_value=[]),
        patch("app.routers.turn.task_svc.today_view", new_callable=AsyncMock, return_value=today_snap),
        patch("app.routers.turn.task_svc.update_task", new_callable=AsyncMock, return_value=mock_task),
        patch("app.routers.turn.ctx_svc.build_companion_context", new_callable=AsyncMock),
        patch("app.routers.turn.remember_turn"),
    ):
        mock_llm.return_value = "should not run"
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            reg = await client.post("/api/v2/auth/register", json={"email": "edityes@example.com"})
            verify = await client.post("/api/v2/auth/verify", json={"token": reg.json()["dev_token"]})
            headers = {"Authorization": f"Bearer {verify.json()['access_token']}"}
            r = await client.post("/api/v2/turn/text", headers=headers, json={"text": "yes"})
        assert r.status_code == 200
        body = r.json()
        mock_llm.assert_not_awaited()
        assert any(a.startswith("Updated task:") for a in body["tool_actions"])
        assert "8" in body["reply"]


@pytest.mark.asyncio
async def test_post_llm_guard_blocks_false_update_claim():
    due = datetime(2026, 6, 22, 17, 0, tzinfo=ZoneInfo("UTC"))
    history = [
        {"role": "user", "content": "is Sweden Open still at 7?"},
    ]
    today_snap = _snap_with_task(99, "Sweden Open", due)

    with (
        patch(
            "app.routers.turn.llm_chat",
            new_callable=AsyncMock,
            return_value="Wonderful — Sweden Open is now set for 8:00 PM tonight.",
        ),
        patch("app.routers.turn.plan_extractor.needs_plan_extraction", return_value=False),
        patch("app.routers.turn.draft_svc.get_draft", new_callable=AsyncMock, return_value=None),
        patch("app.routers.turn.conv_svc.load_history", new_callable=AsyncMock, return_value=history),
        patch("app.routers.turn.conv_svc.append_turn", new_callable=AsyncMock),
        patch("app.routers.turn.task_svc.apply_task_tools_from_text", new_callable=AsyncMock, return_value=[]),
        patch("app.routers.turn.task_svc.today_view", new_callable=AsyncMock, return_value=today_snap),
        patch("app.routers.turn.ctx_svc.build_companion_context", new_callable=AsyncMock),
        patch("app.routers.turn.remember_turn"),
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            reg = await client.post("/api/v2/auth/register", json={"email": "guardup@example.com"})
            verify = await client.post("/api/v2/auth/verify", json={"token": reg.json()["dev_token"]})
            headers = {"Authorization": f"Bearer {verify.json()['access_token']}"}
            r = await client.post(
                "/api/v2/turn/text",
                headers=headers,
                json={"text": "what time is Sweden Open?"},
            )
        body = r.json()
        reply_lower = body["reply"].lower()
        assert "now set" not in reply_lower or "haven't changed" in reply_lower
