"""Assemble companion context before plan tools and LLM."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.brain.memory import memory_search
from app.modules.brain.mood import tone_hint, tone_hint_instruction
from app.modules.brain import plan_extractor
from app.modules.integrations import calendar_service as cal_svc
from app.shared.models import User
from app.shared.schemas import TodayViewResponse


@dataclass
class CompanionContext:
    mem_block: str
    calendar_block: str
    tone_instruction: str | None
    memories: list[str]


async def build_companion_context(
    db: AsyncSession,
    user: User,
    text: str,
    *,
    today_snap: TodayViewResponse,
) -> CompanionContext:
    memories = memory_search(str(user.id), text, limit=5)
    mem_block = "\n".join(f"- {m}" for m in memories if m) if memories else ""
    events = await cal_svc.get_today_events(db, user.id, timezone=user.timezone or "UTC")
    calendar_block = cal_svc.format_calendar_block(events, timezone=user.timezone or "UTC")
    hint = tone_hint(text)
    return CompanionContext(
        mem_block=mem_block,
        calendar_block=calendar_block,
        tone_instruction=tone_hint_instruction(hint),
        memories=memories,
    )


def _draft_mentioned_in_history(history: list[dict[str, str]]) -> bool:
    for h in history:
        if h["role"] != "assistant":
            continue
        lower = h["content"].lower()
        if "plan draft" in lower or "plan waiting" in lower:
            return True
        if "add" in lower and "today" in lower and ("want" in lower or "shall" in lower):
            return True
    return False


def format_system_context(
    *,
    wake: str,
    about_me: str | None,
    local_day: date,
    today_snap: TodayViewResponse,
    companion: CompanionContext,
    tool_actions: list[str],
    pending: dict | None,
    extracted: dict,
    history: list[dict[str, str]],
    auto_confirmed: bool = False,
) -> str:
    system_ctx = f"User wake name: {wake}. About: {about_me or ''}"
    open_count = today_snap.summary.open
    if today_snap.up_next:
        system_ctx += (
            f"\nToday ({local_day.isoformat()}): {open_count} open task(s). "
            f"Up next: {today_snap.up_next.title}."
        )
    else:
        system_ctx += f"\nToday ({local_day.isoformat()}): {open_count} open task(s). No up-next scheduled."
    if companion.calendar_block:
        system_ctx += f"\n{companion.calendar_block}"
    if companion.mem_block:
        system_ctx += f"\nMemories:\n{companion.mem_block}"
    if companion.tone_instruction:
        system_ctx += f"\n{companion.tone_instruction}"
    if tool_actions:
        system_ctx += f"\nTool results: {'; '.join(tool_actions)}"
    if auto_confirmed or any(a.startswith("Confirmed plan:") for a in tool_actions):
        system_ctx += "\nBooking status: confirmed (tasks are on Today)."
    elif plan_extractor.should_defer_draft(extracted):
        system_ctx += "\nBooking status: needs_duration (ask user; do not save draft yet)."
    elif pending and pending.get("proposed_tasks"):
        system_ctx += "\nBooking status: draft_pending (not on Today until user confirms)."
    if pending and pending.get("proposed_tasks") and not _draft_mentioned_in_history(history):
        tasks_desc = "; ".join(
            f"{t['title']}" + (f" at {t['due_at']}" if t.get("due_at") else "")
            for t in pending["proposed_tasks"]
        )
        system_ctx += (
            f"\nPending plan draft (awaiting user confirm): {tasks_desc}. "
            "Mention once if helpful; do not repeat if user already declined or confirmed."
        )
    if extracted.get("clarifying_question"):
        system_ctx += f"\nClarify: {extracted['clarifying_question']}"
    return system_ctx
