import asyncio
import base64
import json
import logging
import os
import re
import tempfile
import time
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, File, Form, UploadFile
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.service import get_current_user
from app.shared.agent_debug import agent_debug
from app.shared.db import get_db
from app.modules.brain.llm_provider import llm_chat, llm_stream
from app.modules.brain.memory import remember_turn
from app.shared.models import User
from app.modules.brain.safety import crisis_reply, is_crisis_likely
from app.shared.schemas import (
    AudioTurnResponse,
    MusicCommand,
    PlanDraftResponse,
    ProposedTask,
    TextTurnRequest,
    TextTurnResponse,
    TtsRequest,
    TtsResponse,
    VoiceCatalogueItem,
)
from app.modules.brain import conversation as conv_svc
from app.modules.brain import context_builder as ctx_svc
from app.modules.brain import reflection as reflection_svc
from app.modules.today import plan_draft as draft_svc
from app.modules.brain import plan_extractor
from app.modules.brain import plan_intent
from app.modules.brain import action_executor as act_svc
from app.modules.voice import session_events as sess_svc
from app.modules.today import tasks as task_svc
from app.shared.timezone_util import user_local_today
from app.modules.voice.stt import transcribe_path
from app.modules.voice.tts import synthesize, get_voice_id, VOICE_CATALOGUE

router = APIRouter(tags=["turn"])
log = logging.getLogger("aipal.turn")

_EMPTY_PLAN = {"intent": "other", "proposed_tasks": [], "edits": [], "clarifying_question": None}
_HONEST_NO_PENDING = (
    "I don't have a saved item to add yet. Tell me the time and I'll put it on Today."
)
_HONEST_NOT_ADDED = (
    "I haven't added anything yet — tell me the time and duration and I'll put it on Today."
)
_HONEST_NOT_CHANGED = (
    "I haven't changed anything on Today yet — tell me which task and the new time."
)

_LOW_SIGNAL = re.compile(r"^[\W\d\s]{0,12}$|^(uh+|um+|hmm+|thanks?|ok+|yeah+)\.?$", re.IGNORECASE)
_AMBIENT_HALLUCINATION = re.compile(
    r"\b("
    r"it'?s okay|there'?s nothing to apologize|feel scared|don'?t worry|"
    r"i understand how you feel|you don'?t need to apologize|i'?m here for you|"
    r"nothing to apologize|no judgment|calm space|sit quietly|no pressure at all|"
    r"your feelings are completely valid|you'?re not alone"
    r")\b",
    re.IGNORECASE,
)
_MEDIA_AMBIENT = re.compile(
    r"\b("
    r"car build|video launch|walking through the logo|final touches on the|"
    r"creative momentum|channel that video|dial in the details|my video just came out|"
    r"logo and the final touches|"
    r"subscribe and hit the bell|like and subscribe|smash that like|"
    r"stay tuned|back with another|welcome back to|"
    r"previously on|coming up next|after the break|"
    r"new episode|season finale|breaking news|"
    r"brought to you by|tonight on|this week on"
    r")\b",
    re.IGNORECASE,
)
_ASSISTANT_LIKE_STT = re.compile(
    r"^(it'?s okay|there'?s nothing|i'?m sorry|don'?t apologize|you'?re doing great|"
    r"i'?m here,?|would you like to sit)",
    re.IGNORECASE,
)
_THERAPY_REPLY = re.compile(
    r"\b(feel scared|nothing to apologize|calm space|no judgment|sit quietly|"
    r"your feelings are valid|you'?re not alone)\b",
    re.IGNORECASE,
)


