import asyncio
import base64
import json
import logging
import time
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from jose import JWTError, jwt
from sqlalchemy import select

from ..config import get_settings
from ..db import async_session
from ..models import LiveSession, User
from ..safety import crisis_reply, is_crisis_likely
from ..services.stt_provider import get_streaming_stt
from ..services.voice_turn import run_voice_turn_stream
from ..tts import synthesize_stream
from ..voice_pipeline import TurnCancellationRegistry, TurnRateLimiter, split_sentences

router = APIRouter()
log = logging.getLogger("aipal.ws")
settings = get_settings()

_rate_limiter = TurnRateLimiter(settings.live_turns_per_minute)


async def _user_from_token(token: str) -> User | None:
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
        user_id = uuid.UUID(payload["sub"])
    except (JWTError, ValueError):
        return None
    async with async_session() as db:
        result = await db.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()


async def _send_state(websocket: WebSocket, state: str) -> None:
    await websocket.send_json({"type": "state", "state": state})


async def _run_turn_pipeline(
    websocket: WebSocket,
    user: User,
    session_id: uuid.UUID,
    turn_id: str,
    text: str,
    cancel_registry: TurnCancellationRegistry,
    *,
    stt_final_ms: int | None = None,
    stt_metrics: dict[str, int] | None = None,
) -> None:
    cancel_event = asyncio.Event()
    tts_t0: float | None = None
    reply_buffer = ""
    metrics: dict[str, int] = {}
    if stt_final_ms is not None:
        metrics["stt_final_ms"] = stt_final_ms
    if stt_metrics:
        metrics.update(stt_metrics)

    async def _pipeline() -> None:
        nonlocal reply_buffer, tts_t0, metrics
        try:
            async with async_session() as db:
                async for event in run_voice_turn_stream(
                    db, user, text, str(session_id), cancel_event=cancel_event
                ):
                    if cancel_event.is_set():
                        return
                    etype = event.get("type")
                    if etype == "reply_delta":
                        chunk = event.get("text", "")
                        if chunk:
                            await websocket.send_json(
                                {"type": "reply_delta", "turn_id": turn_id, "text": chunk}
                            )
                            reply_buffer += chunk
                            sentences, reply_buffer = split_sentences(reply_buffer)
                            for sentence in sentences:
                                if cancel_event.is_set():
                                    return
                                async for audio, mime in synthesize_stream(sentence):
                                    if cancel_event.is_set():
                                        return
                                    if audio:
                                        if tts_t0 is None:
                                            tts_t0 = time.monotonic()
                                        await websocket.send_json(
                                            {
                                                "type": "audio_chunk",
                                                "turn_id": turn_id,
                                                "data": base64.b64encode(audio).decode("ascii"),
                                                "mime": mime,
                                            }
                                        )
                    elif etype == "turn_meta":
                        metrics.update(event.get("metrics") or {})
                        if reply_buffer.strip() and not cancel_event.is_set():
                            async for audio, mime in synthesize_stream(reply_buffer.strip()):
                                if cancel_event.is_set():
                                    return
                                if audio:
                                    if tts_t0 is None:
                                        tts_t0 = time.monotonic()
                                    await websocket.send_json(
                                        {
                                            "type": "audio_chunk",
                                            "turn_id": turn_id,
                                            "data": base64.b64encode(audio).decode("ascii"),
                                            "mime": mime,
                                        }
                                    )
                        if tts_t0 is not None:
                            metrics["tts_first_chunk_ms"] = int((time.monotonic() - tts_t0) * 1000)
                        payload = {
                            "type": "turn_complete",
                            "turn_id": turn_id,
                            "reply": event.get("reply", ""),
                            "tool_actions": event.get("tool_actions", []),
                            "draft_confirmed": event.get("draft_confirmed", False),
                            "metrics": metrics,
                        }
                        draft = event.get("plan_draft")
                        if draft:
                            payload["plan_draft"] = (
                                draft.model_dump() if hasattr(draft, "model_dump") else draft
                            )
                        log.info(
                            "live_turn_complete user=%s turn=%s metrics=%s",
                            user.id,
                            turn_id,
                            metrics,
                        )
                        await websocket.send_json(payload)
                        await _send_state(websocket, "listening")
        except asyncio.CancelledError:
            await websocket.send_json({"type": "turn_cancelled", "turn_id": turn_id})
            await _send_state(websocket, "listening")
            raise
        except Exception:
            log.exception("live_turn_pipeline_failed turn=%s", turn_id)
            raise

    task = asyncio.create_task(_pipeline())
    cancel_registry.register(turn_id, task)
    try:
        await task
    except asyncio.CancelledError:
        cancel_event.set()
    finally:
        cancel_registry.clear(turn_id)


