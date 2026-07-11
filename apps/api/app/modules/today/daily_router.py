from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.service import get_current_user
from app.shared.db import get_db
from app.shared.models import User
from app.modules.brain.companion_prompts import pick_starter
from app.modules.brain import reflection as reflection_svc
from app.shared.schemas import DailyPayload, GreetingResponse, TaskNudgeResponse
from app.modules.brain import conversation as conv_svc
from app.modules.today import plan_draft as draft_svc
from app.modules.today import task_nudge as nudge_svc
from app.modules.today import tasks as task_svc
from app.shared.timezone_util import user_local_today

router = APIRouter(prefix="/daily", tags=["daily"])


@router.get("/morning-payload", response_model=DailyPayload)
async def morning_payload(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    name = user.wake_name or user.display_name or "there"
    local_day = user_local_today(user.timezone)
    summary = await task_svc.task_summary(db, user.id, local_day, timezone=user.timezone)
    companion_line = await reflection_svc.companion_line_for_day(db, user)
    prompt = "What should we plan for today? Tell me your tasks and I'll track them."
    
    # Check for incomplete tasks from yesterday (if-not-done recovery)
    from datetime import timedelta
    yesterday = local_day - timedelta(days=1)
    yesterday_summary = await task_svc.task_summary(db, user.id, yesterday, timezone=user.timezone)
    
    # Compute motivation phrase
    mood_hint = "upbeat" if summary.total > 0 else None
    motivation = reflection_svc.micro_motivation_phrase(
        hour=datetime.now(ZoneInfo(user.timezone or "UTC")).hour,
        completed_today=summary.done,
        total_today=summary.total,
        mood_hint=mood_hint,
    )
    
    # If there are incomplete tasks from yesterday, mention them
    if yesterday_summary.open > 0:
        open_count = yesterday_summary.open
        task_word = "task" if open_count == 1 else "tasks"
        recovery_msg = f"You have {open_count} {task_word} still open from yesterday. Want to reschedule or finish them?"
        prompt = f"{recovery_msg} {prompt}"
    
    if companion_line:
        prompt = f"{companion_line} {prompt}"
    
    return DailyPayload(
        greeting=f"Good morning, {name}. {motivation}",
        prompt=prompt,
        summary=summary,
        companion_line=companion_line,
    )


@router.get("/evening-payload", response_model=DailyPayload)
async def evening_payload(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    name = user.wake_name or user.display_name or "there"
    local_day = user_local_today(user.timezone)
    summary = await task_svc.task_summary(db, user.id, local_day, timezone=user.timezone)
    companion_line = await reflection_svc.companion_line_for_day(db, user)
    if summary.total == 0:
        prompt = "You had a quiet day. Want to set a light plan for tomorrow?"
    else:
        prompt = (
            f"You finished {summary.done} of {summary.total} tasks today. "
            f"Want to carry {summary.open} open items to tomorrow?"
        )
    if companion_line:
        prompt = f"{companion_line} {prompt}"
    return DailyPayload(
        greeting=f"Good evening, {name}.",
        prompt=prompt,
        summary=summary,
        companion_line=companion_line,
    )


@router.get("/checkin-payload", response_model=DailyPayload)
async def checkin_payload(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Round 8: was a static, context-free prompt every time it fired
    ("Just checking in -- how are you feeling?"). Now mirrors the
    morning/evening payload pattern -- references today's actual task
    progress and the companion line, and varies greeting by time of day --
    so the daily check-in reads like the companion noticed something about
    your day, not a generic ping.
    """
    name = user.wake_name or user.display_name or "there"
    local_day = user_local_today(user.timezone)
    summary = await task_svc.task_summary(db, user.id, local_day, timezone=user.timezone)
    companion_line = await reflection_svc.companion_line_for_day(db, user)

    try:
        tz = ZoneInfo(user.timezone or "UTC")
        hour = datetime.now(tz).hour
    except Exception:
        hour = 12

    if hour < 12:
        greeting = f"Hey {name},"
    elif hour < 17:
        greeting = f"Hi {name},"
    else:
        greeting = f"Evening, {name}."

    if summary.total == 0:
        prompt = "Just checking in — how are you feeling, and is there anything you'd like to plan?"
    elif summary.open == 0:
        prompt = (
            f"You're all caught up — {summary.done} of {summary.total} done today. "
            "How are you feeling?"
        )
    elif summary.done == 0:
        task_word = "task" if summary.open == 1 else "tasks"
        prompt = (
            f"Just checking in — you've got {summary.open} {task_word} still open today. "
            "How's it going?"
        )
    else:
        prompt = (
            f"Just checking in — you've done {summary.done} of {summary.total} so far. "
            "How are you feeling about the rest of today?"
        )

    if companion_line:
        prompt = f"{companion_line} {prompt}"

    return DailyPayload(
        greeting=greeting,
        prompt=prompt,
        summary=summary,
        companion_line=companion_line,
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
        view = await task_svc.today_view(db, user.id, local_day, timezone=user.timezone or "UTC")
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


@router.get("/morning-briefing-spoken", response_model=dict)
async def morning_briefing_spoken(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Generate a spoken morning briefing with summary and motivation.
    
    This endpoint can be called by the mobile app at user's morning_brief_at time.
    """
    from app.modules.voice.tts import synthesize
    
    name = user.wake_name or user.display_name or "there"
    local_day = user_local_today(user.timezone)
    summary = await task_svc.task_summary(db, user.id, local_day, timezone=user.timezone)
    
    # Build briefing text
    try:
        tz = ZoneInfo(user.timezone or "UTC")
        hour = datetime.now(tz).hour
    except Exception:
        hour = 9
    
    motivation = reflection_svc.micro_motivation_phrase(
        hour=hour,
        completed_today=0,
        total_today=summary.total,
        mood_hint="upbeat" if summary.total > 0 else None,
    )
    
    briefing = f"Good morning {name}. {motivation}"
    
    if summary.total > 0:
        task_word = "task" if summary.total == 1 else "tasks"
        briefing += f" You have {summary.total} {task_word} on your plan for today."
    
    # Check for incomplete tasks from yesterday
    from datetime import timedelta
    yesterday = local_day - timedelta(days=1)
    yesterday_summary = await task_svc.task_summary(db, user.id, yesterday, timezone=user.timezone)
    if yesterday_summary.open > 0:
        task_word = "task" if yesterday_summary.open == 1 else "tasks"
        briefing += f" You also have {yesterday_summary.open} {task_word} from yesterday."
    
    # Synthesize to speech
    audio_bytes, audio_mime = await synthesize(briefing, user.tts_voice or "aria")
    
    return {
        "text": briefing,
        "audio_base64": __import__("base64").b64encode(audio_bytes).decode() if audio_bytes else None,
        "audio_mime": audio_mime or "audio/mpeg",
        "summary": {
            "total": summary.total,
            "done": summary.done,
            "open": summary.open,
        }
    }

