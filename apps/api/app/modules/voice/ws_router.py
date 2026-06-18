import json
import logging
import time
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from jose import JWTError, jwt
from sqlalchemy import select

from app.shared.config import get_settings
from app.shared.db import async_session
from app.shared.models import LiveSession, User
from app.modules.brain.safety import crisis_reply, is_crisis_likely

router = APIRouter()
log = logging.getLogger("aipal.ws")
settings = get_settings()
DEBUG_LOG = "/home/dev/.cursor/debug-60ce92.log"


def _agent_debug(hypothesis_id: str, location: str, message: str, data: dict, run_id: str = "pre-fix") -> None:
    # #region agent log
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
    # #endregion


async def _user_from_token(token: str) -> User | None:
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
        user_id = uuid.UUID(payload["sub"])
    except (JWTError, ValueError):
        return None
    async with async_session() as db:
        result = await db.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()


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

    await websocket.send_json({"type": "session_started", "session_id": str(session_id), "state": "live"})
    _agent_debug("B", "ws_session.py:live_session", "ws_session_started", {"user_id": str(user.id)})

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_json({"type": "error", "message": "Invalid JSON"})
                continue

            msg_type = msg.get("type")
            _agent_debug("A", "ws_session.py:live_session", "ws_message", {"type": msg_type, "user_id": str(user.id)})
            if msg_type == "ping":
                await websocket.send_json({"type": "pong"})
                continue
            if msg_type == "end":
                break
            if msg_type == "text_turn":
                text = (msg.get("text") or "").strip()
                if not text:
                    continue
                await websocket.send_json({"type": "state", "state": "thinking"})
                if is_crisis_likely(text):
                    await websocket.send_json(
                        {"type": "reply", "text": crisis_reply(), "crisis": True, "state": "speaking"}
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
                await websocket.send_json({"type": "state", "state": "listening"})
            elif msg_type == "audio_chunk":
                await websocket.send_json(
                    {"type": "transcript_partial", "text": "", "note": "STT streaming planned; use text_turn for v2.0"}
                )
    except WebSocketDisconnect:
        log.info("WebSocket disconnected user=%s", user.id)
    finally:
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
