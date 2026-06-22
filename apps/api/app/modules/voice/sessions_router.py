from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.service import get_current_user
from app.shared.db import get_db
from app.shared.models import User
from app.shared.schemas import (
    RecentSessionSummary,
    SessionEventsBatchRequest,
    SessionEventsBatchResponse,
    SessionExportResponse,
)
from app.modules.voice import session_events as sess_svc

router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.post("/events", response_model=SessionEventsBatchResponse)
async def post_session_events(
    body: SessionEventsBatchRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not body.events:
        return SessionEventsBatchResponse(recorded=0, session_id=body.session_id)
    payload = [
        {"event_type": e.event_type, "payload": e.payload, "phase_tag": e.phase_tag}
        for e in body.events
    ]
    count = await sess_svc.record_events_batch(
        db,
        user.id,
        body.session_id,
        payload,
        phase_tag=body.phase_tag,
    )
    return SessionEventsBatchResponse(recorded=count, session_id=body.session_id)


@router.get("/recent", response_model=list[RecentSessionSummary])
async def recent_sessions(
    limit: int = Query(5, ge=1, le=20),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    rows = await sess_svc.list_recent_sessions(db, user.id, limit=limit)
    return [RecentSessionSummary(**row) for row in rows]


@router.get("/{session_id}/export", response_model=SessionExportResponse)
async def export_session(
    session_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    data = await sess_svc.export_session(db, user.id, session_id)
    if data is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return SessionExportResponse(**data)