@router.websocket("/ws/session")
async def live_session(websocket: WebSocket):
    await websocket.accept()
    token = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=4401)
        return
    user = await _user_from_token(token)
    if not user:
        await websocket.close(code=4401)
        return

    session_id = uuid.uuid4()
    async with async_session() as db:
        live = LiveSession(id=session_id, user_id=user.id, state="active")
        db.add(live)
        await db.commit()

    await websocket.send_json(
        {"type": "session_started", "session_id": str(session_id), "state": "live"}
    )
    await _send_state(websocket, "listening")

    stt = get_streaming_stt(settings) if settings.live_voice_v2 else None
    cancel_registry = TurnCancellationRegistry()

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_json({"type": "error", "message": "Invalid JSON"})
                continue

            msg_type = msg.get("type")

            if msg_type == "ping":
                await websocket.send_json({"type": "pong"})
                continue
            if msg_type == "end":
                break

            if msg_type == "interrupt":
                turn_id = msg.get("turn_id") or ""
                if cancel_registry.cancel(turn_id):
                    await websocket.send_json({"type": "turn_cancelled", "turn_id": turn_id})
                    await _send_state(websocket, "listening")
                continue

            if not settings.live_voice_v2:
                if msg_type == "text_turn":
                    text = (msg.get("text") or "").strip()
                    if not text:
                        continue
                    await _send_state(websocket, "thinking")
                    if is_crisis_likely(text):
                        await websocket.send_json(
                            {
                                "type": "reply",
                                "text": crisis_reply(),
                                "crisis": True,
                                "state": "speaking",
                            }
                        )
                        continue
                    from .turn import _reply_for_text

                    async with async_session() as db:
                        reply, crisis, tool_actions, _, draft = await _reply_for_text(
                            db, user, text, str(session_id)
                        )
                    payload = {
                        "type": "reply",
                        "text": reply,
                        "tool_actions": tool_actions,
                        "state": "speaking",
                    }
                    if draft:
                        payload["plan_draft"] = draft.model_dump()
                    await websocket.send_json(payload)
                    await _send_state(websocket, "listening")
                elif msg_type == "audio_chunk":
                    await websocket.send_json(
                        {
                            "type": "transcript_partial",
                            "text": "",
                            "note": "Enable LIVE_VOICE_V2 for streaming STT",
                        }
                    )
                continue

            if msg_type == "audio_frame":
                if stt is None:
                    continue
                data_b64 = msg.get("data") or ""
                try:
                    pcm = base64.b64decode(data_b64)
                except Exception:
                    continue
                partial = await stt.feed_audio(pcm)
                turn_id = msg.get("turn_id") or ""
                if partial:
                    await websocket.send_json(
                        {"type": "transcript_partial", "turn_id": turn_id, "text": partial}
                    )
                continue

            if msg_type == "speech_start":
                if stt:
                    await stt.on_speech_start()
                continue

            turn_id = msg.get("turn_id") or str(uuid.uuid4())

            if msg_type == "speech_end":
                if not _rate_limiter.allow(str(user.id)):
                    await websocket.send_json(
                        {
                            "type": "error",
                            "turn_id": turn_id,
                            "message": "Rate limit exceeded; try again shortly.",
                        }
                    )
                    continue

                stt_t0 = time.monotonic()
                transcript = ""
                stt_metrics: dict[str, int] = {}
                if stt:
                    transcript = await stt.on_speech_end()
                    stt_metrics = stt.consume_metrics()
                stt_final_ms = int((time.monotonic() - stt_t0) * 1000)

                if not (transcript or "").strip():
                    await websocket.send_json(
                        {
                            "type": "transcript_final",
                            "turn_id": turn_id,
                            "text": "",
                        }
                    )
                    continue

                await websocket.send_json(
                    {"type": "transcript_final", "turn_id": turn_id, "text": transcript.strip()}
                )
                await _send_state(websocket, "thinking")
                await _send_state(websocket, "speaking")
                asyncio.create_task(
                    _run_turn_pipeline(
                        websocket,
                        user,
                        session_id,
                        turn_id,
                        transcript.strip(),
                        cancel_registry,
                        stt_final_ms=stt_final_ms,
                        stt_metrics=stt_metrics,
                    )
                )
                continue

            if msg_type == "text_turn":
                text = (msg.get("text") or "").strip()
                if not text:
                    continue
                if not _rate_limiter.allow(str(user.id)):
                    await websocket.send_json(
                        {
                            "type": "error",
                            "turn_id": turn_id,
                            "message": "Rate limit exceeded; try again shortly.",
                        }
                    )
                    continue
                await _send_state(websocket, "thinking")
                await _send_state(websocket, "speaking")
                asyncio.create_task(
                    _run_turn_pipeline(
                        websocket, user, session_id, turn_id, text, cancel_registry
                    )
                )

    except WebSocketDisconnect:
        log.info("WebSocket disconnected user=%s", user.id)
    finally:
        cancel_registry.cancel_all()
        async with async_session() as db:
            result = await db.execute(select(LiveSession).where(LiveSession.id == session_id))
            live = result.scalar_one_or_none()
            if live:
                live.state = "ended"
                live.ended_at = datetime.now(UTC)
                await db.commit()
        try:
            await websocket.send_json({"type": "session_ended", "state": "resting"})
        except Exception:
            pass
