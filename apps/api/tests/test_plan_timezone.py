"""Tests for plan extractor timezone handling and duration clarification."""

from datetime import date
from zoneinfo import ZoneInfo

from app.modules.brain import plan_extractor


def test_localize_due_at_reinterprets_utc_wall_clock():
    tz = ZoneInfo("Europe/Berlin")
    due = plan_extractor._localize_due_at(
        __import__("datetime").datetime.fromisoformat("2026-06-22T14:30:00+00:00"),
        tz,
    )
    assert due.hour == 14
    assert due.minute == 30
    assert str(due.tzinfo) == "Europe/Berlin"


def test_normalize_plan_meeting_without_duration_defers():
    raw = {
        "intent": "plan_day",
        "proposed_tasks": [
            {
                "title": "Team meeting",
                "notes": "team meeting at 2:30pm",
                "due_at": "2026-06-22T14:30:00Z",
                "estimated_minutes": None,
                "priority": 1,
                "category": "work",
            }
        ],
        "clarifying_question": None,
    }
    tz = ZoneInfo("Europe/Berlin")
    result = plan_extractor._normalize_plan(raw, date(2026, 6, 22), tz)
    assert result["proposed_tasks"][0]["estimated_minutes"] is None
    assert result["clarifying_question"] is not None
    assert plan_extractor.should_defer_draft(result)


def test_normalize_plan_simple_reminder_gets_default_duration():
    raw = {
        "intent": "plan_day",
        "proposed_tasks": [
            {
                "title": "Swim",
                "due_at": "2026-06-22T16:00:00+02:00",
                "estimated_minutes": None,
                "priority": 1,
            }
        ],
        "clarifying_question": None,
    }
    tz = ZoneInfo("Europe/Berlin")
    result = plan_extractor._normalize_plan(raw, date(2026, 6, 22), tz)
    assert result["proposed_tasks"][0]["estimated_minutes"] == 30
    assert not plan_extractor.should_defer_draft(result)


def test_collapse_single_booking_keeps_7pm_not_7am():
    tz = ZoneInfo("Europe/Stockholm")
    tasks = [
        {"title": "Meal", "due_at": "2026-06-22T05:00:00+00:00", "estimated_minutes": 60},
        {"title": "Sweden Open", "due_at": "2026-06-22T17:00:00+00:00", "estimated_minutes": 60},
    ]
    msg = "book a 7 pm appointment for one hour"
    fixed = plan_extractor._fix_pm_confusion(tasks, msg, tz)
    collapsed = plan_extractor._collapse_single_booking(fixed, msg, tz)
    assert len(collapsed) == 1
    assert collapsed[0]["title"] == "Sweden Open"
    assert plan_extractor._local_hour_from_due_str(collapsed[0]["due_at"], tz) == 19


def test_format_today_schedule_uses_local_time():
    from datetime import datetime

    from app.modules.brain import context_builder
    from app.shared.schemas import TaskResponse, TaskSummary, TodaySections, TodayViewResponse

    task = TaskResponse(
        id=1,
        title="Meal",
        notes=None,
        due_at=datetime.fromisoformat("2026-06-22T05:00:00+00:00"),
        priority=1,
        status="planned",
        source="plan_confirm",
        estimated_minutes=60,
        sort_order=0,
        category=None,
        created_at=datetime.fromisoformat("2026-06-22T15:47:21+00:00"),
        completed_at=None,
    )
    snap = TodayViewResponse(
        summary=TaskSummary(date="2026-06-22", total=1, done=0, open=1, deferred=0, streak_days=0),
        up_next=task,
        sections=TodaySections(now=[], upcoming=[task], completed=[]),
    )
    block = context_builder.format_today_schedule_block(snap, "Europe/Stockholm")
    assert "7:00 AM" in block
    assert "5:00 AM" not in block
