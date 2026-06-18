import logging
import re
from datetime import date, datetime
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
      "due_at": "ISO8601 datetime with timezone or null",
      "estimated_minutes": 30,
      "priority": 1,
      "category": "work|health|home|personal|null"
    }
  ],
  "clarifying_question": null or "one short question if times or tasks are unclear"
}
Rules:
- title MUST be 1-4 words, concise (e.g. "Bedtime", "Team meeting", "Swim") — never full sentences.
- Put the user's original phrasing in notes when helpful.
- If user mentions specific times (e.g. 4pm, 8pm, 16:00), set due_at for today in their timezone.
- priority: 0=low, 1=medium, 2=high
- Do not invent tasks not mentioned unless user asks to plan their day generally.
- If only checking in with no tasks, proposed_tasks can be empty.
"""


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
                if due_dt.tzinfo is None:
                    due_dt = due_dt.replace(tzinfo=tz)
            except ValueError:
                due_dt = None
        else:
            due_dt = None
        notes = t.get("notes")
        title, notes = _compact_title(str(t["title"]), str(notes) if notes else None)
        if not notes and user_message and len(str(t["title"])) > len(title) + 5:
            notes = str(t["title"])[:500]
        normalized.append(
            {
                "title": title,
                "notes": notes,
                "due_at": due_dt.isoformat() if due_dt else None,
                "estimated_minutes": int(t.get("estimated_minutes") or 30),
                "priority": min(3, max(0, int(t.get("priority", 1)))),
                "category": t.get("category"),
            }
        )
    return {
        "intent": intent,
        "proposed_tasks": normalized,
        "clarifying_question": raw.get("clarifying_question"),
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
            tasks.append(
                {
                    "title": title,
                    "notes": phrase[:500],
                    "due_at": due_dt.isoformat(),
                    "estimated_minutes": 60,
                    "priority": 1,
                    "category": "personal",
                }
            )
    return {
        "intent": "plan_day" if tasks else "other",
        "proposed_tasks": tasks,
        "clarifying_question": None,
    }
