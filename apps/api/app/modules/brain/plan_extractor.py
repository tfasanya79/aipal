import logging
import re
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from app.modules.brain.llm_provider import llm_chat_json
from app.shared.timezone_util import user_local_today

log = logging.getLogger("aipal.plan_extractor")

_PLAN_SIGNAL = re.compile(
    r"\b(remind|add|plan|schedule|meeting|tomorrow|swim|bed|gym|at\s+\d|\d{1,2}\s*(?:am|pm)|\d{1,2}:\d{2})\b",
    re.IGNORECASE,
)
_COMPLETE_SIGNAL = re.compile(
    r"\b(finished|completed|done with|already did|mark .+ done)\b",
    re.IGNORECASE,
)
_EVENT_LIKE = re.compile(
    r"\b(meeting|call|appointment|interview|standup|sync|event|lunch|dinner)\b",
    re.IGNORECASE,
)


def needs_plan_extraction(text: str) -> bool:
    """Skip the extra LLM call unless the utterance may involve planning or completion."""
    t = text.strip()
    if not t:
        return False
    return bool(_PLAN_SIGNAL.search(t) or _COMPLETE_SIGNAL.search(t))


EXTRACT_PROMPT = """You extract daily plans from user messages. Return ONLY valid JSON:
{
  "intent": "plan_day|check_in|complete_task|other",
  "proposed_tasks": [
    {
      "title": "1-4 word action label",
      "notes": "optional longer context from user",
      "due_at": "ISO8601 datetime with timezone offset or null",
      "estimated_minutes": null,
      "priority": 1,
      "category": "work|health|home|personal|null"
    }
  ],
  "clarifying_question": null or "one short question if times or tasks are unclear"
}
Rules:
- title MUST be 1-4 words, concise (e.g. "Bedtime", "Team meeting", "Swim") — never full sentences.
- Put the user's original phrasing in notes when helpful.
- If user mentions specific times (e.g. 2:30pm, 4pm, 16:00), set due_at for today using their timezone offset — not Z/UTC unless user explicitly means UTC.
- For meetings/calls/appointments with a time but no stated duration, set estimated_minutes to null and ask one clarifying_question about duration.
- For simple reminders without a fixed end time, estimated_minutes may be 30.
- priority: 0=low, 1=medium, 2=high
- Do not invent tasks not mentioned unless user asks to plan their day generally.
- If only checking in with no tasks, proposed_tasks can be empty.
"""


def _localize_due_at(due_dt: datetime, tz: ZoneInfo) -> datetime:
    """Treat naive or UTC/Z timestamps as wall-clock in the user's timezone."""
    if due_dt.tzinfo is None:
        return due_dt.replace(tzinfo=tz)
    if due_dt.utcoffset() == timedelta(0):
        return due_dt.replace(tzinfo=None).replace(tzinfo=tz)
    return due_dt


def _is_timed_event(title: str, notes: str | None, due_dt: datetime | None) -> bool:
    if not due_dt:
        return False
    blob = f"{title} {notes or ''}"
    return bool(_EVENT_LIKE.search(blob))


def _parse_estimated_minutes(raw_val, *, is_event: bool) -> int | None:
    if raw_val is None or raw_val == "":
        return None if is_event else 30
    try:
        return int(raw_val)
    except (TypeError, ValueError):
        return None if is_event else 30


def should_defer_draft(extracted: dict) -> bool:
    """Hold plan draft until timed events have a duration (companion asks in chat first)."""
    if not extracted.get("clarifying_question"):
        return False
    for t in extracted.get("proposed_tasks") or []:
        if t.get("due_at") and t.get("estimated_minutes") is None:
            return True
    return False


def _compact_title(title: str, notes: str | None = None) -> tuple[str, str | None]:
    cleaned = " ".join(title.strip().split())
    words = cleaned.split()
    if len(words) <= 4:
        compact = cleaned.title() if cleaned.islower() or cleaned.isupper() else cleaned
        return compact[:80], notes
    short = " ".join(words[:4])
    short = short.title() if short.islower() else short
    overflow = " ".join(words[4:])
    merged_notes = f"{overflow}. {notes}".strip(". ") if notes else overflow
    return short[:80], merged_notes[:500] if merged_notes else None


def _heuristic_title(phrase: str) -> str:
    p = phrase.lower().strip()
    if "bed" in p or "sleep" in p:
        return "Bedtime"
    if "swim" in p:
        return "Swimming"
    if "meet" in p:
        return "Meeting"
    if "gym" in p or "workout" in p:
        return "Workout"
    if "eat" in p or "lunch" in p or "dinner" in p:
        return "Meal"
    words = p.split()
    if len(words) <= 4:
        return phrase.strip().title()
    return " ".join(words[-4:]).title()


