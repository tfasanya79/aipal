import re
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from app.modules.brain import plan_extractor
from app.modules.brain import task_resolver
from app.shared.schemas import TodayViewResponse

_CONFIRM_PATTERNS = (
    r"^(yes|yeah|yep|sure|ok|okay|please do|sounds good|go ahead|add it|add them|"
    r"add to today|put it on today|confirm|do it|that works)\b",
    r"\b(yes add|add that|add those|add to today)\b",
)

_OFFER_PATTERNS = (
    r"\bi can add\b",
    r"\bwant me to add\b",
    r"\bshall i add\b",
    r"\bsay yes\b",
    r"\badd .+ (to )?today\b",
    r"\badd a .+ appointment\b",
    r"\bjust say yes\b",
)

_UPDATE_OFFER_PATTERNS = (
    r"\bi can move\b",
    r"\bwant me to (move|change|update|reschedule)\b",
    r"\bshall i (move|change|update|reschedule)\b",
    r"\bsay yes and i'll update\b",
    r"\bupdate it to\b",
    r"\bchange it to\b",
    r"\bmove .+ to\b",
    r"\bofficially update\b",
)

_EDIT_SIGNAL = re.compile(
    r"\b(move|reschedule|change|update|shift|push|make it|switch)\b",
    re.IGNORECASE,
)

_MUTATION_CLAIM = re.compile(
    r"\b("
    r"added|scheduled|put .+ on today|all set|done[,\s].*today|i've added|i have added|"
    r"updated|moved|rescheduled|changed|set for|now at|now set|officially update|"
    r"i've moved|i have moved|marked done|completed|removed from today"
    r")\b",
    re.IGNORECASE,
)

_BOOKING_SIGNAL = re.compile(
    r"\b(book|schedule|set up|add|appointment|meeting)\b",
    re.IGNORECASE,
)

_SUCCESS_CLAIM = _MUTATION_CLAIM


def is_confirm_intent(text: str) -> bool:
    """True when user is approving a pending plan draft."""
    t = text.lower().strip()
    if not t:
        return False
    words = t.split()
    first = re.sub(r"[^\w]", "", words[0]) if words else ""
    # Noisy STT: "Yes, I did so much. I do." — not a draft confirm.
    if re.search(r"\b(did so much|i do\.?$|did subscribe|my evening|thank you)\b", t) and first == "yes":
        return False
    if first in ("yes", "yeah", "yep", "sure", "ok", "okay") and len(words) > 6:
        return False
    if first in ("yes", "yeah", "yep") and len(words) > 3:
        return bool(
            re.search(
                r"\b(add it|add that|add to today|go ahead|please do|sounds good|confirm|do it)\b",
                t,
            )
        )
    return any(re.search(p, t) for p in _CONFIRM_PATTERNS)


def is_discard_intent(text: str) -> bool:
    t = text.lower().strip()
    return bool(
        re.search(
            r"^(no|nope|not now|skip|cancel|don't add|do not add|never mind|nevermind)\b",
            t,
        )
    )


_NEGATED_EDIT = re.compile(
    r"\b(didn't|did not|don't|do not|not ask you to|without)\s+(\w+\s+){0,4}(change|move|update|reschedule)\b",
    re.IGNORECASE,
)


def is_edit_request(text: str) -> bool:
    t = text or ""
    if not t.strip():
        return False
    if _NEGATED_EDIT.search(t):
        return False
    lower = t.lower()
    # "book a breakfast" is create, not edit — even if STT also mentions "change" elsewhere.
    if _BOOKING_SIGNAL.search(lower) and re.search(r"\b(book|schedule)\b", lower):
        if not re.match(r"^\s*(move|reschedule|change|update|shift|push|switch)\b", lower):
            return False
    return bool(_EDIT_SIGNAL.search(t))


def assistant_offered_to_add(history: list[dict[str, str]]) -> bool:
    """True when a recent assistant turn offered to add something to Today."""
    for h in reversed(history):
        if h.get("role") != "assistant":
            continue
        lower = h.get("content", "").lower()
        if any(re.search(p, lower) for p in _OFFER_PATTERNS):
            return True
    return False


def assistant_offered_to_update(history: list[dict[str, str]]) -> bool:
    """True when a recent assistant turn offered to update/reschedule a task."""
    for h in reversed(history):
        if h.get("role") != "assistant":
            continue
        lower = h.get("content", "").lower()
        if any(re.search(p, lower) for p in _UPDATE_OFFER_PATTERNS):
            return True
    return False


