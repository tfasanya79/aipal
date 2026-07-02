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


def smart_follow_up_prompts(proposed_task: dict) -> list[str] | None:
    """Return up to 2 follow-up questions after task booking."""
    if not proposed_task:
        return None
    
    title = (proposed_task.get("title") or "").lower()
    notes = (proposed_task.get("notes") or "").lower()
    category = proposed_task.get("category", "")
    est_min = proposed_task.get("estimated_minutes")
    
    prompts = []
    
    # Follow-up 1: Focus time for work tasks
    if category in ("work", "personal") or "meeting" in title or "call" in title:
        prompts.append("Should I block focus time before this?")
    
    # Follow-up 2: Travel time for timed events
    if "meeting" in title or "appointment" in notes or est_min and est_min > 30:
        prompts.append("Do you need travel time added?")
    
    # Follow-up 3: Prep/prep materials
    if "meeting" in title or "interview" in notes or "presentation" in notes:
        prompts.append("Anything you need to prep?")
    
    # Return max 2
    return prompts[:2] if prompts else None


def micro_motivation_phrase(
    hour: int, 
    completed_today: int = 0, 
    total_today: int = 0,
    mood_hint: str | None = None,
) -> str:
    """Adaptive motivation phrase based on time of day + progress."""
    
    # Evening reflection
    if hour >= 18:
        if completed_today == total_today and total_today > 0:
            return "🌙 Crushed it today. You earned that rest!"
        elif completed_today > 0:
            return "🌙 Good momentum today. Rest well!"
        return "🌙 You showed up. That matters."
    
    # Mid-day progress
    if hour >= 12 and hour < 18:
        pct = int(100 * completed_today / total_today) if total_today > 0 else 0
        if pct >= 75:
            return f"💪 Almost there! {pct}% done—keep the pace."
        elif pct >= 50:
            return f"⚡ Halfway there ({pct}%). You're on fire!"
        elif pct > 0:
            return f"🎯 {pct}% done. Afternoon push coming up!"
        return "☀️ Afternoon grind starts now. You've got this!"
    
    # Morning
    count_str = f"{total_today} thing" if total_today == 1 else f"{total_today} things"
    if mood_hint == "upbeat":
        return f"🌅 You've got {count_str} today. Let's crush it!"
    if mood_hint == "gentle":
        return f"🌅 Just {count_str} today. Nice and manageable. Ready?"
    return f"🌅 You've got {count_str} today. Let's get going!"

