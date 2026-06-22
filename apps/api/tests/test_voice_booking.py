"""Voice booking auto-confirm and context tests."""

from datetime import date, datetime
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.modules.brain import context_builder, plan_intent
from app.shared.schemas import TaskSummary, TodaySections, TodayViewResponse


def _empty_snap() -> TodayViewResponse:
    return TodayViewResponse(
        summary=TaskSummary(date="2026-06-22", total=0, done=0, open=0, deferred=0, streak_days=0),
        sections=TodaySections(now=[], upcoming=[], completed=[]),
    )


def test_assistant_offered_to_add_detects_offer():
    history = [
        {"role": "user", "content": "was my 6pm appointment added?"},
        {
            "role": "assistant",
            "content": "I can add a 6pm appointment to Today — just say yes.",
        },
    ]
    assert plan_intent.assistant_offered_to_add(history)


def test_assistant_offered_to_add_false_without_offer():
    history = [{"role": "assistant", "content": "Your next task is Team meeting."}]
    assert not plan_intent.assistant_offered_to_add(history)


def test_reply_claims_success_detects_false_done():
    assert plan_intent.reply_claims_success("Done, I've added Dinner to Today.")
    assert not plan_intent.reply_claims_success("I don't see a 6pm appointment yet.")


def test_ensure_recovery_duration_defaults_missing():
    extracted = {
        "proposed_tasks": [{"title": "Dinner", "due_at": "2026-06-22T18:00:00+00:00"}],
        "clarifying_question": "How long?",
    }
    out = plan_intent.ensure_recovery_duration(extracted)
    assert out["proposed_tasks"][0]["estimated_minutes"] == 60
    assert out["clarifying_question"] is None


def test_is_complete_booking_request_true():
    extracted = {
        "clarifying_question": None,
        "proposed_tasks": [
            {"title": "Appointment", "due_at": "2026-06-22T18:00:00+02:00", "estimated_minutes": 30}
        ],
    }
    assert plan_intent.is_complete_booking_request("book a 6pm appointment for 30 minutes", extracted)


def test_is_complete_booking_request_false_without_duration():
    extracted = {
        "clarifying_question": "How long is your meeting?",
        "proposed_tasks": [
            {"title": "Meeting", "due_at": "2026-06-22T15:00:00+02:00", "estimated_minutes": None}
        ],
    }
    assert not plan_intent.is_complete_booking_request("schedule a meeting at 3pm", extracted)


def test_context_booking_status_draft_pending():
    snap = _empty_snap()
    ctx = context_builder.format_system_context(
        wake="Tim",
        about_me=None,
        local_day=date(2026, 6, 22),
        today_snap=snap,
        companion=context_builder.CompanionContext("", "", None, []),
        tool_actions=[],
        pending={"proposed_tasks": [{"title": "Appointment", "due_at": "18:00"}]},
        extracted={"clarifying_question": None, "proposed_tasks": []},
        history=[],
    )
    assert "Booking status: draft_pending" in ctx


def test_context_includes_local_time():
    snap = _empty_snap()
    local_now = datetime(2026, 6, 22, 16, 40)
    ctx = context_builder.format_system_context(
        wake="Tim",
        about_me=None,
        local_day=date(2026, 6, 22),
        local_now=local_now,
        today_snap=snap,
        companion=context_builder.CompanionContext("", "", None, []),
        tool_actions=[],
        pending=None,
        extracted={"clarifying_question": None, "proposed_tasks": []},
        history=[],
    )
    assert "Current local time: 2026-06-22 16:40 (afternoon)" in ctx
    assert "never say \"good morning\" in the afternoon or evening" in ctx


