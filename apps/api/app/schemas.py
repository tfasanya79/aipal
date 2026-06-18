from datetime import datetime, time
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


class RegisterRequest(BaseModel):
    email: EmailStr


class RegisterResponse(BaseModel):
    ok: bool = True
    message: str = "Magic link sent"
    dev_token: str | None = None


class VerifyRequest(BaseModel):
    token: str


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: UUID


class ProfileResponse(BaseModel):
    user_id: UUID
    email: str
    display_name: str | None = None
    wake_name: str | None = None
    timezone: str = "UTC"
    about_me: str | None = None
    morning_brief_at: str | None = None
    evening_recap_at: str | None = None
    checkin_enabled: bool = True


class ProfileUpdate(BaseModel):
    display_name: str | None = None
    wake_name: str | None = None
    timezone: str | None = None
    about_me: str | None = None
    morning_brief_at: str | None = None
    evening_recap_at: str | None = None
    checkin_enabled: bool | None = None


class TaskCreate(BaseModel):
    title: str
    notes: str | None = None
    due_at: datetime | None = None
    priority: int = Field(default=1, ge=0, le=3)
    source: str = "text"
    parent_task_id: int | None = None
    estimated_minutes: int | None = None
    sort_order: int = 0
    category: str | None = None


class TaskUpdate(BaseModel):
    title: str | None = None
    status: str | None = None
    due_at: datetime | None = None
    notes: str | None = None
    estimated_minutes: int | None = None
    sort_order: int | None = None
    category: str | None = None


class TaskResponse(BaseModel):
    id: int
    title: str
    notes: str | None
    due_at: datetime | None
    priority: int
    status: str
    source: str
    parent_task_id: int | None = None
    estimated_minutes: int | None = None
    sort_order: int = 0
    category: str | None = None
    created_at: datetime
    completed_at: datetime | None
    subtasks: list["TaskResponse"] = Field(default_factory=list)


class TaskReorderRequest(BaseModel):
    ordered_ids: list[int]


class TaskSummary(BaseModel):
    date: str
    total: int
    done: int
    open: int
    deferred: int
    streak_days: int = 0


class TodaySections(BaseModel):
    now: list[TaskResponse] = Field(default_factory=list)
    upcoming: list[TaskResponse] = Field(default_factory=list)
    completed: list[TaskResponse] = Field(default_factory=list)


class TodayViewResponse(BaseModel):
    summary: TaskSummary
    up_next: TaskResponse | None = None
    sections: TodaySections


class TaskBulkCreate(BaseModel):
    tasks: list[TaskCreate]


class DailyPayload(BaseModel):
    greeting: str
    prompt: str
    summary: TaskSummary | None = None


class TextTurnRequest(BaseModel):
    text: str
    session_id: str | None = None


class ProposedTask(BaseModel):
    title: str
    notes: str | None = None
    due_at: str | None = None
    estimated_minutes: int | None = 30
    priority: int = 1
    category: str | None = None


class PlanDraftResponse(BaseModel):
    intent: str = "other"
    proposed_tasks: list[ProposedTask] = Field(default_factory=list)
    clarifying_question: str | None = None


class SuggestDayRequest(BaseModel):
    template: str | None = None


class SuggestDayResponse(BaseModel):
    plan_draft: PlanDraftResponse | None = None


class TextTurnResponse(BaseModel):
    reply: str
    crisis: bool = False
    tool_actions: list[str] = Field(default_factory=list)
    session_id: str | None = None
    plan_draft: PlanDraftResponse | None = None


class AudioTurnResponse(BaseModel):
    transcript: str
    reply: str
    crisis: bool = False
    tool_actions: list[str] = Field(default_factory=list)
    session_id: str | None = None
    plan_draft: PlanDraftResponse | None = None
    draft_confirmed: bool = False
    audio_base64: str | None = None
    audio_mime: str | None = None


class TaskNudgeResponse(BaseModel):
    text: str
    task_id: int
    minutes: int


class TtsRequest(BaseModel):
    text: str


class TtsResponse(BaseModel):
    text: str
    audio_base64: str | None = None
    audio_mime: str | None = None


class GreetingResponse(BaseModel):
    text: str
    wake_word_hint: str | None = None


class HealthResponse(BaseModel):
    ok: bool
    version: str = "2.0.0"
    mem0_enabled: bool
    llm_provider: str


class SessionEventInput(BaseModel):
    event_type: str
    payload: dict = Field(default_factory=dict)
    phase_tag: str | None = None


class SessionEventsBatchRequest(BaseModel):
    session_id: str
    phase_tag: str | None = None
    events: list[SessionEventInput] = Field(default_factory=list)


class SessionEventsBatchResponse(BaseModel):
    recorded: int
    session_id: str


class RecentSessionSummary(BaseModel):
    session_id: str
    last_event_at: str | None = None
    event_count: int
    phase_tag: str | None = None


class SessionExportEvent(BaseModel):
    event_type: str
    phase_tag: str | None = None
    payload: dict = Field(default_factory=dict)
    created_at: str


class SessionExportTurn(BaseModel):
    role: str
    content: str
    created_at: str


class SessionExportResponse(BaseModel):
    session_id: str
    phase_tag: str | None = None
    events: list[SessionExportEvent] = Field(default_factory=list)
    turns: list[SessionExportTurn] = Field(default_factory=list)


def time_to_str(t: time | None) -> str | None:
    return t.strftime("%H:%M") if t else None


def str_to_time(s: str | None) -> time | None:
    if not s:
        return None
    parts = s.split(":")
    return time(int(parts[0]), int(parts[1]) if len(parts) > 1 else 0)
