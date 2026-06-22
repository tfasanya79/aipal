import asyncio
import base64
import json
import logging
import os
import tempfile
import time
import uuid
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.service import get_current_user
from app.shared.db import get_db
from app.modules.brain.llm_provider import llm_chat
from app.modules.brain.memory import remember_turn
from app.shared.models import User
from app.modules.brain.safety import crisis_reply, is_crisis_likely
from app.shared.schemas import AudioTurnResponse, PlanDraftResponse, ProposedTask, TextTurnRequest, TextTurnResponse, TtsRequest, TtsResponse
from app.modules.brain import conversation as conv_svc
from app.modules.brain import context_builder as ctx_svc
from app.modules.today import plan_draft as draft_svc
from app.modules.brain import plan_extractor
from app.modules.brain import plan_intent
from app.modules.voice import session_events as sess_svc
from app.modules.today import tasks as task_svc
from app.shared.timezone_util import user_local_today
from app.modules.voice.stt import transcribe_path
from app.modules.voice.tts import synthesize

router = APIRouter(tags=["turn"])
log = logging.getLogger("aipal.turn")
DEBUG_LOG = "/home/dev/.cursor/debug-60ce92.log"

_EMPTY_PLAN = {"intent": "other", "proposed_tasks": [], "clarifying_question": None}
_HONEST_NO_PENDING = (
    "I don't have a saved item to add yet. Tell me the time and I'll put it on Today."
)
_HONEST_NOT_ADDED = (
    "I haven't added anything yet — tell me the time and duration and I'll put it on Today."
)


