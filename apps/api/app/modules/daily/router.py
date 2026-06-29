from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.service import get_current_user
from app.modules.daily import weekly_summary as ws_svc
from app.shared.db import get_db
from app.shared.models import User

router = APIRouter(prefix="/daily", tags=["daily"])


class WeeklySummaryResponse(BaseModel):
    week_start: str
    week_end: str
    tasks_completed: int
    tasks_deferred: int
    tasks_total: int
    streak_days: int
    top_categories: list[dict]
    companion_note: str
    email_html: str


class WeeklySendResponse(BaseModel):
    sent: bool
    email: str


@router.get("/weekly-summary", response_model=WeeklySummaryResponse)
async def get_weekly_summary(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    data = await ws_svc.build_weekly_summary(db, user)
    return WeeklySummaryResponse(**data)


@router.post("/weekly-summary/send", response_model=WeeklySendResponse)
async def send_weekly_summary(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    sent = await ws_svc.send_weekly_summary_email(db, user)
    return WeeklySendResponse(sent=sent, email=user.email)
