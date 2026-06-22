import re

from app.modules.brain import plan_extractor

_CONFIRM_PATTERNS = (
    r"^(yes|yeah|yep|sure|ok|okay|please do|sounds good|go ahead|add it|add them|"
    r"add to today|put it on today|confirm|do it|that works)\b",
    r"\b(yes add|add that|add those|add to today)\b",
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


_BOOKING_SIGNAL = re.compile(
    r"\b(book|schedule|set up|add|appointment|meeting)\b",
    re.IGNORECASE,
)


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
