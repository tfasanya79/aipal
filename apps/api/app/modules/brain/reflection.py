"""Companion reflection lines for daily payloads."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, time

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.brain.memory import memory_search
from app.shared.models import ConversationTurn, User
from app.shared.timezone_util import user_local_today


async def _last_user_turn_today(db: AsyncSession, user_id: uuid.UUID, timezone: str) -> str | None:
    try:
        from zoneinfo import ZoneInfo

        tz = ZoneInfo(timezone or "UTC")
    except Exception:
        tz = ZoneInfo("UTC")
    local_day = user_local_today(timezone)
    start = datetime.combine(local_day, time.min, tzinfo=tz).astimezone(UTC)

    result = await db.execute(
        select(ConversationTurn)
        .where(
            ConversationTurn.user_id == user_id,
            ConversationTurn.role == "user",
            ConversationTurn.created_at >= start,
        )
        .order_by(ConversationTurn.created_at.desc())
        .limit(1)
    )
    turn = result.scalar_one_or_none()
    if not turn or not turn.content.strip():
        return None
    text = " ".join(turn.content.strip().split())
    if len(text) > 120:
        return text[:117] + "..."
    return text


async def companion_line_for_day(db: AsyncSession, user: User) -> str | None:
    """One sentence of relational continuity for morning/evening payloads."""
    last = await _last_user_turn_today(db, user.id, user.timezone or "UTC")
    if last:
        return f"Earlier you mentioned: {last}"
    memories = memory_search(str(user.id), "preferences and recent context", limit=1)
    if memories:
        mem = memories[0].strip()
        if len(mem) > 100:
            mem = mem[:97] + "..."
        return f"I remember: {mem}"
    return None
