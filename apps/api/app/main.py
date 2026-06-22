import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.modules.auth import profile_router, router as auth_router
from app.modules.integrations import calendar_router, router as integrations_router
from app.modules.today import daily_router, tasks_router
from app.modules.voice import router as turn_router, sessions_router, ws_router
from app.modules.voice import session_events as sess_svc
from app.modules.voice.stt import prewarm_model
from app.shared.config import get_settings
from app.shared.db import async_session, init_db
from app.shared.schemas import HealthResponse

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
log = logging.getLogger("aipal")
settings = get_settings()

if not logging.getLogger().handlers:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


async def _prewarm_whisper() -> None:
    """Load faster-whisper at startup so the first half-duplex turn is not blocked."""
    try:
        await asyncio.to_thread(prewarm_model)
    except Exception:
        log.exception("Whisper STT pre-warm failed; first turn may be slow")


async def _prewarm_whisper() -> None:
    """Load faster-whisper at startup so first Live turn is not blocked on HF download."""
    if not settings.live_voice_v2:
        return
    if (settings.stt_provider or "").lower() != "whisper_stream":
        return
    try:
        from .stt import _get_model

        await asyncio.to_thread(_get_model)
        log.info(
            "Whisper STT pre-warmed (model=%s device=%s)",
            settings.whisper_model,
            settings.whisper_device,
        )
    except Exception:
        log.exception("Whisper STT pre-warm failed; first turn may be slow")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    async with async_session() as db:
        deleted = await sess_svc.cleanup_old_events(db)
        if deleted:
            log.info("Cleaned up %d old session events", deleted)
    await _prewarm_whisper()
    log.info("AIpal API v2 started")
    yield


app = FastAPI(title="AIpal API v2", version="2.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins.split(",") if settings.cors_origins != "*" else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

prefix = "/api/v2"
app.include_router(auth_router, prefix=prefix)
app.include_router(profile_router, prefix=prefix)
app.include_router(tasks_router, prefix=prefix)
app.include_router(daily_router, prefix=prefix)
app.include_router(turn_router, prefix=prefix)
app.include_router(sessions_router, prefix=prefix)
app.include_router(calendar_router, prefix=prefix)
app.include_router(integrations_router, prefix=prefix)
app.include_router(ws_router, prefix=prefix)


@app.get("/api/v2/health", response_model=HealthResponse)
async def health():
    return HealthResponse(ok=True, mem0_enabled=settings.mem0_enabled, llm_provider=settings.llm_provider)


@app.get("/health")
async def health_root():
    return {"ok": True, "service": "aipal-v2"}
