import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import ConversationTurn, SessionEvent

RETENTION_DAYS = 30


async def record_event(
    db: AsyncSession,
    user_id: uuid.UUID,
    session_id: str,
    event_type: str,
    *,
    phase_tag: str | None = None,
    payload: dict | None = None,
) -> None:
    db.add(
        SessionEvent(
            user_id=user_id,
            session_id=session_id,
            event_type=event_type,
            phase_tag=phase_tag,
            payload=payload or {},
        )
    )
    await db.commit()


async def record_events_batch(
    db: AsyncSession,
    user_id: uuid.UUID,
    session_id: str,
    events: list[dict],
    *,
    phase_tag: str | None = None,
) -> int:
    for item in events:
        db.add(
            SessionEvent(
                user_id=user_id,
                session_id=session_id,
                event_type=item["event_type"],
                phase_tag=phase_tag or item.get("phase_tag"),
                payload=item.get("payload") or {},
            )
        )
    await db.commit()
    return len(events)


async def cleanup_old_events(db: AsyncSession, days: int = RETENTION_DAYS) -> int:
    cutoff = datetime.now(UTC) - timedelta(days=days)
    result = await db.execute(delete(SessionEvent).where(SessionEvent.created_at < cutoff))
    await db.commit()
    return result.rowcount or 0


async def list_recent_sessions(
    db: AsyncSession,
    user_id: uuid.UUID,
    limit: int = 5,
) -> list[dict]:
    subq = (
        select(
            SessionEvent.session_id,
            func.max(SessionEvent.created_at).label("last_at"),
            func.count(SessionEvent.id).label("event_count"),
            func.max(SessionEvent.phase_tag).label("phase_tag"),
        )
        .where(SessionEvent.user_id == user_id)
        .group_by(SessionEvent.session_id)
        .order_by(func.max(SessionEvent.created_at).desc())
        .limit(limit)
    )
    result = await db.execute(subq)
    rows = result.all()
    return [
        {
            "session_id": row.session_id,
            "last_event_at": row.last_at.isoformat() if row.last_at else None,
            "event_count": row.event_count,
            "phase_tag": row.phase_tag,
        }
        for row in rows
    ]


async def export_session(
    db: AsyncSession,
    user_id: uuid.UUID,
    session_id: str,
) -> dict | None:
    ev_result = await db.execute(
        select(SessionEvent)
        .where(SessionEvent.user_id == user_id, SessionEvent.session_id == session_id)
        .order_by(SessionEvent.created_at.asc())
    )
    events = ev_result.scalars().all()
    turn_result = await db.execute(
        select(ConversationTurn)
        .where(ConversationTurn.user_id == user_id, ConversationTurn.session_id == session_id)
        .order_by(ConversationTurn.created_at.asc())
    )
    turns = turn_result.scalars().all()
    if not events and not turns:
        return None
    phase_tags = [e.phase_tag for e in events if e.phase_tag]
    return {
        "session_id": session_id,
        "phase_tag": phase_tags[-1] if phase_tags else None,
        "events": [
            {
                "event_type": e.event_type,
                "phase_tag": e.phase_tag,
                "payload": e.payload,
                "created_at": e.created_at.isoformat(),
            }
            for e in events
        ],
        "turns": [
            {
                "role": t.role,
                "content": t.content,
                "created_at": t.created_at.isoformat(),
            }
            for t in turns
        ],
    }
