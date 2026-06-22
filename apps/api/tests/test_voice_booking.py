"""Voice booking auto-confirm and context tests."""

from datetime import date
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.modules.brain import context_builder, plan_intent
from app.shared.schemas import TaskSummary, TodaySections, TodayViewResponse


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
    snap = TodayViewResponse(
        summary=TaskSummary(date="2026-06-22", total=0, done=0, open=0, deferred=0, streak_days=0),
        sections=TodaySections(now=[], upcoming=[], completed=[]),
    )
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