def recovery_context_from_history(history: list[dict[str, str]]) -> str:
    """Build text for plan extraction from recent offer + user request."""
    parts: list[str] = []
    for h in history[-6:]:
        role = h.get("role", "user")
        content = (h.get("content") or "").strip()
        if content:
            parts.append(f"{role}: {content}")
    return "\n".join(parts)


def _is_vague_edit(user_text: str, edit: dict) -> bool:
    """True when user gave a pronoun-only edit without explicit am/pm or task title."""
    if re.search(r"\d{1,2}\s*(?::\d{2})?\s*(am|pm)", user_text, re.IGNORECASE):
        return False
    title = (edit.get("match_title") or "").lower()
    if title and title in user_text.lower():
        return False
    return True


def is_clear_edit(
    extracted: dict,
    resolved_edits: list[dict],
    user_text: str,
    today_snap: TodayViewResponse,
) -> bool:
    """Instant apply when one task, resolved match, new time, and not vague."""
    if len(resolved_edits) != 1:
        return False
    edit = resolved_edits[0]
    if not edit.get("new_due_at"):
        return False
    if not is_edit_request(user_text):
        return False
    if _is_vague_edit(user_text, edit):
        return False
    resolved = task_resolver.resolve_task(
        match_title=edit.get("match_title"),
        task_id=edit.get("task_id"),
        user_text=user_text,
        today_snap=today_snap,
    )
    return bool(resolved and resolved.confidence >= 0.5)


def reply_claims_mutation(reply: str) -> bool:
    return bool(_MUTATION_CLAIM.search(reply or ""))


def reply_claims_success(reply: str) -> bool:
    return reply_claims_mutation(reply)


def has_mutation_tool_action(tool_actions: list[str]) -> bool:
    prefixes = ("Confirmed plan:", "Updated task:", "Completed:", "Deleted task:")
    return any(a.startswith(p) for a in tool_actions for p in prefixes)


def _due_time_plausible(user_message: str, due_at: str | None, tz: ZoneInfo) -> bool:
    """Reject auto-confirm when STT/LLM picked an absurd early hour vs user intent."""
    if not due_at:
        return False
    try:
        dt = datetime.fromisoformat(str(due_at).replace("Z", "+00:00"))
        local = dt.astimezone(tz) if dt.tzinfo else dt.replace(tzinfo=tz)
        hour = local.hour
        msg = (user_message or "").lower()
        if hour < 5 and re.search(r"\b([89]|eight|nine|morning|8\s*[:.]?\s*30|8\.30)\b", msg):
            return False
        if hour < 6 and re.search(r"\b30\s*am\b", msg) and not re.search(r"\b8\s*[:.]?\s*30\b", msg):
            return False
        return True
    except ValueError:
        return True


def is_complete_booking_request(
    text: str,
    extracted: dict,
    *,
    local_day: date | None = None,
    timezone: str = "UTC",
) -> bool:
    """True when user explicitly books/schedules with time and duration for all proposed tasks."""
    if plan_extractor.should_defer_draft(extracted):
        return False
    if extracted.get("clarifying_question"):
        return False
    tasks = extracted.get("proposed_tasks") or []
    if not tasks:
        return False
    if not _BOOKING_SIGNAL.search(text.strip()):
        return False
    try:
        tz = ZoneInfo(timezone or "UTC")
    except Exception:
        tz = ZoneInfo("UTC")
    day = local_day or date.today()
    for t in tasks:
        if not t.get("due_at") or t.get("estimated_minutes") is None:
            return False
        if not plan_extractor.due_matches_relative_day(text, t.get("due_at"), day, tz):
            return False
        if not _due_time_plausible(text, t.get("due_at"), tz):
            return False
    return True


def ensure_recovery_duration(extracted: dict, *, default_minutes: int = 60) -> dict:
    """Fill missing duration on recovered tasks so confirm never blocks."""
    out = dict(extracted)
    tasks = []
    for t in out.get("proposed_tasks") or []:
        if not isinstance(t, dict):
            continue
        item = dict(t)
        if item.get("due_at") and item.get("estimated_minutes") is None:
            item["estimated_minutes"] = default_minutes
        tasks.append(item)
    out["proposed_tasks"] = tasks
    out["clarifying_question"] = None
    return out