async def extract_plan(
    user_message: str,
    *,
    wake_name: str,
    timezone: str,
    history_summary: str = "",
    today: date | None = None,
) -> dict:
    today = today or user_local_today(timezone)
    try:
        tz = ZoneInfo(timezone or "UTC")
    except Exception:
        tz = ZoneInfo("UTC")

    ctx = f"Today: {today.isoformat()}. Timezone: {timezone}. User wake name: {wake_name}."
    if history_summary:
        ctx += f"\nRecent conversation:\n{history_summary}"

    messages = [
        {"role": "user", "content": f"{EXTRACT_PROMPT}\n\n{ctx}\n\nUser message: {user_message}"},
    ]
    try:
        raw = await llm_chat_json(messages)
        return _normalize_plan(raw, today, tz, user_message)
    except Exception as e:
        log.warning("plan extract failed: %s", e)
        return _regex_fallback(user_message, today, tz)


def _normalize_plan(raw: dict, today: date, tz: ZoneInfo, user_message: str = "") -> dict:
    intent = raw.get("intent") or "other"
    tasks = raw.get("proposed_tasks") or []
    if not isinstance(tasks, list):
        tasks = []
    normalized = []
    for t in tasks[:8]:
        if not isinstance(t, dict) or not t.get("title"):
            continue
        due = t.get("due_at")
        if due and isinstance(due, str):
            try:
                due_dt = datetime.fromisoformat(due.replace("Z", "+00:00"))
                due_dt = _localize_due_at(due_dt, tz)
            except ValueError:
                due_dt = None
        else:
            due_dt = None
        notes = t.get("notes")
        title, notes = _compact_title(str(t["title"]), str(notes) if notes else None)
        if not notes and user_message and len(str(t["title"])) > len(title) + 5:
            notes = str(t["title"])[:500]
        is_event = _is_timed_event(title, notes, due_dt)
        est = _parse_estimated_minutes(t.get("estimated_minutes"), is_event=is_event)
        normalized.append(
            {
                "title": title,
                "notes": notes,
                "due_at": due_dt.isoformat() if due_dt else None,
                "estimated_minutes": est,
                "priority": min(3, max(0, int(t.get("priority", 1)))),
                "category": t.get("category"),
            }
        )

    clarifying = raw.get("clarifying_question")
    if not clarifying:
        for item in normalized:
            due_str = item.get("due_at")
            due_parsed = None
            if due_str:
                try:
                    due_parsed = datetime.fromisoformat(due_str.replace("Z", "+00:00"))
                except ValueError:
                    pass
            if item["due_at"] and _is_timed_event(item["title"], item.get("notes"), due_parsed) and item["estimated_minutes"] is None:
                clarifying = f"How long is your {item['title'].lower()}?"
                break

    return {
        "intent": intent,
        "proposed_tasks": normalized,
        "clarifying_question": clarifying,
    }


def _regex_fallback(user_message: str, today: date, tz: ZoneInfo) -> dict:
    """Lightweight fallback when LLM JSON fails."""
    tasks = []
    patterns = [
        re.compile(
            r"(?:remind(?:\s+me)?\s+(?:to\s+)?|add\s+(?:a\s+)?)([\w\s]{2,50}?)\s+(?:at|by)\s+"
            r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)?",
            re.IGNORECASE,
        ),
        re.compile(
            r"(\w[\w\s]{2,40}?)\s+(?:at|by)\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?",
            re.IGNORECASE,
        ),
    ]
    seen = set()
    for pattern in patterns:
        for m in pattern.finditer(user_message):
            phrase = m.group(1).strip()
            hour = int(m.group(2))
            minute = int(m.group(3) or 0)
            ampm = (m.group(4) or "").lower()
            if ampm == "pm" and hour < 12:
                hour += 12
            if ampm == "am" and hour == 12:
                hour = 0
            due_dt = datetime(today.year, today.month, today.day, hour, minute, tzinfo=tz)
            title = _heuristic_title(phrase)
            key = (title.lower(), due_dt.isoformat())
            if key in seen:
                continue
            seen.add(key)
            is_event = _is_timed_event(title, phrase, due_dt)
            tasks.append(
                {
                    "title": title,
                    "notes": phrase[:500],
                    "due_at": due_dt.isoformat(),
                    "estimated_minutes": None if is_event else 60,
                    "priority": 1,
                    "category": "personal",
                }
            )
    clarifying = None
    if tasks and any(t["estimated_minutes"] is None for t in tasks):
        clarifying = f"How long is your {tasks[0]['title'].lower()}?"
    return {
        "intent": "plan_day" if tasks else "other",
        "proposed_tasks": tasks,
        "clarifying_question": clarifying,
    }
