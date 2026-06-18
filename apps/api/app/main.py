import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .db import async_session, init_db
from .routers import auth, calendar, daily, integrations, profile, sessions, tasks, turn, ws_session
from .schemas import HealthResponse
from .services import session_events as sess_svc

log = logging.getLogger("aipal")
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    async with async_session() as db:
        deleted = await sess_svc.cleanup_old_events(db)
        if deleted:
            log.info("Cleaned up %d old session events", deleted)
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
app.include_router(sessions.router, prefix=prefix)
app.include_router(calendar.router, prefix=prefix)
app.include_router(integrations.router, prefix=prefix)
app.include_router(ws_session.router, prefix=prefix)


@app.get("/api/v2/health", response_model=HealthResponse)
async def health():
    return HealthResponse(ok=True, mem0_enabled=settings.mem0_enabled, llm_provider=settings.llm_provider)


@app.get("/health")
async def health_root():
    return {"ok": True, "service": "aipal-v2"}
