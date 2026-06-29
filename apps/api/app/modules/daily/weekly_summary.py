"""Weekly activity summary — data aggregation, HTML render, and email send."""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from jinja2 import Environment, FileSystemLoader, select_autoescape
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.config import get_settings
from app.shared.models import Task, User
from app.shared.timezone_util import user_local_today

log = logging.getLogger("aipal.weekly_summary")
settings = get_settings()

_TEMPLATE_DIR = Path(__file__).resolve().parents[2] / "templates"


def _week_bounds(today: date, timezone: str) -> tuple[date, date]:
    """Return (monday, sunday) of the current week in user-local time."""
    monday = today - timedelta(days=today.weekday())
    sunday = monday + timedelta(days=6)
    return monday, sunday


async def build_weekly_summary(db: AsyncSession, user: User) -> dict:
    tz = user.timezone or "UTC"
    today = user_local_today(tz)
    monday, sunday = _week_bounds(today, tz)

    try:
        tzinfo = ZoneInfo(tz)
    except Exception:
        tzinfo = ZoneInfo("UTC")

    week_start_dt = datetime.combine(monday, datetime.min.time(), tzinfo=tzinfo).astimezone(UTC)
    week_end_dt = datetime.combine(sunday + timedelta(days=1), datetime.min.time(), tzinfo=tzinfo).astimezone(UTC)

    # Total and completed tasks this week
    result = await db.execute(
        select(Task.status, func.count())
        .where(
            Task.user_id == user.id,
            Task.parent_task_id.is_(None),
            Task.created_at >= week_start_dt,
            Task.created_at < week_end_dt,
        )
        .group_by(Task.status)
    )
    counts = dict(result.all())
    tasks_completed = counts.get("done", 0)
    tasks_deferred = counts.get("deferred", 0)
    tasks_total = sum(counts.values())

    # Top categories
    cat_result = await db.execute(
        select(Task.category, func.count().label("cnt"))
        .where(
            Task.user_id == user.id,
            Task.parent_task_id.is_(None),
            Task.status == "done",
            Task.completed_at >= week_start_dt,
            Task.completed_at < week_end_dt,
            Task.category.is_not(None),
        )
        .group_by(Task.category)
        .order_by(func.count().desc())
        .limit(3)
    )
    top_categories = [{"category": row[0], "count": row[1]} for row in cat_result.all()]

    # Streak (reuse existing logic)
    from app.modules.today.tasks import _completion_streak

    streak_days = await _completion_streak(db, user.id, tz)

    # LLM companion note
    companion_note = await _generate_companion_note(user, tasks_completed, tasks_deferred, streak_days)

    wake_name = user.wake_name or user.display_name or "friend"

    email_html = _render_html(
        wake_name=wake_name,
        week_start=monday.strftime("%b %d"),
        week_end=sunday.strftime("%b %d, %Y"),
        tasks_completed=tasks_completed,
        tasks_deferred=tasks_deferred,
        streak_days=streak_days,
        top_categories=top_categories,
        companion_note=companion_note,
    )

    return {
        "week_start": monday.isoformat(),
        "week_end": sunday.isoformat(),
        "tasks_completed": tasks_completed,
        "tasks_deferred": tasks_deferred,
        "tasks_total": tasks_total,
        "streak_days": streak_days,
        "top_categories": top_categories,
        "companion_note": companion_note,
        "email_html": email_html,
        "wake_name": wake_name,
    }


async def _generate_companion_note(user: User, done: int, deferred: int, streak: int) -> str:
    try:
        from app.modules.brain.llm_provider import llm_chat

        wake = user.wake_name or user.display_name or "friend"
        prompt = (
            f"Write ONE warm, encouraging sentence (max 25 words) for {wake}'s weekly AiPal summary. "
            f"They completed {done} tasks, deferred {deferred}, and have a {streak}-day streak. "
            "Be specific and positive. No greetings. No emojis."
        )
        return await llm_chat([{"role": "user", "content": prompt}], max_tokens=60)
    except Exception as exc:
        log.warning("companion note generation failed: %s", exc)
        return "Great work this week — keep that momentum going!"


def _render_html(**ctx) -> str:
    try:
        env = Environment(
            loader=FileSystemLoader(str(_TEMPLATE_DIR)),
            autoescape=select_autoescape(["html"]),
        )
        template = env.get_template("weekly_summary.html")
        return template.render(**ctx)
    except Exception as exc:
        log.warning("HTML render failed: %s", exc)
        return f"<p>Weekly summary: {ctx.get('tasks_completed', 0)} tasks completed.</p>"


async def send_weekly_summary_email(db: AsyncSession, user: User) -> bool:
    """Send weekly summary email via Resend. Returns True if sent."""
    if not settings.resend_api_key:
        log.warning("RESEND_API_KEY not configured — cannot send email")
        return False
    summary = await build_weekly_summary(db, user)
    subject = f"Your AiPal week: {summary['tasks_completed']} tasks done 🎯"
    html = summary["email_html"]
    try:
        import resend

        resend.api_key = settings.resend_api_key
        resend.Emails.send({
            "from": "AiPal <weekly@aipal.io>",
            "to": [user.email],
            "subject": subject,
            "html": html,
        })
        log.info("Weekly summary sent to %s", user.email)
        return True
    except Exception as exc:
        log.error("Failed to send weekly summary to %s: %s", user.email, exc)
        return False