@pytest.mark.asyncio
async def test_confirm_with_no_draft_recovers_and_creates_task():
    extracted = {
        "intent": "plan_day",
        "clarifying_question": None,
        "proposed_tasks": [
            {
                "title": "Appointment",
                "due_at": "2026-06-22T18:00:00+00:00",
                "estimated_minutes": None,
                "priority": 1,
            }
        ],
    }
    history = [
        {"role": "user", "content": "was my 6pm appointment added?"},
        {
            "role": "assistant",
            "content": "I can add a 6pm appointment to Today — just say yes.",
        },
    ]
    today_snap = _empty_snap()
    confirm_mock = AsyncMock(
        return_value=[
            {
                "id": 1,
                "title": "Appointment",
                "due_at": datetime(2026, 6, 22, 18, 0),
                "estimated_minutes": 60,
            }
        ]
    )

    with (
        patch("app.routers.turn.llm_chat", new_callable=AsyncMock) as mock_llm,
        patch("app.routers.turn.plan_extractor.extract_plan", new_callable=AsyncMock, return_value=extracted),
        patch("app.routers.turn.plan_extractor.needs_plan_extraction", return_value=False),
        patch("app.routers.turn.draft_svc.save_draft", new_callable=AsyncMock) as mock_save,
        patch("app.routers.turn.draft_svc.confirm_draft", confirm_mock),
        patch("app.routers.turn.conv_svc.load_history", new_callable=AsyncMock, return_value=history),
        patch("app.routers.turn.conv_svc.append_turn", new_callable=AsyncMock),
        patch("app.routers.turn.draft_svc.get_draft", new_callable=AsyncMock, return_value=None),
        patch("app.routers.turn.task_svc.apply_task_tools_from_text", new_callable=AsyncMock, return_value=[]),
        patch("app.routers.turn.task_svc.today_view", new_callable=AsyncMock, return_value=today_snap),
        patch("app.routers.turn.ctx_svc.build_companion_context", new_callable=AsyncMock),
        patch("app.routers.turn.remember_turn"),
    ):
        mock_llm.return_value = "should not be called"
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            reg = await client.post("/api/v2/auth/register", json={"email": "recover@example.com"})
            verify = await client.post("/api/v2/auth/verify", json={"token": reg.json()["dev_token"]})
            headers = {"Authorization": f"Bearer {verify.json()['access_token']}"}
            r = await client.post(
                "/api/v2/turn/text",
                headers=headers,
                json={"text": "yes"},
            )
        assert r.status_code == 200
        body = r.json()
        mock_save.assert_awaited()
        confirm_mock.assert_awaited()
        mock_llm.assert_not_awaited()
        assert any(a.startswith("Confirmed plan:") for a in body["tool_actions"])
        assert "added" in body["reply"].lower()


