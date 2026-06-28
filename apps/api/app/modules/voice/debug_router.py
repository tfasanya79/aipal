"""Client-side debug events from mobile (wake, session) → NDJSON log."""

from pydantic import BaseModel, Field

from app.modules.auth.service import get_current_user
from app.shared.agent_debug import agent_debug
from app.shared.models import User
from fastapi import APIRouter, Depends

router = APIRouter(tags=["debug"])


class ClientDebugEvent(BaseModel):
    hypothesis_id: str = Field(..., max_length=8)
    location: str = Field(..., max_length=120)
    message: str = Field(..., max_length=200)
    data: dict = Field(default_factory=dict)
    run_id: str = Field(default="pre-fix", max_length=32)


@router.post("/debug/client-log")
async def client_debug_log(body: ClientDebugEvent, user: User = Depends(get_current_user)):
    agent_debug(
        body.hypothesis_id,
        body.location,
        body.message,
        {**body.data, "user_id": str(user.id)},
        run_id=body.run_id,
    )
    return {"ok": True}
