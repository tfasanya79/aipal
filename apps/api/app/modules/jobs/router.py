from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.jobs import service as job_svc
from app.shared.config import get_settings
from app.shared.db import get_db
from app.shared.models import User

router = APIRouter(prefix="/jobs", tags=["jobs"])
settings = get_settings()


class WeeklyEnqueueResponse(BaseModel):
    queued: int


def _require_internal_secret(
    x_internal_secret: str | None = Header(default=None, alias="X-Internal-Secret"),
) -> None:
    configured = (settings.aipal_internal_secret or "").strip()
    if not configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AIPAL_INTERNAL_SECRET not configured",
        )
    if x_internal_secret != configured:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid internal secret",
        )


@router.post("/enqueue-weekly-summaries", response_model=WeeklyEnqueueResponse)
async def enqueue_weekly_summaries(
    _auth: None = Depends(_require_internal_secret),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(User.id).where(User.weekly_summary_enabled.is_(True))
    )
    user_ids = [str(row[0]) for row in result.all()]

    queued = 0
    for user_id in user_ids:
        await job_svc.enqueue(
            db,
            "weekly_summary_email",
            payload={"user_id": user_id},
        )
        queued += 1

    return WeeklyEnqueueResponse(queued=queued)
