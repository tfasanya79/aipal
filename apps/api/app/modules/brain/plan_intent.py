import re

from app.modules.brain import plan_extractor

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


def is_confirm_intent(text: str) -> bool:
    """True when user is approving a pending plan draft."""
    t = text.lower().strip()
    if not t:
        return False
    return any(re.search(p, t) for p in _CONFIRM_PATTERNS)


def is_discard_intent(text: str) -> bool:
    t = text.lower().strip()
    return bool(
        re.search(
            r"^(no|nope|not now|skip|cancel|don't add|do not add|never mind|nevermind)\b",
            t,
        )
    )


def assistant_offered_to_add(history: list[dict[str, str]]) -> bool:
    """True when a recent assistant turn offered to add something to Today."""
    for h in reversed(history):
        if h.get("role") != "assistant":
            continue
        lower = h.get("content", "").lower()
        if any(re.search(p, lower) for p in _OFFER_PATTERNS):
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


_BOOKING_SIGNAL = re.compile(
    r"\b(book|schedule|set up|add|appointment|meeting)\b",
    re.IGNORECASE,
)

_SUCCESS_CLAIM = re.compile(
    r"\b(added|scheduled|put .+ on today|all set|done[,\s].*today|i've added|i have added)\b",
    re.IGNORECASE,
)


def reply_claims_success(reply: str) -> bool:
    return bool(_SUCCESS_CLAIM.search(reply or ""))


def is_complete_booking_request(text: str, extracted: dict) -> bool:
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
    for t in tasks:
        if not t.get("due_at") or t.get("estimated_minutes") is None:
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
