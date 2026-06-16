from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import get_current_user
from ..db import get_db
from ..models import User
from ..companion_prompts import pick_starter
from ..schemas import DailyPayload, GreetingResponse, TaskNudgeResponse
from ..services import conversation as conv_svc
from ..services import plan_draft as draft_svc
from ..services import task_nudge as nudge_svc
from ..services import tasks as task_svc
from ..timezone_util import user_local_today

router = APIRouter(prefix="/daily", tags=["daily"])


@router.get("/morning-payload", response_model=DailyPayload)
async def morning_payload(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    name = user.wake_name or user.display_name or "there"
    summary = await task_svc.task_summary(db, user.id, user_local_today(user.timezone))
    return DailyPayload(
        greeting=f"Good morning, {name}.",
        prompt="What should we plan for today? Tell me your tasks and I'll track them.",
        summary=summary,
    )


@router.get("/evening-payload", response_model=DailyPayload)
async def evening_payload(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    name = user.wake_name or user.display_name or "there"
    summary = await task_svc.task_summary(db, user.id, user_local_today(user.timezone))
    if summary.total == 0:
        prompt = "You had a quiet day. Want to set a light plan for tomorrow?"
    else:
        prompt = (
            f"You finished {summary.done} of {summary.total} tasks today. "
            f"Want to carry {summary.open} open items to tomorrow?"
        )
    return DailyPayload(
        greeting=f"Good evening, {name}.",
        prompt=prompt,
        summary=summary,
    )


@router.get("/checkin-payload", response_model=DailyPayload)
async def checkin_payload(user: User = Depends(get_current_user)):
    name = user.wake_name or user.display_name or "there"
    return DailyPayload(
        greeting=f"Hey {name},",
        prompt="Just checking in — how are you feeling?",
    )


_WAKE_HINT = (
    "You can say Hi Pal anytime to wake me — no need to tap the orb."
)


@router.get("/live-greeting", response_model=GreetingResponse)
async def live_greeting(
    in_live: bool = Query(False, description="True when greeting plays after user already went Live"),
    wake_enabled: bool = Query(False, description="User has foreground wake word enabled"),
    show_wake_intro: bool = Query(False, description="Include one-time wake phrase teaching copy"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    name = user.wake_name or user.display_name or "friend"
    wake_hint = _WAKE_HINT if wake_enabled and show_wake_intro else None
    local_day = user_local_today(user.timezone)
    if await conv_svc.has_chatted_today(db, user.id, user.timezone):
        if in_live:
            text = f"I'm listening, {name}."
            if wake_hint:
                text = f"{wake_hint} {text}"
            return GreetingResponse(text=text, wake_word_hint=wake_hint)
        draft = await draft_svc.get_draft(db, user.id)
        if draft and draft.get("proposed_tasks"):
            items = ", ".join(t["title"] for t in draft["proposed_tasks"][:3])
            text = (
                f"Welcome back, {name}. You have a plan waiting: {items}. "
                "Want to add it to Today or talk through something else?"
            )
            if wake_hint and in_live:
                text = f"{wake_hint} {text}"
            return GreetingResponse(text=text, wake_word_hint=wake_hint)
        view = await task_svc.today_view(db, user.id, local_day)
        if view.up_next:
            if in_live:
                text = (
                    f"Hi {name}, your next up is {view.up_next.title}. "
                    "Tell me what changed or what to tackle first."
                )
                if wake_hint and in_live:
                    text = f"{wake_hint} {text}"
                return GreetingResponse(text=text, wake_word_hint=wake_hint)
            text = (
                f"Hi {name}, your next up is {view.up_next.title}. "
                "Go Live when you're ready, or tell me what changed."
            )
            return GreetingResponse(text=text, wake_word_hint=wake_hint)
        return GreetingResponse(
            text=f"Hi {name}, I'm here. What would you like to focus on next?",
            wake_word_hint=wake_hint,
        )

    try:
        tz = ZoneInfo(user.timezone or "UTC")
        hour = datetime.now(tz).hour
    except Exception:
        hour = 12

    if hour < 12:
        text = f"Good morning, {name}. What should we plan for today?"
    elif hour < 17:
        text = f"Hey {name}, how's your day going? Want to adjust your plan?"
    else:
        text = pick_starter(name)
    if wake_hint and in_live:
        text = f"{wake_hint} {text}"
    return GreetingResponse(text=text, wake_word_hint=wake_hint)


@router.get("/task-nudge", response_model=TaskNudgeResponse)
async def task_nudge(
    task_id: int = Query(..., description="Task id to nudge for"),
    minutes: int = Query(12, ge=1, le=60, description="Minutes until due"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    task = await task_svc.get_task(db, user.id, task_id)
    if not task or task.status in ("done", "skipped"):
        return TaskNudgeResponse(
            text="You're all set — nothing coming up for that item.",
            task_id=task_id,
            minutes=minutes,
        )
    text = await nudge_svc.build_nudge_message(db, user, task, minutes)
    return TaskNudgeResponse(text=text, task_id=task_id, minutes=minutes)
