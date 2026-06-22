import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.models import ConversationTurn

MAX_TURNS = 12


async def append_turn(
    db: AsyncSession,
    user_id: uuid.UUID,
    session_id: str,
    role: str,
    content: str,
) -> None:
    db.add(
        ConversationTurn(
            user_id=user_id,
            session_id=session_id,
            role=role,
            content=content,
        )
    )
    await db.commit()


async def load_history(
    db: AsyncSession,
    user_id: uuid.UUID,
    session_id: str,
    limit: int = MAX_TURNS,
) -> list[dict[str, str]]:
    result = await db.execute(
        select(ConversationTurn)
        .where(ConversationTurn.user_id == user_id, ConversationTurn.session_id == session_id)
        .order_by(ConversationTurn.created_at.desc())
        .limit(limit)
    )
    turns = list(reversed(result.scalars().all()))
    return [{"role": t.role, "content": t.content} for t in turns]


async def has_chatted_today(
    db: AsyncSession,
    user_id: uuid.UUID,
    timezone: str | None = None,
) -> bool:
    from datetime import UTC, datetime, time
    from zoneinfo import ZoneInfo

    try:
        tz = ZoneInfo(timezone or "UTC")
    except Exception:
        tz = ZoneInfo("UTC")
    local_day = datetime.now(tz).date()
    start = datetime.combine(local_day, time.min, tzinfo=tz).astimezone(UTC)
    result = await db.execute(
        select(ConversationTurn.id)
        .where(ConversationTurn.user_id == user_id, ConversationTurn.created_at >= start)
        .limit(1)
    )
    return result.scalar_one_or_none() is not None