def _is_low_signal_transcript(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return True
    if len(t) < 3:
        return True
    words = t.split()
    if len(words) == 1 and len(t) <= 6:
        return True
    if _LOW_SIGNAL.match(t):
        return True
    if not re.search(r"[a-zA-Z]{2,}", t):
        return True
    return False


def _is_media_ambient_transcript(text: str) -> bool:
    """Discard STT that mirrors TV / ambient monologue (not directed speech)."""
    t = (text or "").strip()
    if not t:
        return False
    return bool(_MEDIA_AMBIENT.search(t))


def _is_suspicious_ambient_transcript(text: str) -> bool:
    """Discard STT that looks like assistant/therapy speech from ambient noise."""
    t = (text or "").strip()
    if not t:
        return False
    if _AMBIENT_HALLUCINATION.search(t):
        return True
    if _ASSISTANT_LIKE_STT.match(t) and not plan_extractor.needs_plan_extraction(t):
        return True
    return False


def _user_expresses_emotion(text: str) -> bool:
    t = (text or "").lower()
    return bool(
        re.search(
            r"\b(scared|afraid|anxious|sad|depressed|lonely|sorry|apologize|upset|worried|stressed)\b",
            t,
        )
    )


def _day_label_for_due(due_at, local_day: date, tz: ZoneInfo) -> str:
    if due_at is None:
        return "Today"
    try:
        if isinstance(due_at, datetime):
            dt = due_at
        else:
            dt = datetime.fromisoformat(str(due_at).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=tz)
        task_day = dt.astimezone(tz).date()
        if task_day == local_day:
            return "Today"
        if task_day == local_day + timedelta(days=1):
            return "Tomorrow"
        return task_day.strftime("%A, %b %d")
    except (ValueError, TypeError):
        return "Today"


def _is_nonsense_transcript(text: str) -> bool:
    """Discard repetitive or semantically empty STT from ambient noise."""
    t = (text or "").strip()
    if not t:
        return True
    lower = t.lower()
    if re.search(r"\b(put it in the air|put it on the back|back of the head)\b", lower):
        return True
    if re.search(r"^(i'?m going to put|i'?m gonna put)\b", lower):
        return True
    words = lower.split()
    if len(words) >= 4:
        if len(set(words)) / len(words) < 0.45:
            return True
        if words.count(words[0]) >= max(3, len(words) // 2):
            return True
    return False


async def _extract_plan_for_turn(
    text: str,
    *,
    wake_name: str,
    timezone: str,
    history_summary: str,
    local_day,
) -> dict:
    """Regex-first for edits, then LLM extraction when needed."""
    extracted: dict | None = None
    try:
        tzinfo = ZoneInfo(timezone or "UTC")
    except Exception:
        tzinfo = ZoneInfo("UTC")

    booking = plan_extractor._regex_booking_fallback(text, local_day, tzinfo)
    if booking:
        extracted = booking
    elif plan_intent.is_edit_request(text):
        regex_edit = plan_extractor._regex_edit_fallback(text, local_day, tzinfo)
        if regex_edit:
            extracted = regex_edit
    if extracted is None and plan_extractor.needs_plan_extraction(text):
        extracted = await plan_extractor.extract_plan(
            text,
            wake_name=wake_name,
            timezone=timezone,
            history_summary=history_summary,
            today=local_day,
        )
    return extracted if extracted is not None else dict(_EMPTY_PLAN)


def _is_edit_draft(payload: dict | None) -> bool:
    return bool(payload and payload.get("intent") == "edit_task" and payload.get("edits"))


def _has_mutation_tool_action(tool_actions: list[str]) -> bool:
    return plan_intent.has_mutation_tool_action(tool_actions)


def _draft_to_schema(payload: dict | None) -> PlanDraftResponse | None:
    if not payload or not payload.get("proposed_tasks"):
        return None
    
    proposed_tasks = [ProposedTask(**t) for t in payload["proposed_tasks"]]
    smart_follow_ups = None
    
    # Compute smart follow-ups for the first proposed task
    if proposed_tasks:
        first_task = payload["proposed_tasks"][0]
        smart_follow_ups = reflection_svc.smart_follow_up_prompts(first_task)
    
    return PlanDraftResponse(
        intent=payload.get("intent", "plan_day"),
        proposed_tasks=proposed_tasks,
        clarifying_question=payload.get("clarifying_question"),
        smart_follow_ups=smart_follow_ups,
    )


def _has_confirmed_plan(tool_actions: list[str]) -> bool:
    return any(a.startswith("Confirmed plan:") for a in tool_actions)


def _format_time_label(due_at, tz: ZoneInfo | None = None) -> str:
    if due_at is None:
        return ""
    try:
        if isinstance(due_at, datetime):
            dt = due_at
        else:
            dt = datetime.fromisoformat(str(due_at).replace("Z", "+00:00"))
        if tz is not None:
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=tz)
            dt = dt.astimezone(tz)
        elif dt.tzinfo is not None:
            dt = dt.astimezone(ZoneInfo("UTC"))
        return dt.strftime("%-I:%M %p") if os.name != "nt" else dt.strftime("%I:%M %p").lstrip("0")
    except (ValueError, TypeError):
        return ""


def _confirmed_reply(
    created: list[dict],
    *,
    local_day: date,
    tz: ZoneInfo,
    default_minutes: int = 60,
) -> tuple[str, str]:
    names = ", ".join(c["title"] for c in created)
    tool_msg = f"Confirmed plan: {names}"
    first = created[0]
    mins = first.get("estimated_minutes") or default_minutes
    time_label = _format_time_label(first.get("due_at"), tz)
    day_label = _day_label_for_due(first.get("due_at"), local_day, tz)
    if time_label:
        reply = (
            f"Done — I've added {first['title']} at {time_label} on {day_label} "
            f"({mins} minutes — tap to edit on Today)."
        )
    else:
        reply = f"Done — I've added {names} on {day_label}."
    return reply, tool_msg


_SENTENCE_END = re.compile(r'[.!?](?:\s|$)')


async def _resolve_early_tts(
    raw_reply: str,
    final_reply: str,
    early_first_sent: str | None,
    early_tts_task: "asyncio.Task | None",
    voice: str | None,
    early_audio: dict | None,
    session_id: str,
) -> None:
    """Reconcile a speculatively-started first-sentence TTS task against the
    final (post-safety-check) reply text.

    If the safety checks (honesty override / therapy blanking / mutation
    recovery) left the reply byte-for-byte unchanged, the speculative audio
    is reused (populating early_audio in place) -- this is the latency win.
    If the reply was rewritten by any safety check, the speculative audio no
    longer matches what will be spoken, so it is discarded (task cancelled,
    early_audio left empty) and the caller falls back to synthesizing the
    final text fresh, exactly as it did before early-TTS existed -- so a
    safety override can never result in stale/wrong audio being played.
    """
    if early_tts_task is None:
        return
    if final_reply != raw_reply or not early_first_sent:
        early_tts_task.cancel()
        agent_debug(
            "H3",
            "router._reply_for_text",
            "early_tts_discarded_reply_overridden",
            {"session_id": session_id},
        )
        return

    first_bytes, first_mime = await early_tts_task
    if final_reply == early_first_sent:
        if early_audio is not None:
            early_audio["bytes"] = first_bytes
            early_audio["mime"] = first_mime
    else:
        remainder = final_reply[len(early_first_sent):].strip()
        if remainder:
            remainder_bytes, remainder_mime = await synthesize(remainder, voice)
            if remainder_mime == first_mime and early_audio is not None:
                early_audio["bytes"] = first_bytes + remainder_bytes
                early_audio["mime"] = first_mime
        elif early_audio is not None:
            early_audio["bytes"] = first_bytes
            early_audio["mime"] = first_mime
    agent_debug(
        "H3",
        "router._reply_for_text",
        "early_tts_used" if (early_audio or {}).get("bytes") else "early_tts_discarded_mime_mismatch",
        {"session_id": session_id},
    )



async def _recover_edit_from_history(
    db: AsyncSession,
    user: User,
    history: list[dict[str, str]],
    today_snap,
    *,
    local_day,
    tz: str,
    wake_name: str,
    history_summary: str,
) -> tuple[str, list[str]] | None:
    result = await act_svc.recover_edit_from_history(
        db,
        user.id,
        history,
        today_snap,
        timezone=tz,
        wake_name=wake_name,
        history_summary=history_summary,
        local_day=local_day,
    )
    if not result or not result.handled or not result.tool_actions:
        return None
    return result.reply or "Done — I've updated your task on Today.", result.tool_actions


async def _recover_and_confirm_from_history(
    db: AsyncSession,
    user: User,
    history: list[dict[str, str]],
    *,
    local_day,
    tz: str,
    wake_name: str,
    history_summary: str,
) -> tuple[str, str] | None:
    """Re-extract from prior offer, save draft, confirm, return (reply, tool_msg) or None."""
    try:
        tzinfo = ZoneInfo(tz or "UTC")
    except Exception:
        tzinfo = ZoneInfo("UTC")
    if not plan_intent.assistant_offered_to_add(history):
        return None
    recovery_text = plan_intent.recovery_context_from_history(history)
    if not recovery_text.strip():
        return None
    extracted = await plan_extractor.extract_plan(
        recovery_text,
        wake_name=wake_name,
        timezone=tz,
        history_summary=history_summary,
        today=local_day,
    )
    tasks = extracted.get("proposed_tasks") or []
    if not tasks or not any(t.get("due_at") for t in tasks):
        return None
    extracted = plan_intent.ensure_recovery_duration(extracted)
    await draft_svc.save_draft(db, user.id, extracted)
    created = await draft_svc.confirm_draft(db, user.id, timezone=tz)
    if not created:
        return None
    return _confirmed_reply(created, local_day=local_day, tz=tzinfo)


async def _reply_for_text(
    db: AsyncSession,
    user: User,
    text: str,
    session_id: str | None = None,
    *,
    channel: str = "text",
    voice: str | None = None,
    early_audio: dict | None = None,
) -> tuple[str, bool, list[str], str, PlanDraftResponse | None, MusicCommand | None]:
    sid = session_id or str(uuid.uuid4())
    if is_crisis_likely(text):
        return crisis_reply(), True, [], sid, None, None

    local_day = user_local_today(user.timezone)
    tz = user.timezone or "UTC"
    try:
        tzinfo = ZoneInfo(tz)
    except Exception:
        tzinfo = ZoneInfo("UTC")
    try:
        local_now = datetime.now(tzinfo)
    except Exception:
        local_now = datetime.now(ZoneInfo("UTC"))

    history, pending_early = await asyncio.gather(
        conv_svc.load_history(db, user.id, sid),
        draft_svc.get_draft(db, user.id),
    )
    history_summary = "\n".join(f"{h['role']}: {h['content'][:200]}" for h in history[-6:])
    wake = user.wake_name or user.display_name or "friend"

    if pending_early and (pending_early.get("proposed_tasks") or _is_edit_draft(pending_early)):
        if plan_intent.is_confirm_intent(text):
            if _is_edit_draft(pending_early):
                today_snap_early = await task_svc.today_view(db, user.id, local_day, timezone=tz)
                edit_result = await act_svc.confirm_edit_draft(
                    db, user.id, pending_early, today_snap_early, timezone=tz
                )
                reply = edit_result.reply or _HONEST_NOT_CHANGED
                tool_msg = edit_result.tool_actions or []
                await conv_svc.append_turn(db, user.id, sid, "user", text)
                await conv_svc.append_turn(db, user.id, sid, "assistant", reply)
                return reply, False, tool_msg, sid, None, None
            created = await draft_svc.confirm_draft(db, user.id, timezone=tz)
            if created:
                reply, tool_msg = _confirmed_reply(created, local_day=local_day, tz=tzinfo)
            else:
                reply = "Got it — those are already on Today."
                tool_msg = "Confirmed plan: duplicates skipped"
            await conv_svc.append_turn(db, user.id, sid, "user", text)
            await conv_svc.append_turn(db, user.id, sid, "assistant", reply)
            return reply, False, [tool_msg], sid, None, None
        if plan_intent.is_discard_intent(text):
            await draft_svc.clear_draft(db, user.id)
            reply = "Okay, I won't add that plan to Today."
            await conv_svc.append_turn(db, user.id, sid, "user", text)
            await conv_svc.append_turn(db, user.id, sid, "assistant", reply)
            return reply, False, ["Discarded plan draft"], sid, None, None

    if plan_intent.is_confirm_intent(text) and not (
        pending_early and (pending_early.get("proposed_tasks") or _is_edit_draft(pending_early))
    ):
        today_snap_early = await task_svc.today_view(db, user.id, local_day, timezone=tz)
        edit_recovered = await _recover_edit_from_history(
            db,
            user,
            history,
            today_snap_early,
            local_day=local_day,
            tz=tz,
            wake_name=wake,
            history_summary=history_summary,
        )
        if edit_recovered:
            reply, tool_msgs = edit_recovered
            await conv_svc.append_turn(db, user.id, sid, "user", text)
            await conv_svc.append_turn(db, user.id, sid, "assistant", reply)
            uid = str(user.id)
            asyncio.create_task(asyncio.to_thread(remember_turn, uid, role="user", text=text, session_id=sid))
            asyncio.create_task(asyncio.to_thread(remember_turn, uid, role="assistant", text=reply, session_id=sid))
            return reply, False, tool_msgs, sid, None, None
        if plan_intent.assistant_offered_to_update(history) and not plan_intent.assistant_offered_to_add(
            history
        ):
            reply = _HONEST_NOT_CHANGED
            await conv_svc.append_turn(db, user.id, sid, "user", text)
            await conv_svc.append_turn(db, user.id, sid, "assistant", reply)
            return reply, False, [], sid, None, None
        recovered = await _recover_and_confirm_from_history(
            db,
            user,
            history,
            local_day=local_day,
            tz=tz,
            wake_name=wake,
            history_summary=history_summary,
        )
        if recovered:
            reply, tool_msg = recovered
            await conv_svc.append_turn(db, user.id, sid, "user", text)
            await conv_svc.append_turn(db, user.id, sid, "assistant", reply)
            uid = str(user.id)
            asyncio.create_task(asyncio.to_thread(remember_turn, uid, role="user", text=text, session_id=sid))
            asyncio.create_task(asyncio.to_thread(remember_turn, uid, role="assistant", text=reply, session_id=sid))
            return reply, False, [tool_msg], sid, None, None
        if plan_intent.assistant_offered_to_add(history):
            reply = _HONEST_NO_PENDING
            await conv_svc.append_turn(db, user.id, sid, "user", text)
            await conv_svc.append_turn(db, user.id, sid, "assistant", reply)
            return reply, False, [], sid, None, None

    tool_actions, today_snap = await asyncio.gather(
        task_svc.apply_task_tools_from_text(db, user.id, text, timezone=tz),
        task_svc.today_view(db, user.id, local_day, timezone=tz),
    )
    music_command: MusicCommand | None = None
    companion = await ctx_svc.build_companion_context(db, user, text, today_snap=today_snap)

    if plan_extractor.needs_plan_extraction(text):
        extracted = await _extract_plan_for_turn(
            text,
            wake_name=user.wake_name or user.display_name or "friend",
            timezone=tz,
            history_summary=history_summary,
            local_day=local_day,
        )
    else:
        extracted = dict(_EMPTY_PLAN)

    if extracted.get("intent") == "complete_task":
        completion_actions = await task_svc.complete_tasks_from_extraction(
            db, user.id, extracted, local_day, timezone=tz
        )
        tool_actions.extend(completion_actions)
        if completion_actions:
            today_snap = await task_svc.today_view(db, user.id, local_day, timezone=tz)

    if extracted.get("intent") == "music_control":
        music_action = extracted.get("music_action") or "play"
        music_query = extracted.get("music_query")
        music_command = MusicCommand(
            provider="spotify",
            action=music_action,
            query=music_query,
            mode="android_deep_link",
        )
        label = (music_query or music_action).strip() if isinstance(music_query, str) else music_action
        tool_actions.append(f"Music: queued on device — {music_action} ({label})")

    if extracted.get("intent") == "edit_task":
        lower = (text or "").lower()
        if plan_intent._BOOKING_SIGNAL.search(lower) and re.search(r"\b(book|schedule)\b", lower):
            if not plan_intent.is_edit_request(text):
                booking = plan_extractor._regex_booking_fallback(text, local_day, tzinfo)
                extracted = booking if booking else dict(_EMPTY_PLAN)

    if extracted.get("intent") == "edit_task":
        edit_result = await act_svc.try_handle_edit_extraction(
            db, user.id, text, extracted, today_snap, timezone=tz
        )
        if edit_result and edit_result.handled:
            reply = edit_result.reply or _HONEST_NOT_CHANGED
            if edit_result.refresh_today:
                today_snap = await task_svc.today_view(db, user.id, local_day, timezone=tz)
            await conv_svc.append_turn(db, user.id, sid, "user", text)
            await conv_svc.append_turn(db, user.id, sid, "assistant", reply)
            uid = str(user.id)
            asyncio.create_task(asyncio.to_thread(remember_turn, uid, role="user", text=text, session_id=sid))
            asyncio.create_task(asyncio.to_thread(remember_turn, uid, role="assistant", text=reply, session_id=sid))
            return reply, False, edit_result.tool_actions or [], sid, None, None

    delete_result = await act_svc.try_handle_delete(db, user.id, text, today_snap)
    if delete_result and delete_result.handled:
        reply = delete_result.reply or "Done."
        if delete_result.refresh_today:
            today_snap = await task_svc.today_view(db, user.id, local_day, timezone=tz)
        await conv_svc.append_turn(db, user.id, sid, "user", text)
        await conv_svc.append_turn(db, user.id, sid, "assistant", reply)
        uid = str(user.id)
        asyncio.create_task(asyncio.to_thread(remember_turn, uid, role="user", text=text, session_id=sid))
        asyncio.create_task(asyncio.to_thread(remember_turn, uid, role="assistant", text=reply, session_id=sid))
        return reply, False, delete_result.tool_actions or [], sid, None, None

    # Handle delete_task intent from extraction
    delete_extraction_result = await act_svc.try_handle_delete_extraction(db, user.id, extracted, today_snap)
    if delete_extraction_result and delete_extraction_result.handled:
        reply = delete_extraction_result.reply or "Done."
        if delete_extraction_result.refresh_today:
            today_snap = await task_svc.today_view(db, user.id, local_day, timezone=tz)
        await conv_svc.append_turn(db, user.id, sid, "user", text)
        await conv_svc.append_turn(db, user.id, sid, "assistant", reply)
        uid = str(user.id)
        asyncio.create_task(asyncio.to_thread(remember_turn, uid, role="user", text=text, session_id=sid))
        asyncio.create_task(asyncio.to_thread(remember_turn, uid, role="assistant", text=reply, session_id=sid))
        return reply, False, delete_extraction_result.tool_actions or [], sid, None, None

    # Handle mark_urgent intent from extraction
    mark_urgent_result = await act_svc.try_handle_mark_urgent_extraction(db, user.id, extracted, today_snap)
    if mark_urgent_result and mark_urgent_result.handled:
        reply = mark_urgent_result.reply or "Done."
        if mark_urgent_result.refresh_today:
            today_snap = await task_svc.today_view(db, user.id, local_day, timezone=tz)
        await conv_svc.append_turn(db, user.id, sid, "user", text)
        await conv_svc.append_turn(db, user.id, sid, "assistant", reply)
        uid = str(user.id)
        asyncio.create_task(asyncio.to_thread(remember_turn, uid, role="user", text=text, session_id=sid))
        asyncio.create_task(asyncio.to_thread(remember_turn, uid, role="assistant", text=reply, session_id=sid))
        return reply, False, mark_urgent_result.tool_actions or [], sid, None, None

    plan_draft_payload = None
    auto_confirmed = False
    if extracted.get("proposed_tasks") and extracted.get("intent") != "complete_task":
        if not plan_extractor.should_defer_draft(extracted):
            await draft_svc.save_draft(db, user.id, extracted)
            booking_ok = plan_intent.is_complete_booking_request(
                text, extracted, local_day=local_day, timezone=tz
            )
            # #region agent log
            agent_debug(
                "H4",
                "router._reply_for_text",
                "booking_check",
                {
                    "channel": channel,
                    "booking_ok": booking_ok,
                    "relative_day": plan_extractor._relative_day_offset(text),
                    "tasks": [
                        {"title": t.get("title"), "due_at": t.get("due_at")}
                        for t in (extracted.get("proposed_tasks") or [])
                    ],
                },
            )
            # #endregion
            if channel == "audio" and booking_ok:
                created = await draft_svc.confirm_draft(db, user.id, timezone=tz)
                if created:
                    reply, tool_msg = _confirmed_reply(created, local_day=local_day, tz=tzinfo)
                    tool_actions.append(tool_msg)
                    today_snap = await task_svc.today_view(db, user.id, local_day, timezone=tz)
                    auto_confirmed = True
                    plan_draft_payload = None
                    await conv_svc.append_turn(db, user.id, sid, "user", text)
                    await conv_svc.append_turn(db, user.id, sid, "assistant", reply)
                    uid = str(user.id)
                    asyncio.create_task(asyncio.to_thread(remember_turn, uid, role="user", text=text, session_id=sid))
                    asyncio.create_task(asyncio.to_thread(remember_turn, uid, role="assistant", text=reply, session_id=sid))
                    return reply, False, tool_actions, sid, None, None
                plan_draft_payload = extracted
            else:
                plan_draft_payload = extracted

    pending = await draft_svc.get_draft(db, user.id) if not auto_confirmed else None
    system_ctx = ctx_svc.format_system_context(
        wake=wake,
        about_me=user.about_me,
        local_day=local_day,
        local_now=local_now,
        timezone=tz,
        today_snap=today_snap,
        companion=companion,
        tool_actions=tool_actions,
        pending=pending,
        extracted=extracted,
        history=history,
        auto_confirmed=auto_confirmed,
        city=getattr(user, "city", None),
        country_code=getattr(user, "country_code", None),
        audio_channel=True,
    )

    if auto_confirmed:
        names = next(
            (a.replace("Confirmed plan: ", "") for a in tool_actions if a.startswith("Confirmed plan:")),
            "your appointment",
        )
        reply = f"Done — I've added {names} to Today."
        await conv_svc.append_turn(db, user.id, sid, "user", text)
        await conv_svc.append_turn(db, user.id, sid, "assistant", reply)
        uid = str(user.id)
        asyncio.create_task(asyncio.to_thread(remember_turn, uid, role="user", text=text, session_id=sid))
        asyncio.create_task(asyncio.to_thread(remember_turn, uid, role="assistant", text=reply, session_id=sid))
        return reply, False, tool_actions, sid, None, music_command

    messages = list(history)
    prefix = "[Context" if not messages else "[State"
    messages.append({"role": "user", "content": f"{prefix}: {system_ctx}]\n\n{text}"})

    _early_first_sent: str | None = None
    _early_tts_task: asyncio.Task | None = None
    if channel == "audio":
        # Use streaming for voice turns to reduce time-to-first-token. When a
        # voice is given, also speculatively start TTS on the first complete
        # sentence while the rest keeps streaming, overlapping TTS latency
        # with LLM generation instead of running them fully sequentially.
        # The speculative audio is only used (see below, after the safety
        # checks) if those checks leave the reply unchanged; otherwise it is
        # discarded and the caller synthesizes fresh -- never a regression.
        reply_tokens: list[str] = []
        async for token in llm_stream(messages):
            reply_tokens.append(token)
            if voice and _early_first_sent is None:
                _accumulated = "".join(reply_tokens)
                if _SENTENCE_END.search(_accumulated):
                    _early_first_sent = _accumulated.strip()
                    _early_tts_task = asyncio.create_task(
                        synthesize(_early_first_sent, voice)
                    )
        reply = "".join(reply_tokens).strip()
    else:
        reply = await llm_chat(messages)
    _raw_llm_reply = reply

    if re.search(r"\bi['']?ll add\b|\bi will add\b", reply, re.IGNORECASE) and not (
        _has_mutation_tool_action(tool_actions) or _has_confirmed_plan(tool_actions)
    ):
        agent_debug(
            "H5",
            "router._reply_for_text",
            "llm_add_claim_blocked",
            {"reply_preview": reply[:120]},
        )
        reply = _HONEST_NOT_ADDED

    if _THERAPY_REPLY.search(reply) and not _user_expresses_emotion(text):
        # #region agent log
        agent_debug(
            "H2",
            "router._reply_for_text",
            "therapy_reply_blocked",
            {"transcript_preview": text[:120], "reply_preview": reply[:120]},
        )
        # #endregion
        reply = ""

    if plan_intent.reply_claims_mutation(reply) and not _has_mutation_tool_action(tool_actions):
        edit_recovered = await _recover_edit_from_history(
            db,
            user,
            history + [{"role": "user", "content": text}, {"role": "assistant", "content": reply}],
            today_snap,
            local_day=local_day,
            tz=tz,
            wake_name=wake,
            history_summary=history_summary,
        )
        if edit_recovered:
            reply, tool_msgs = edit_recovered
            tool_actions.extend(tool_msgs)
            today_snap = await task_svc.today_view(db, user.id, local_day, timezone=tz)
        elif plan_intent.reply_claims_success(reply) and not _has_confirmed_plan(tool_actions):
            recovered = await _recover_and_confirm_from_history(
                db,
                user,
                history + [{"role": "user", "content": text}, {"role": "assistant", "content": reply}],
                local_day=local_day,
                tz=tz,
                wake_name=wake,
                history_summary=history_summary,
            )
            if recovered:
                reply, tool_msg = recovered
                tool_actions.append(tool_msg)
                today_snap = await task_svc.today_view(db, user.id, local_day, timezone=tz)
            else:
                reply = _HONEST_NOT_ADDED
        else:
            reply = _HONEST_NOT_CHANGED

    await _resolve_early_tts(
        _raw_llm_reply, reply, _early_first_sent, _early_tts_task, voice, early_audio, sid
    )

    await conv_svc.append_turn(db, user.id, sid, "user", text)
    await conv_svc.append_turn(db, user.id, sid, "assistant", reply)
    uid = str(user.id)
    asyncio.create_task(asyncio.to_thread(remember_turn, uid, role="user", text=text, session_id=sid))
    asyncio.create_task(asyncio.to_thread(remember_turn, uid, role="assistant", text=reply, session_id=sid))

    return reply, False, tool_actions, sid, _draft_to_schema(plan_draft_payload or pending), music_command


@router.post("/turn/text", response_model=TextTurnResponse)
async def text_turn(
    body: TextTurnRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    reply, crisis, tool_actions, sid, draft, music_command = await _reply_for_text(
        db, user, body.text, body.session_id
    )
    return TextTurnResponse(
        reply=reply,
        crisis=crisis,
        tool_actions=tool_actions,
        session_id=sid,
        plan_draft=draft,
        music_command=music_command,
    )


@router.post("/turn/text/stream")
async def text_turn_stream(
    body: TextTurnRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """SSE streaming endpoint: emits tokens as they arrive, then a final 'done' event.

    Event format:
      data: {"type": "token", "token": "..."}   — one per streamed token
      data: {"type": "done", "reply": "...", "tool_actions": [...], "session_id": "...", "crisis": false}
    """
    from fastapi.responses import StreamingResponse

    reply, crisis, tool_actions, sid, draft, music_command = await _reply_for_text(
        db, user, body.text, body.session_id
    )

    async def event_generator():
        for token in reply:
            payload = json.dumps({"type": "token", "token": token})
            yield f"data: {payload}\n\n"
        done_payload = json.dumps({
            "type": "done",
            "reply": reply,
            "crisis": crisis,
            "tool_actions": tool_actions,
            "session_id": sid,
            "plan_draft": draft.model_dump() if draft else None,
            "music_command": music_command.model_dump() if music_command else None,
        })
        yield f"data: {done_payload}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.post("/turn/audio", response_model=AudioTurnResponse)
async def audio_turn(
    file: UploadFile = File(...),
    session_id: str | None = Form(None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    raw = await file.read()
    sid = session_id or str(uuid.uuid4())
    t0 = time.monotonic()
    agent_debug("A", "router.audio_turn", "audio_upload_received", {"bytes": len(raw), "user_id": str(user.id)})
    if not raw:
        return AudioTurnResponse(
            transcript="",
            reply="",
            session_id=sid,
            skip_tts=True,
        )

    suffix = Path(file.filename or "turn.m4a").suffix.lower() or ".m4a"
    fd, tmp_path = tempfile.mkstemp(suffix=suffix, prefix="aipal-v2-")
    os.close(fd)
    try:
        Path(tmp_path).write_bytes(raw)
        t_stt = time.monotonic()
        transcript = await asyncio.to_thread(transcribe_path, tmp_path)
        stt_ms = int((time.monotonic() - t_stt) * 1000)
    finally:
        Path(tmp_path).unlink(missing_ok=True)

    if not (transcript or "").strip():
        await sess_svc.safe_record_event(
            db,
            user.id,
            sid,
            "stt_empty",
            payload={"bytes": len(raw), "stt_ms": stt_ms},
        )
        agent_debug(
            "H2",
            "router.audio_turn",
            "stt_empty",
            {"bytes": len(raw), "stt_ms": stt_ms, "session_id": sid},
        )
        return AudioTurnResponse(
            transcript="",
            reply="",
            session_id=sid,
            skip_tts=True,
        )

    transcript = transcript.strip()
    if _is_low_signal_transcript(transcript):
        await sess_svc.safe_record_event(
            db,
            user.id,
            sid,
            "stt_low_signal",
            payload={"transcript": transcript, "stt_ms": stt_ms},
        )
        return AudioTurnResponse(
            transcript=transcript,
            reply="",
            session_id=sid,
            skip_tts=True,
        )

    if _is_suspicious_ambient_transcript(transcript) or _is_media_ambient_transcript(transcript):
        await sess_svc.safe_record_event(
            db,
            user.id,
            sid,
            "stt_ambient_hallucination",
            payload={"transcript": transcript, "stt_ms": stt_ms},
        )
        agent_debug(
            "H2",
            "router.audio_turn",
            "stt_ambient_discarded",
            {"transcript_preview": transcript[:120], "session_id": sid},
        )
        return AudioTurnResponse(
            transcript=transcript,
            reply="",
            session_id=sid,
            skip_tts=True,
        )

    if _is_nonsense_transcript(transcript):
        await sess_svc.safe_record_event(
            db,
            user.id,
            sid,
            "stt_nonsense",
            payload={"transcript": transcript, "stt_ms": stt_ms},
        )
        agent_debug(
            "H2",
            "router.audio_turn",
            "stt_nonsense_discarded",
            {"transcript_preview": transcript[:120], "session_id": sid},
        )
        return AudioTurnResponse(
            transcript=transcript,
            reply="",
            session_id=sid,
            skip_tts=True,
        )

    chosen_voice = get_voice_id(getattr(user, "tts_voice", "aria"))
    early_audio: dict = {}
    t_reply = time.monotonic()
    reply, crisis, tool_actions, sid, draft, music_command = await _reply_for_text(
        db, user, transcript, sid, channel="audio", voice=chosen_voice, early_audio=early_audio
    )
    reply_ms = int((time.monotonic() - t_reply) * 1000)
    # #region agent log
    agent_debug(
        "H3",
        "router.audio_turn",
        "stt_ok",
        {
            "bytes": len(raw),
            "transcript_preview": transcript[:120],
            "reply_len": len(reply),
            "tool_actions": tool_actions[:3],
            "stt_ms": stt_ms,
            "reply_ms": reply_ms,
            "session_id": sid,
        },
    )
    # #endregion

    if not (reply or "").strip():
        return AudioTurnResponse(
            transcript=transcript.strip(),
            reply="",
            session_id=sid,
            skip_tts=True,
            tool_actions=tool_actions,
            plan_draft=draft,
            music_command=music_command,
        )

    if reply == _HONEST_NOT_ADDED and not plan_extractor.needs_plan_extraction(transcript):
        agent_debug(
            "H5",
            "router.audio_turn",
            "honest_not_added_suppressed",
            {"transcript_preview": transcript[:120], "session_id": sid},
        )
        return AudioTurnResponse(
            transcript=transcript.strip(),
            reply="",
            session_id=sid,
            skip_tts=True,
            tool_actions=tool_actions,
            plan_draft=draft,
            music_command=music_command,
        )

    draft_confirmed = bool(
        tool_actions and any(a.startswith("Confirmed plan:") for a in tool_actions)
    )
    t_tts = time.monotonic()
    if early_audio.get("bytes"):
        audio_bytes, audio_mime = early_audio["bytes"], early_audio["mime"]
    else:
        audio_bytes, audio_mime = await synthesize(reply, chosen_voice)
    tts_ms = int((time.monotonic() - t_tts) * 1000)
    total_ms = int((time.monotonic() - t0) * 1000)

    await sess_svc.safe_record_event(
        db,
        user.id,
        sid,
        "audio_turn_complete",
        payload={
            "bytes": len(raw),
            "transcript_len": len(transcript.strip()),
            "reply_len": len(reply),
            "stt_ms": stt_ms,
            "reply_ms": reply_ms,
            "tts_ms": tts_ms,
            "total_ms": total_ms,
        },
    )

    return AudioTurnResponse(
        transcript=transcript.strip(),
        reply=reply,
        crisis=crisis,
        tool_actions=tool_actions,
        plan_draft=draft,
        draft_confirmed=draft_confirmed,
        music_command=music_command,
        session_id=sid,
        audio_base64=base64.b64encode(audio_bytes).decode("ascii") if audio_bytes else None,
        audio_mime=audio_mime if audio_bytes else None,
    )


@router.post("/turn/tts", response_model=TtsResponse)
async def tts_turn(body: TtsRequest, user: User = Depends(get_current_user)):
    text = (body.text or "").strip()
    if not text:
        return TtsResponse(text="")
    chosen_voice = get_voice_id(getattr(user, "tts_voice", "aria"))
    audio_bytes, audio_mime = await synthesize(text, chosen_voice)
    return TtsResponse(
        text=text,
        audio_base64=base64.b64encode(audio_bytes).decode("ascii") if audio_bytes else None,
        audio_mime=audio_mime if audio_bytes else None,
    )


@router.get("/voice/catalogue", response_model=list[VoiceCatalogueItem])
async def voice_catalogue(_user: User = Depends(get_current_user)):
    """Return the curated voice options available for Companion TTS."""
    return [
        VoiceCatalogueItem(
            id=v["id"],
            display_name=v["display_name"],
            gender=v["gender"],
            style=v["style"],
            is_default=v["is_default"],
            sample_phrase=v["sample_phrase"],
        )
        for v in VOICE_CATALOGUE
    ]


class VoicePreviewRequest(BaseModel):
    voice_id: str


@router.post("/voice/preview")
async def voice_preview(body: VoicePreviewRequest, _user: User = Depends(get_current_user)):
    """Synthesize a short sample phrase in the requested voice. Returns audio/mpeg bytes."""
    sample_phrase = "Hi, I'm your AiPal Companion — ready when you are."
    edge_voice = get_voice_id(body.voice_id)
    audio_bytes, audio_mime = await synthesize(sample_phrase, edge_voice)
    if not audio_bytes:
        from fastapi import HTTPException
        raise HTTPException(status_code=502, detail="TTS synthesis failed")
    from fastapi.responses import Response as RawResponse
    return RawResponse(content=audio_bytes, media_type=audio_mime)
