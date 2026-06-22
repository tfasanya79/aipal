"""Read-only calendar cache helpers for brain context."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, time

from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.models import CalendarEventCache
from app.shared.timezone_util import user_local_today


async def get_today_events(
    db: AsyncSession,
    user_id: uuid.UUID,
    *,
    timezone: str = "UTC",
) -> list[CalendarEventCache]:
    local_day = user_local_today(timezone)
    try:
        tz = ZoneInfo(timezone or "UTC")
    except Exception:
        tz = ZoneInfo("UTC")
    start = datetime.combine(local_day, time.min, tzinfo=tz).astimezone(UTC)
    end = datetime.combine(local_day, time.max, tzinfo=tz).astimezone(UTC)

    result = await db.execute(
        select(CalendarEventCache)
        .where(
            CalendarEventCache.user_id == user_id,
            CalendarEventCache.starts_at >= start,
            CalendarEventCache.starts_at <= end,
        )
        .order_by(CalendarEventCache.starts_at)
    )
    return list(result.scalars().all())


def format_calendar_block(events: list[CalendarEventCache], timezone: str = "UTC") -> str:
    if not events:
        return ""
    try:
        tz = ZoneInfo(timezone or "UTC")
    except Exception:
        tz = ZoneInfo("UTC")
    lines: list[str] = []
    for ev in events[:8]:
        local = ev.starts_at.astimezone(tz)
        lines.append(f"- {ev.title} at {local.strftime('%H:%M')}")
    return "Calendar today:\n" + "\n".join(lines)