def _agent_debug(hypothesis_id: str, location: str, message: str, data: dict, run_id: str = "pre-fix") -> None:
    if os.environ.get("AGENT_DEBUG") != "1":
        return
    try:
        entry = {
            "sessionId": "60ce92",
            "hypothesisId": hypothesis_id,
            "location": location,
            "message": message,
            "data": data,
            "timestamp": int(time.time() * 1000),
            "runId": run_id,
        }
        with open(DEBUG_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
    except OSError:
        log.info("AGENT_DEBUG %s", json.dumps(entry))


def _draft_to_schema(payload: dict | None) -> PlanDraftResponse | None:
    if not payload or not payload.get("proposed_tasks"):
        return None
    return PlanDraftResponse(
        intent=payload.get("intent", "plan_day"),
        proposed_tasks=[ProposedTask(**t) for t in payload["proposed_tasks"]],
        clarifying_question=payload.get("clarifying_question"),
    )


def _has_confirmed_plan(tool_actions: list[str]) -> bool:
    return any(a.startswith("Confirmed plan:") for a in tool_actions)


def _format_time_label(due_at) -> str:
    if due_at is None:
        return ""
    if hasattr(due_at, "strftime"):
        return due_at.strftime("%-I:%M %p") if os.name != "nt" else due_at.strftime("%I:%M %p").lstrip("0")
    try:
        dt = datetime.fromisoformat(str(due_at).replace("Z", "+00:00"))
        return dt.strftime("%I:%M %p").lstrip("0")
    except ValueError:
        return ""


def _confirmed_reply(created: list[dict], *, default_minutes: int = 60) -> tuple[str, str]:
    names = ", ".join(c["title"] for c in created)
    tool_msg = f"Confirmed plan: {names}"
    first = created[0]
    mins = first.get("estimated_minutes") or default_minutes
    time_label = _format_time_label(first.get("due_at"))
    if time_label:
        reply = (
            f"Done — I've added {first['title']} at {time_label} to Today "
            f"({mins} minutes — tap to edit on Today)."
        )
    else:
        reply = f"Done — I've added {names} to Today."
    return reply, tool_msg


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
    return _confirmed_reply(created)


async def _reply_for_text(
    db: AsyncSession,
    user: User,
    text: str,
    session_id: str | None = None,
    *,
    channel: str = "text",
) -> tuple[str, bool, list[str], str, PlanDraftResponse | None]:
    sid = session_id or str(uuid.uuid4())
    if is_crisis_likely(text):
        return crisis_reply(), True, [], sid, None

    local_day = user_local_today(user.timezone)
    tz = user.timezone or "UTC"
    try:
        local_now = datetime.now(ZoneInfo(tz))
    except Exception:
        local_now = datetime.now(ZoneInfo("UTC"))

    history, pending_early = await asyncio.gather(
        conv_svc.load_history(db, user.id, sid),
        draft_svc.get_draft(db, user.id),
    )
    history_summary = "\n".join(f"{h['role']}: {h['content'][:200]}" for h in history[-6:])
    wake = user.wake_name or user.display_name or "friend"

    if pending_early and pending_early.get("proposed_tasks"):
        if plan_intent.is_confirm_intent(text):
            created = await draft_svc.confirm_draft(db, user.id, timezone=tz)
            if created:
                names = ", ".join(c["title"] for c in created)
                reply = f"Done — I've added {names} to Today."
                tool_msg = f"Confirmed plan: {names}"
            else:
                reply = "Got it — those are already on Today."
                tool_msg = "Confirmed plan: duplicates skipped"
            await conv_svc.append_turn(db, user.id, sid, "user", text)
            await conv_svc.append_turn(db, user.id, sid, "assistant", reply)
            return reply, False, [tool_msg], sid, None
        if plan_intent.is_discard_intent(text):
            await draft_svc.clear_draft(db, user.id)
            reply = "Okay, I won't add that plan to Today."
            await conv_svc.append_turn(db, user.id, sid, "user", text)
            await conv_svc.append_turn(db, user.id, sid, "assistant", reply)
            return reply, False, ["Discarded plan draft"], sid, None

    if plan_intent.is_confirm_intent(text) and not (pending_early and pending_early.get("proposed_tasks")):
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
            return reply, False, [tool_msg], sid, None
        if plan_intent.assistant_offered_to_add(history):
            reply = _HONEST_NO_PENDING
            await conv_svc.append_turn(db, user.id, sid, "user", text)
            await conv_svc.append_turn(db, user.id, sid, "assistant", reply)
            return reply, False, [], sid, None

    tool_actions, today_snap = await asyncio.gather(
        task_svc.apply_task_tools_from_text(db, user.id, text, timezone=tz),
        task_svc.today_view(db, user.id, local_day, timezone=tz),
    )
    companion = await ctx_svc.build_companion_context(db, user, text, today_snap=today_snap)

    if plan_extractor.needs_plan_extraction(text):
        extracted = await plan_extractor.extract_plan(
            text,
            wake_name=user.wake_name or user.display_name or "friend",
            timezone=tz,
            history_summary=history_summary,
            today=local_day,
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

    plan_draft_payload = None
    auto_confirmed = False
    if extracted.get("proposed_tasks") and extracted.get("intent") != "complete_task":
        if not plan_extractor.should_defer_draft(extracted):
            await draft_svc.save_draft(db, user.id, extracted)
            if channel == "audio" and plan_intent.is_complete_booking_request(text, extracted):
                created = await draft_svc.confirm_draft(db, user.id, timezone=tz)
                if created:
                    names = ", ".join(c["title"] for c in created)
                    tool_actions.append(f"Confirmed plan: {names}")
                    today_snap = await task_svc.today_view(db, user.id, local_day, timezone=tz)
                    auto_confirmed = True
                    plan_draft_payload = None
                else:
                    plan_draft_payload = extracted
            else:
                plan_draft_payload = extracted

    pending = await draft_svc.get_draft(db, user.id) if not auto_confirmed else None
    system_ctx = ctx_svc.format_system_context(
        wake=wake,
        about_me=user.about_me,
        local_day=local_day,
        local_now=local_now,
        today_snap=today_snap,
        companion=companion,
        tool_actions=tool_actions,
        pending=pending,
        extracted=extracted,
        history=history,
        auto_confirmed=auto_confirmed,
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
        return reply, False, tool_actions, sid, None

    messages = list(history)
    prefix = "[Context" if not messages else "[State"
    messages.append({"role": "user", "content": f"{prefix}: {system_ctx}]\n\n{text}"})

    reply = await llm_chat(messages)

    if plan_intent.reply_claims_success(reply) and not _has_confirmed_plan(tool_actions):
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

    await conv_svc.append_turn(db, user.id, sid, "user", text)
    await conv_svc.append_turn(db, user.id, sid, "assistant", reply)
    uid = str(user.id)
    asyncio.create_task(asyncio.to_thread(remember_turn, uid, role="user", text=text, session_id=sid))
    asyncio.create_task(asyncio.to_thread(remember_turn, uid, role="assistant", text=reply, session_id=sid))

    return reply, False, tool_actions, sid, _draft_to_schema(plan_draft_payload or pending)


@router.post("/turn/text", response_model=TextTurnResponse)
async def text_turn(
    body: TextTurnRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    reply, crisis, tool_actions, sid, draft = await _reply_for_text(db, user, body.text, body.session_id)
    return TextTurnResponse(
        reply=reply,
        crisis=crisis,
        tool_actions=tool_actions,
        session_id=sid,
        plan_draft=draft,
    )


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
    _agent_debug("A", "turn.py:audio_turn", "audio_upload_received", {"bytes": len(raw), "user_id": str(user.id)})
    if not raw:
        return AudioTurnResponse(
            transcript="",
            reply="I did not receive any audio. Stay in Live mode and speak naturally.",
            session_id=sid,
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
        return AudioTurnResponse(
            transcript="",
            reply="I did not catch that clearly. Try one short sentence near the microphone.",
            session_id=sid,
        )

    t_reply = time.monotonic()
    reply, crisis, tool_actions, sid, draft = await _reply_for_text(
        db, user, transcript.strip(), sid, channel="audio"
    )
    reply_ms = int((time.monotonic() - t_reply) * 1000)

    draft_confirmed = bool(
        tool_actions and any(a.startswith("Confirmed plan:") for a in tool_actions)
    )
    t_tts = time.monotonic()
    audio_bytes, audio_mime = await synthesize(reply)
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
        session_id=sid,
        audio_base64=base64.b64encode(audio_bytes).decode("ascii") if audio_bytes else None,
        audio_mime=audio_mime if audio_bytes else None,
    )


@router.post("/turn/tts", response_model=TtsResponse)
async def tts_turn(body: TtsRequest, user: User = Depends(get_current_user)):
    text = (body.text or "").strip()
    if not text:
        return TtsResponse(text="")
    audio_bytes, audio_mime = await synthesize(text)
    return TtsResponse(
        text=text,
        audio_base64=base64.b64encode(audio_bytes).decode("ascii") if audio_bytes else None,
        audio_mime=audio_mime if audio_bytes else None,
    )
