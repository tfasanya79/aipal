"""Voice booking auto-confirm and context tests."""

from datetime import date, datetime
from unittest.mock import AsyncMock, patch

from zoneinfo import ZoneInfo

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.modules.brain import context_builder, plan_extractor, plan_intent
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


def test_is_complete_booking_request_false_wrong_day_for_tomorrow():
    tz = "Europe/Stockholm"
    extracted = {
        "clarifying_question": None,
        "proposed_tasks": [
            {"title": "Team meeting", "due_at": "2026-06-22T08:00:00+02:00", "estimated_minutes": 60}
        ],
    }
    assert not plan_intent.is_complete_booking_request(
        "book a team meeting tomorrow morning at 8am for an hour",
        extracted,
        local_day=date(2026, 6, 22),
        timezone=tz,
    )


def test_is_complete_booking_request_true_for_tomorrow():
    extracted = {
        "clarifying_question": None,
        "proposed_tasks": [
            {"title": "Team meeting", "due_at": "2026-06-23T08:00:00+02:00", "estimated_minutes": 60}
        ],
    }
    assert plan_intent.is_complete_booking_request(
        "book a team meeting tomorrow morning at 8am for an hour",
        extracted,
        local_day=date(2026, 6, 22),
        timezone="Europe/Stockholm",
    )


def test_apply_relative_day_shifts_tomorrow():
    tz = ZoneInfo("Europe/Stockholm")
    tasks = [{"title": "Team meeting", "due_at": "2026-06-22T08:00:00+02:00"}]
    shifted = plan_extractor._apply_relative_day(
        tasks,
        "book meeting tomorrow morning at 8",
        date(2026, 6, 22),
        tz,
    )
    assert shifted[0]["due_at"].startswith("2026-06-23T08:00")


def test_regex_booking_fallback_tomorrow_morning():
    tz = ZoneInfo("Europe/Stockholm")
    out = plan_extractor._regex_booking_fallback(
        "book a team meeting tomorrow morning at 8am for an hour",
        date(2026, 6, 22),
        tz,
    )
    assert out is not None
    assert out["proposed_tasks"][0]["title"] == "Team meeting"
    assert "2026-06-23" in out["proposed_tasks"][0]["due_at"]
    assert out["proposed_tasks"][0]["estimated_minutes"] == 60


def test_is_complete_booking_request_false_absurd_early_hour():
    extracted = {
        "clarifying_question": None,
        "proposed_tasks": [
            {"title": "Breakfast date", "due_at": "2026-06-23T04:30:00+02:00", "estimated_minutes": 30}
        ],
    }
    assert not plan_intent.is_complete_booking_request(
        "book a breakfast date for me tomorrow morning at 8:30 am",
        extracted,
        local_day=date(2026, 6, 22),
        timezone="Europe/Stockholm",
    )


def test_confirm_intent_rejects_noisy_yes():
    assert not plan_intent.is_confirm_intent("Yes, I did so much. I do.")
    assert not plan_intent.is_confirm_intent(
        "Yes, I did subscribe. My evening is going fine. Thank you"
    )
    assert plan_intent.is_confirm_intent("yes")
    assert plan_intent.is_confirm_intent("yes add it to today")


def test_nonsense_transcript():
    from app.modules.voice.router import _is_nonsense_transcript

    assert _is_nonsense_transcript("I'm going to put it on the back of the head.")
    assert _is_nonsense_transcript(
        "I'm going to put it in the air. I'm going to put it in the air."
    )
    assert not _is_nonsense_transcript("book a team meeting tomorrow at 8am")


def test_low_signal_single_word():
    from app.modules.voice.router import _is_low_signal_transcript

    assert _is_low_signal_transcript("You")
    assert _is_low_signal_transcript("Ok")
    assert not _is_low_signal_transcript("book a team meeting tomorrow at 8am")


def test_media_ambient_transcript():
    from app.modules.voice.router import _is_media_ambient_transcript

    assert _is_media_ambient_transcript(
        "walking through the logo and the final touches on the car build"
    )
    assert _is_media_ambient_transcript("my video just came out this morning")
    assert not _is_media_ambient_transcript("book a team meeting tomorrow at 8am")


def test_edit_request_not_booking():
    assert not plan_intent.is_edit_request(
        "Book appointment for tomorrow morning 8.30 a.m."
    )
    assert not plan_intent.is_edit_request(
        "I did not ask you to change any task, I asked you to book a breakfast"
    )
    assert plan_intent.is_edit_request("move Sweden Open to 8pm")


def test_confirmed_reply_uses_tomorrow_label():
    from app.modules.voice.router import _confirmed_reply

    tz = ZoneInfo("Europe/Stockholm")
    created = [
        {
            "title": "Team meeting",
            "due_at": datetime(2026, 6, 23, 8, 0, tzinfo=tz),
            "estimated_minutes": 60,
        }
    ]
    reply, tool = _confirmed_reply(created, local_day=date(2026, 6, 22), tz=tz)
    assert "Tomorrow" in reply
    assert "Team meeting" in reply
    assert tool.startswith("Confirmed plan:")


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
async def test_audio_turn_discards_ambient_hallucination_stt():
    with patch("app.routers.turn.transcribe_path", return_value="It's okay to feel scared, Tim."):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            reg = await client.post("/api/v2/auth/register", json={"email": "ambient@example.com"})
            verify = await client.post("/api/v2/auth/verify", json={"token": reg.json()["dev_token"]})
            headers = {"Authorization": f"Bearer {verify.json()['access_token']}"}
            r = await client.post(
                "/api/v2/turn/audio",
                headers=headers,
                files={"file": ("turn.m4a", b"\x00" * 256, "audio/mp4")},
            )
        assert r.status_code == 200
        body = r.json()
        assert body.get("skip_tts") is True
        assert not body.get("audio_base64")


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
