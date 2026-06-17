import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .db import init_db
from .routers import auth, calendar, daily, integrations, profile, tasks, turn, ws_session
from .schemas import HealthResponse

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
log = logging.getLogger("aipal")
settings = get_settings()


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
app.include_router(auth.router, prefix=prefix)
app.include_router(profile.router, prefix=prefix)
app.include_router(tasks.router, prefix=prefix)
app.include_router(daily.router, prefix=prefix)
app.include_router(turn.router, prefix=prefix)
app.include_router(calendar.router, prefix=prefix)
app.include_router(integrations.router, prefix=prefix)
app.include_router(ws_session.router, prefix=prefix)


@app.get("/api/v2/health", response_model=HealthResponse)
async def health():
    return HealthResponse(ok=True, mem0_enabled=settings.mem0_enabled, llm_provider=settings.llm_provider)


@app.get("/health")
async def health_root():
    return {"ok": True, "service": "aipal-v2"}
