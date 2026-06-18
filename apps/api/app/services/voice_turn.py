"""Live Voice v2 streaming turn pipeline."""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
import uuid
from typing import Any, AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession

from ..llm_provider import llm_chat_stream
from ..memory import memory_add, memory_search
from ..models import User
from ..safety import crisis_reply, is_crisis_likely
from ..services import conversation as conv_svc
from ..services import plan_draft as draft_svc
from ..services import plan_intent
from ..services import tasks as task_svc
from ..services.plan_extractor import needs_plan_extraction
from ..timezone_util import user_local_today
from ..voice_pipeline import strip_plan_json_block
from ..services.turn_shared import EMPTY_PLAN as _EMPTY_PLAN
from ..services.turn_shared import build_system_ctx as _build_system_ctx
from ..services.turn_shared import draft_to_schema as _draft_to_schema

log = logging.getLogger("aipal.voice_turn")

_PLAN_JSON_TAIL = re.compile(r"\{[\s\S]*\"intent\"[\s\S]*\}\s*$")


async def build_turn_context(
    db: AsyncSession,
    user: User,
    text: str,
    session_id: str,
) -> dict[str, Any]:
    """Pre-LLM context: history, tools, draft state, messages list."""
    local_day = user_local_today(user.timezone)
    tz = user.timezone or "UTC"

    history, pending_early = await asyncio.gather(
        conv_svc.load_history(db, user.id, session_id),
        draft_svc.get_draft(db, user.id),
    )

    tool_actions: list[str] = []
    extracted = dict(_EMPTY_PLAN)
    crisis = False
    early_reply: str | None = None

    if pending_early and pending_early.get("proposed_tasks"):
        if plan_intent.is_confirm_intent(text):
            created = await draft_svc.confirm_draft(db, user.id, timezone=tz)
            if created:
                names = ", ".join(c["title"] for c in created)
                early_reply = f"Done — I've added {names} to Today."
                tool_actions = [f"Confirmed plan: {names}"]
            else:
                early_reply = "Got it — those are already on Today."
                tool_actions = ["Confirmed plan: duplicates skipped"]
            await conv_svc.append_turn(db, user.id, session_id, "user", text)
            await conv_svc.append_turn(db, user.id, session_id, "assistant", early_reply)
            return {
                "early_reply": early_reply,
                "crisis": False,
                "tool_actions": tool_actions,
                "plan_draft": None,
                "draft_confirmed": True,
                "messages": None,
            }
        if plan_intent.is_discard_intent(text):
            await draft_svc.clear_draft(db, user.id)
            early_reply = "Okay, I won't add that plan to Today."
            await conv_svc.append_turn(db, user.id, session_id, "user", text)
            await conv_svc.append_turn(db, user.id, session_id, "assistant", early_reply)
            return {
                "early_reply": early_reply,
                "crisis": False,
                "tool_actions": ["Discarded plan draft"],
                "plan_draft": None,
                "draft_confirmed": False,
                "messages": None,
            }

    tool_actions, today_snap = await asyncio.gather(
        task_svc.apply_task_tools_from_text(db, user.id, text, timezone=tz),
        task_svc.today_view(db, user.id, local_day),
    )
    memories = memory_search(str(user.id), text)
    mem_block = "\n".join(f"- {m}" for m in memories) if memories else ""

    if needs_plan_extraction(text):
        extracted_hint = (
            "\n\nIf this message involves planning or task completion, append a fenced JSON block "
            "at the very end (after your spoken reply):\n```json\n"
            '{"intent":"plan_day|check_in|complete_task|other","proposed_tasks":[...],'
            '"clarifying_question":null}\n```'
        )
    else:
        extracted_hint = ""

    if extracted.get("intent") == "complete_task":
        completion_actions = await task_svc.complete_tasks_from_extraction(
            db, user.id, extracted, local_day
        )
        tool_actions.extend(completion_actions)
        if completion_actions:
            today_snap = await task_svc.today_view(db, user.id, local_day)

    pending = await draft_svc.get_draft(db, user.id)
    wake = user.wake_name or user.display_name or "friend"
    system_ctx = _build_system_ctx(
        wake=wake,
        about_me=user.about_me,
        local_day=local_day,
        today_snap=today_snap,
        mem_block=mem_block,
        tool_actions=tool_actions,
        pending=pending,
        extracted=extracted,
        history=history,
    )

    messages = list(history)
    prefix = "[Context" if not messages else "[State"
    user_content = f"{prefix}: {system_ctx}]\n\n{text}{extracted_hint}"
    messages.append({"role": "user", "content": user_content})

    return {
        "early_reply": None,
        "crisis": crisis,
        "tool_actions": tool_actions,
        "plan_draft": None,
        "draft_confirmed": False,
        "messages": messages,
        "text": text,
        "session_id": session_id,
        "user_id": user.id,
    }