@pytest.mark.asyncio
async def test_confirm_with_no_offer_does_not_lie():
    today_snap = _empty_snap()

    with (
        patch("app.routers.turn.llm_chat", new_callable=AsyncMock, return_value="Okay, what would you like to add?"),
        patch("app.routers.turn.plan_extractor.needs_plan_extraction", return_value=False),
        patch("app.routers.turn.draft_svc.confirm_draft", new_callable=AsyncMock) as confirm_mock,
        patch("app.routers.turn.conv_svc.load_history", new_callable=AsyncMock, return_value=[]),
        patch("app.routers.turn.conv_svc.append_turn", new_callable=AsyncMock),
        patch("app.routers.turn.draft_svc.get_draft", new_callable=AsyncMock, return_value=None),
        patch("app.routers.turn.task_svc.apply_task_tools_from_text", new_callable=AsyncMock, return_value=[]),
        patch("app.routers.turn.task_svc.today_view", new_callable=AsyncMock, return_value=today_snap),
        patch("app.routers.turn.ctx_svc.build_companion_context", new_callable=AsyncMock),
        patch("app.routers.turn.remember_turn"),
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            reg = await client.post("/api/v2/auth/register", json={"email": "bareyes@example.com"})
            verify = await client.post("/api/v2/auth/verify", json={"token": reg.json()["dev_token"]})
            headers = {"Authorization": f"Bearer {verify.json()['access_token']}"}
            r = await client.post(
                "/api/v2/turn/text",
                headers=headers,
                json={"text": "yes"},
            )
        assert r.status_code == 200
        body = r.json()
        confirm_mock.assert_not_awaited()
        reply_lower = body["reply"].lower()
        assert "added" not in reply_lower
        assert "done" not in reply_lower


@pytest.mark.asyncio
async def test_post_llm_guard_rewrites_false_claim():
    extracted = {
        "intent": "plan_day",
        "clarifying_question": None,
        "proposed_tasks": [
            {
                "title": "Dinner",
                "due_at": "2026-06-22T18:00:00+00:00",
                "estimated_minutes": 60,
                "priority": 1,
            }
        ],
    }
    history = [
        {"role": "user", "content": "add dinner at 6"},
        {"role": "assistant", "content": "Want me to add Dinner at 6pm to Today? Say yes."},
    ]
    today_snap = _empty_snap()

    with (
        patch(
            "app.routers.turn.llm_chat",
            new_callable=AsyncMock,
            return_value="Done, I've added Dinner to Today.",
        ),
        patch("app.routers.turn.plan_extractor.extract_plan", new_callable=AsyncMock, return_value=extracted),
        patch("app.routers.turn.plan_extractor.needs_plan_extraction", return_value=False),
        patch("app.routers.turn.draft_svc.save_draft", new_callable=AsyncMock),
        patch(
            "app.routers.turn.draft_svc.confirm_draft",
            new_callable=AsyncMock,
            return_value=[
                {
                    "id": 2,
                    "title": "Dinner",
                    "due_at": datetime(2026, 6, 22, 18, 0),
                    "estimated_minutes": 60,
                }
            ],
        ),
        patch("app.routers.turn.conv_svc.load_history", new_callable=AsyncMock, return_value=history),
        patch("app.routers.turn.conv_svc.append_turn", new_callable=AsyncMock),
        patch("app.routers.turn.draft_svc.get_draft", new_callable=AsyncMock, return_value=None),
        patch("app.routers.turn.task_svc.apply_task_tools_from_text", new_callable=AsyncMock, return_value=[]),
        patch("app.routers.turn.task_svc.today_view", new_callable=AsyncMock, return_value=today_snap),
        patch("app.routers.turn.ctx_svc.build_companion_context", new_callable=AsyncMock),
        patch("app.routers.turn.remember_turn"),
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            reg = await client.post("/api/v2/auth/register", json={"email": "guard@example.com"})
            verify = await client.post("/api/v2/auth/verify", json={"token": reg.json()["dev_token"]})
            headers = {"Authorization": f"Bearer {verify.json()['access_token']}"}
            r = await client.post(
                "/api/v2/turn/text",
                headers=headers,
                json={"text": "was dinner added to today?"},
            )
        assert r.status_code == 200
        body = r.json()
        assert any(a.startswith("Confirmed plan:") for a in body["tool_actions"])
        assert "Dinner" in body["reply"]


@pytest.mark.asyncio
async def test_audio_turn_auto_confirms_complete_booking():
    extracted = {
        "intent": "plan_day",
        "clarifying_question": None,
        "proposed_tasks": [
            {
                "title": "Appointment",
                "due_at": "2026-06-22T18:00:00+00:00",
                "estimated_minutes": 30,
                "priority": 1,
            }
        ],
    }
    today_snap = TodayViewResponse(
        summary=TaskSummary(date="2026-06-22", total=1, done=0, open=1, deferred=0, streak_days=0),
        sections=TodaySections(now=[], upcoming=[], completed=[]),
    )

    with (
        patch("app.routers.turn.transcribe_path", return_value="book a 6pm appointment for 30 minutes"),
        patch("app.routers.turn.synthesize", new_callable=AsyncMock, return_value=(b"audio", "audio/wav")),
        patch("app.routers.turn.plan_extractor.extract_plan", new_callable=AsyncMock, return_value=extracted),
        patch("app.routers.turn.plan_extractor.needs_plan_extraction", return_value=True),
        patch("app.routers.turn.draft_svc.save_draft", new_callable=AsyncMock),
        patch(
            "app.routers.turn.draft_svc.confirm_draft",
            new_callable=AsyncMock,
            return_value=[{"id": 1, "title": "Appointment", "due_at": None}],
        ),
        patch("app.routers.turn.conv_svc.load_history", new_callable=AsyncMock, return_value=[]),
        patch("app.routers.turn.conv_svc.append_turn", new_callable=AsyncMock),
        patch("app.routers.turn.draft_svc.get_draft", new_callable=AsyncMock, return_value=None),
        patch("app.routers.turn.task_svc.apply_task_tools_from_text", new_callable=AsyncMock, return_value=[]),
        patch("app.routers.turn.task_svc.today_view", new_callable=AsyncMock, return_value=today_snap),
        patch("app.routers.turn.ctx_svc.build_companion_context", new_callable=AsyncMock),
        patch("app.routers.turn.sess_svc.safe_record_event", new_callable=AsyncMock),
        patch("app.routers.turn.remember_turn"),
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            reg = await client.post("/api/v2/auth/register", json={"email": "autobook@example.com"})
            verify = await client.post("/api/v2/auth/verify", json={"token": reg.json()["dev_token"]})
            headers = {"Authorization": f"Bearer {verify.json()['access_token']}"}
            r = await client.post(
                "/api/v2/turn/audio",
                headers=headers,
                files={"file": ("turn.m4a", b"fake-audio", "audio/mp4")},
            )
        assert r.status_code == 200
        body = r.json()
        assert body["draft_confirmed"] is True
        assert body["plan_draft"] is None
        assert "added" in body["reply"].lower()
