"""Grounded mutations: create/update/complete/delete before LLM claims success."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.brain import plan_extractor, task_resolver
from app.modules.brain import plan_intent
from app.modules.today import plan_draft as draft_svc
from app.modules.today import tasks as task_svc
from app.shared.schemas import TodayViewResponse


@dataclass
class ActionResult:
    handled: bool
    reply: str | None = None
    tool_actions: list[str] | None = None
    refresh_today: bool = False


_DELETE_SIGNAL = re.compile(
    r"\b(remove|delete|cancel|drop|clear)\b.+\b(from today|off today|task|appointment)\b|"
    r"\b(cancel|remove)\s+(my|the)\s+",
    re.IGNORECASE,
)


def _parse_due(raw: str | None, tz: ZoneInfo) -> datetime | None:
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        return plan_extractor._localize_due_at(dt, tz)
    except ValueError:
        return None


def _updated_reply(title: str, time_label: str) -> tuple[str, str]:
    tool_msg = f"Updated task: {title} → {time_label}"
    reply = f"Done — I've moved {title} to {time_label} on Today."
    return reply, tool_msg


async def apply_edits(
    db: AsyncSession,
    user_id: UUID,
    edits: list[dict],
    today_snap: TodayViewResponse,
    *,
    timezone: str,
    user_text: str = "",
) -> tuple[list[str], str | None]:
    """Apply edit_task payload; return (tool_actions, reply)."""
    try:
        tz = ZoneInfo(timezone or "UTC")
    except Exception:
        tz = ZoneInfo("UTC")

    tool_actions: list[str] = []
    last_reply: str | None = None
    for edit in edits:
        if not isinstance(edit, dict):
            continue
        resolved = task_resolver.resolve_task(
            match_title=edit.get("match_title"),
            task_id=edit.get("task_id"),
            user_text=user_text,
            today_snap=today_snap,
        )
        if not resolved:
            continue
        new_due = _parse_due(edit.get("new_due_at"), tz)
        new_mins = edit.get("new_estimated_minutes")
        new_title = edit.get("new_title")
        updated = await task_svc.update_task(
            db,
            user_id,
            resolved.task_id,
            title=str(new_title).strip() if new_title else None,
            due_at=new_due,
            estimated_minutes=int(new_mins) if new_mins is not None else None,
        )
        if not updated:
            continue
        time_label = task_resolver.format_due_local(updated.due_at, timezone)
        last_reply, tool_msg = _updated_reply(updated.title, time_label)
        tool_actions.append(tool_msg)

    return tool_actions, last_reply


def _is_edit_draft(payload: dict | None) -> bool:
    return bool(payload and payload.get("intent") == "edit_task" and payload.get("edits"))


async def confirm_edit_draft(
    db: AsyncSession,
    user_id: UUID,
    payload: dict,
    today_snap: TodayViewResponse,
    *,
    timezone: str,
) -> ActionResult:
    tool_actions, reply = await apply_edits(
        db, user_id, payload.get("edits") or [], today_snap, timezone=timezone
    )
    await draft_svc.clear_draft(db, user_id)
    if not tool_actions:
        return ActionResult(
            handled=True,
            reply="I couldn't find that task to update. Check Today and try again.",
            tool_actions=[],
            refresh_today=False,
        )
    return ActionResult(
        handled=True,
        reply=reply or "Done — I've updated your task on Today.",
        tool_actions=tool_actions,
        refresh_today=True,
    )


def _offer_edit_reply(edit: dict, resolved: task_resolver.ResolvedTask, timezone: str) -> str:
    new_due = edit.get("new_due_at")
    try:
        tz = ZoneInfo(timezone or "UTC")
    except Exception:
        tz = ZoneInfo("UTC")
    dt = _parse_due(new_due, tz)
    time_label = task_resolver.format_due_local(dt, timezone) if dt else "the new time"
    return (
        f"I can move {resolved.title} to {time_label} on Today — "
        f"say yes and I'll update it."
    )


async def try_handle_edit_extraction(
    db: AsyncSession,
    user_id: UUID,
    text: str,
    extracted: dict,
    today_snap: TodayViewResponse,
    *,
    timezone: str,
) -> ActionResult | None:
    if extracted.get("intent") != "edit_task":
        return None
    lower = (text or "").lower()
    if plan_intent._BOOKING_SIGNAL.search(lower) and re.search(r"\b(book|schedule)\b", lower):
        if not plan_intent.is_edit_request(text):
            return None
    edits = extracted.get("edits") or []
    if not edits:
        return None

    try:
        tz = ZoneInfo(timezone or "UTC")
    except Exception:
        tz = ZoneInfo("UTC")

    resolved_edits: list[dict] = []
    ambiguous = False
    for edit in edits:
        if not isinstance(edit, dict):
            continue
        resolved = task_resolver.resolve_task(
            match_title=edit.get("match_title"),
            task_id=edit.get("task_id"),
            user_text=text,
            today_snap=today_snap,
        )
        if not resolved:
            ambiguous = True
            continue
        item = dict(edit)
        item["task_id"] = resolved.task_id
        item["match_title"] = resolved.title
        if not item.get("new_due_at"):
            ambiguous = True
        resolved_edits.append(item)

    if not resolved_edits:
        return ActionResult(
            handled=True,
            reply="Which task should I change? Tell me the name and the new time.",
            tool_actions=[],
        )

    payload = {"intent": "edit_task", "edits": resolved_edits, "clarifying_question": None}

    if ambiguous or len(resolved_edits) > 1:
        await draft_svc.save_draft(db, user_id, payload)
        first = resolved_edits[0]
        resolved = task_resolver.resolve_task(
            match_title=first.get("match_title"),
            task_id=first.get("task_id"),
            user_text=text,
            today_snap=today_snap,
        )
        if resolved:
            return ActionResult(
                handled=True,
                reply=_offer_edit_reply(first, resolved, timezone),
                tool_actions=[],
            )
        return ActionResult(
            handled=True,
            reply="Which task should I move, and to what time?",
            tool_actions=[],
        )

    if plan_intent.is_clear_edit(extracted, resolved_edits, text, today_snap):
        tool_actions, reply = await apply_edits(
            db, user_id, resolved_edits, today_snap, timezone=timezone, user_text=text
        )
        if tool_actions:
            return ActionResult(
                handled=True,
                reply=reply,
                tool_actions=tool_actions,
                refresh_today=True,
            )
        return ActionResult(
            handled=True,
            reply="I couldn't find that task to update. Check Today and try again.",
            tool_actions=[],
        )

    await draft_svc.save_draft(db, user_id, payload)
    resolved = task_resolver.resolve_task(
        match_title=resolved_edits[0].get("match_title"),
        task_id=resolved_edits[0].get("task_id"),
        user_text=text,
        today_snap=today_snap,
    )
    if resolved:
        return ActionResult(
            handled=True,
            reply=_offer_edit_reply(resolved_edits[0], resolved, timezone),
            tool_actions=[],
        )
    return None


async def try_handle_delete(
    db: AsyncSession,
    user_id: UUID,
    text: str,
    today_snap: TodayViewResponse,
) -> ActionResult | None:
    if not _DELETE_SIGNAL.search(text):
        return None
    resolved = task_resolver.resolve_task(
        match_title=None,
        task_id=None,
        user_text=text,
        today_snap=today_snap,
    )
    if not resolved:
        return ActionResult(
            handled=True,
            reply="Which task should I remove from Today?",
            tool_actions=[],
        )
    updated = await task_svc.update_task(db, user_id, resolved.task_id, status="skipped")
    if not updated:
        return ActionResult(
            handled=True,
            reply="I couldn't remove that task.",
            tool_actions=[],
        )
    tool_msg = f"Deleted task: {updated.title}"
    return ActionResult(
        handled=True,
        reply=f"Done — I've removed {updated.title} from Today.",
        tool_actions=[tool_msg],
        refresh_today=True,
    )


async def try_handle_delete_extraction(
    db: AsyncSession,
    user_id: UUID,
    extracted: dict,
    today_snap: TodayViewResponse,
) -> ActionResult | None:
    """Handle delete_task intent from plan extraction."""
    if extracted.get("intent") != "delete_task":
        return None
    
    delete_targets = extracted.get("delete_targets") or []
    if not delete_targets:
        return ActionResult(
            handled=True,
            reply="Which task should I remove?",
            tool_actions=[],
        )
    
    tool_actions: list[str] = []
    last_reply: str | None = None
    
    for target in delete_targets:
        if not isinstance(target, dict):
            continue
        resolved = task_resolver.resolve_task(
            match_title=target.get("match_title"),
            task_id=target.get("task_id"),
            user_text="",
            today_snap=today_snap,
        )
        if not resolved:
            continue
        updated = await task_svc.update_task(db, user_id, resolved.task_id, status="skipped")
        if not updated:
            continue
        tool_msg = f"Deleted task: {updated.title}"
        last_reply = f"Done — I've removed {updated.title} from Today."
        tool_actions.append(tool_msg)
    
    if tool_actions:
        return ActionResult(
            handled=True,
            reply=last_reply,
            tool_actions=tool_actions,
            refresh_today=True,
        )
    
    return ActionResult(
        handled=True,
        reply="I couldn't find that task to remove.",
        tool_actions=[],
    )


async def try_handle_mark_urgent_extraction(
    db: AsyncSession,
    user_id: UUID,
    extracted: dict,
    today_snap: TodayViewResponse,
) -> ActionResult | None:
    """Handle mark_urgent intent from plan extraction."""
    if extracted.get("intent") != "mark_urgent":
        return None
    
    mark_urgent_targets = extracted.get("mark_urgent_targets") or []
    if not mark_urgent_targets:
        return ActionResult(
            handled=True,
            reply="Which task should I mark as urgent?",
            tool_actions=[],
        )
    
    tool_actions: list[str] = []
    last_reply: str | None = None
    
    for target in mark_urgent_targets:
        if not isinstance(target, dict):
            continue
        resolved = task_resolver.resolve_task(
            match_title=target.get("match_title"),
            task_id=target.get("task_id"),
            user_text="",
            today_snap=today_snap,
        )
        if not resolved:
            continue
        new_priority = target.get("new_priority", 2)
        updated = await task_svc.update_task(
            db, user_id, resolved.task_id, priority=int(new_priority)
        )
        if not updated:
            continue
        tool_msg = f"Marked urgent: {updated.title}"
        last_reply = f"Done — I've marked {updated.title} as urgent."
        tool_actions.append(tool_msg)
    
    if tool_actions:
        return ActionResult(
            handled=True,
            reply=last_reply,
            tool_actions=tool_actions,
            refresh_today=True,
        )
    
    return ActionResult(
        handled=True,
        reply="I couldn't find that task to mark urgent.",
        tool_actions=[],
    )


async def recover_edit_from_history(
    db: AsyncSession,
    user_id: UUID,
    history: list[dict[str, str]],
    today_snap: TodayViewResponse,
    *,
    timezone: str,
    wake_name: str,
    history_summary: str,
    local_day,
) -> ActionResult | None:
    if not plan_intent.assistant_offered_to_update(history):
        return None
    recovery_text = plan_intent.recovery_context_from_history(history)
    if not recovery_text.strip():
        return None
    extracted = await plan_extractor.extract_plan(
        recovery_text,
        wake_name=wake_name,
        timezone=timezone,
        history_summary=history_summary,
        today=local_day,
    )
    if extracted.get("intent") != "edit_task":
        return None
    edits = extracted.get("edits") or []
    if not edits:
        return None
    tool_actions, reply = await apply_edits(
        db, user_id, edits, today_snap, timezone=timezone, user_text=recovery_text
    )
    if not tool_actions:
        return None
    await draft_svc.clear_draft(db, user_id)
    return ActionResult(
        handled=True,
        reply=reply,
        tool_actions=tool_actions,
        refresh_today=True,
    )