def _parse_plan_from_reply(full_text: str) -> tuple[str, dict | None]:
    visible, json_str = strip_plan_json_block(full_text)
    if json_str:
        try:
            return visible.strip(), json.loads(json_str)
        except json.JSONDecodeError:
            pass
    tail = _PLAN_JSON_TAIL.search(full_text)
    if tail:
        try:
            plan = json.loads(tail.group(0))
            visible = full_text[: tail.start()].strip()
            return visible, plan
        except json.JSONDecodeError:
            pass
    return full_text.strip(), None


async def run_voice_turn_stream(
    db: AsyncSession,
    user: User,
    text: str,
    session_id: str,
    *,
    cancel_event: asyncio.Event | None = None,
) -> AsyncIterator[dict[str, Any]]:
    """Yield streaming events: reply_delta, then metadata for turn_complete."""
    t0 = time.monotonic()
    metrics: dict[str, int] = {}
    sid = session_id or str(uuid.uuid4())

    if is_crisis_likely(text):
        reply = crisis_reply()
        yield {"type": "reply_delta", "text": reply}
        yield {
            "type": "turn_meta",
            "reply": reply,
            "crisis": True,
            "tool_actions": [],
            "plan_draft": None,
            "draft_confirmed": False,
            "metrics": {"turn_total_ms": int((time.monotonic() - t0) * 1000)},
        }
        return

    ctx = await build_turn_context(db, user, text, sid)
    if ctx.get("early_reply"):
        reply = ctx["early_reply"]
        yield {"type": "reply_delta", "text": reply}
        yield {
            "type": "turn_meta",
            "reply": reply,
            "crisis": False,
            "tool_actions": ctx.get("tool_actions", []),
            "plan_draft": ctx.get("plan_draft"),
            "draft_confirmed": ctx.get("draft_confirmed", False),
            "metrics": {"turn_total_ms": int((time.monotonic() - t0) * 1000)},
        }
        return

    messages = ctx["messages"]
    llm_t0 = time.monotonic()
    first_token = True
    full_parts: list[str] = []

    async for delta in llm_chat_stream(messages):
        if cancel_event and cancel_event.is_set():
            return
        if first_token:
            metrics["llm_first_token_ms"] = int((time.monotonic() - llm_t0) * 1000)
            first_token = False
        # Strip plan JSON from deltas as it streams (best-effort)
        clean, _ = strip_plan_json_block(delta)
        if clean:
            full_parts.append(clean)
            yield {"type": "reply_delta", "text": clean}

    raw_reply = "".join(full_parts)
    visible_reply, plan_json = _parse_plan_from_reply(raw_reply)

    plan_draft_payload = None
    draft_confirmed = False
    tool_actions = list(ctx.get("tool_actions", []))
    local_day = user_local_today(user.timezone)

    if plan_json and plan_json.get("proposed_tasks"):
        if plan_json.get("intent") == "complete_task":
            completion_actions = await task_svc.complete_tasks_from_extraction(
                db, user.id, plan_json, local_day
            )
            tool_actions.extend(completion_actions)
        elif plan_json.get("intent") != "complete_task":
            await draft_svc.save_draft(db, user.id, plan_json)
            plan_draft_payload = plan_json

    pending = await draft_svc.get_draft(db, user.id)
    await conv_svc.append_turn(db, user.id, sid, "user", text)
    await conv_svc.append_turn(db, user.id, sid, "assistant", visible_reply or raw_reply)
    asyncio.create_task(asyncio.to_thread(memory_add, str(user.id), f"User said: {text}"))
    asyncio.create_task(
        asyncio.to_thread(memory_add, str(user.id), f"AiPal replied: {visible_reply or raw_reply}")
    )

    metrics["turn_total_ms"] = int((time.monotonic() - t0) * 1000)
    yield {
        "type": "turn_meta",
        "reply": visible_reply or raw_reply,
        "crisis": False,
        "tool_actions": tool_actions,
        "plan_draft": _draft_to_schema(plan_draft_payload or pending),
        "draft_confirmed": draft_confirmed,
        "metrics": metrics,
    }
