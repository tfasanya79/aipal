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
