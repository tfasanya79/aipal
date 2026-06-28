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
_EDIT_SIGNAL = re.compile(
    r"\b(move|reschedule|change|update|shift|push|make it|switch)\b",
    re.IGNORECASE,
)


def needs_plan_extraction(text: str) -> bool:
    """Skip the extra LLM call unless the utterance may involve planning or completion."""
    t = text.strip()
    if not t:
        return False
    return bool(_PLAN_SIGNAL.search(t) or _COMPLETE_SIGNAL.search(t) or _EDIT_SIGNAL.search(t))


EXTRACT_PROMPT = """You extract daily plans and task edits from user messages. Return ONLY valid JSON:
{
  "intent": "plan_day|check_in|complete_task|edit_task|other",
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
  "edits": [
    {
      "match_title": "existing task title to change",
      "task_id": null,
      "new_due_at": "ISO8601 datetime with timezone offset or null",
      "new_estimated_minutes": null,
      "new_title": null
    }
  ],
  "clarifying_question": null or "one short question if times or tasks are unclear"
}
Rules:
- title MUST be 1-4 words, concise (e.g. "Bedtime", "Team meeting", "Swim") — never full sentences.
- Put the user's original phrasing in notes when helpful.
- If user mentions specific times (e.g. 2:30pm, 4pm, 16:00), set due_at for today using their timezone offset — not Z/UTC unless user explicitly means UTC.
- When user says "tomorrow" or "tomorrow morning/evening", set due_at on the next calendar day in their timezone (not today).
- A single booking request (e.g. "book a 7pm appointment") must produce exactly ONE proposed_task.
- When user says 7pm in the afternoon/evening, never schedule 7am.
- For move/reschedule/change requests use intent edit_task with edits (not proposed_tasks). Match existing task by title from conversation.
- For meetings/calls/appointments with a time but no stated duration, set estimated_minutes to null and ask one clarifying_question about duration.
- For simple reminders without a fixed end time, estimated_minutes may be 30.
- priority: 0=low, 1=medium, 2=high
- Do not invent tasks not mentioned unless user asks to plan their day generally.
- If only checking in with no tasks, proposed_tasks can be empty and edits empty.
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

    booking = _regex_booking_fallback(user_message, today, tz)
    if booking:
        return booking

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


def _relative_day_offset(user_message: str) -> int | None:
    msg = (user_message or "").lower()
    if re.search(r"\btomorrow\b", msg):
        return 1
    if re.search(r"\btoday\b", msg):
        return 0
    return None


def due_matches_relative_day(
    user_message: str,
    due_at: str | None,
    local_day: date,
    tz: ZoneInfo,
) -> bool:
    """True when extracted due_at matches explicit today/tomorrow in user text."""
    offset = _relative_day_offset(user_message)
    if offset is None or not due_at:
        return True
    try:
        dt = datetime.fromisoformat(str(due_at).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=tz)
        task_day = dt.astimezone(tz).date()
        expected = local_day + timedelta(days=offset)
        return task_day == expected
    except ValueError:
        return False


def _target_day_for_message(user_message: str, today: date) -> date:
    offset = _relative_day_offset(user_message)
    if offset is None:
        return today
    return today + timedelta(days=offset)


def _apply_relative_day(
    tasks: list[dict],
    user_message: str,
    today: date,
    tz: ZoneInfo,
) -> list[dict]:
    offset = _relative_day_offset(user_message)
    if offset is None or offset == 0:
        return tasks
    target = today + timedelta(days=offset)
    out: list[dict] = []
    for t in tasks:
        due_str = t.get("due_at")
        if not due_str:
            out.append(t)
            continue
        try:
            dt = datetime.fromisoformat(str(due_str).replace("Z", "+00:00"))
            local = dt.astimezone(tz) if dt.tzinfo else dt.replace(tzinfo=tz)
            shifted = datetime(
                target.year, target.month, target.day, local.hour, local.minute, tzinfo=tz
            )
            item = dict(t)
            item["due_at"] = shifted.isoformat()
            out.append(item)
        except ValueError:
            out.append(t)
    return out


def _local_hour_from_due_str(due_str: str | None, tz: ZoneInfo) -> int | None:
    if not due_str:
        return None
    try:
        dt = datetime.fromisoformat(str(due_str).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=tz)
        return dt.astimezone(tz).hour
    except ValueError:
        return None


def _extract_explicit_pm_hours(msg: str) -> set[int]:
    hours: set[int] = set()
    for m in re.finditer(r"(\d{1,2})\s*(?::(\d{2}))?\s*pm", msg, re.IGNORECASE):
        h = int(m.group(1))
        hours.add(12 if h == 12 else (h + 12 if h < 12 else h))
    if re.search(r"\b(seven|7)\s*(pm|p\.m\.)", msg, re.IGNORECASE):
        hours.add(19)
    return hours


def _fix_pm_confusion(tasks: list[dict], user_message: str, tz: ZoneInfo) -> list[dict]:
    """Correct 7am tasks when user clearly asked for 7pm."""
    if not _extract_explicit_pm_hours(user_message):
        return tasks
    out: list[dict] = []
    for t in tasks:
        due_str = t.get("due_at")
        if not due_str:
            out.append(t)
            continue
        try:
            dt = datetime.fromisoformat(str(due_str).replace("Z", "+00:00"))
            local = dt.astimezone(tz) if dt.tzinfo else dt.replace(tzinfo=tz)
            if local.hour == 7 and local.minute == 0:
                item = dict(t)
                item["due_at"] = local.replace(hour=19).isoformat()
                out.append(item)
                continue
        except ValueError:
            pass
        out.append(t)
    return out


def _pick_best_booking(tasks: list[dict], user_message: str) -> dict:
    msg = user_message.lower()
    best = tasks[0]
    best_score = -999
    for t in tasks:
        score = 0
        title = str(t.get("title", "")).lower()
        if title and title in msg:
            score += 10
        if re.search(r"\b(appointment|meeting|dinner|open)\b", title):
            score += 2
        if title in ("meal", "appointment"):
            score -= 1
        if score > best_score:
            best_score = score
            best = t
    return best


def _collapse_single_booking(tasks: list[dict], user_message: str, tz: ZoneInfo) -> list[dict]:
    """Keep one task when user asked for a single PM appointment."""
    if len(tasks) <= 1:
        return tasks
    pm_hours = _extract_explicit_pm_hours(user_message)
    if not pm_hours:
        return tasks
    matched = [t for t in tasks if _local_hour_from_due_str(t.get("due_at"), tz) in pm_hours]
    if len(matched) == 1:
        return matched
    if len(matched) > 1:
        return [_pick_best_booking(matched, user_message)]
    afternoon = [t for t in tasks if (_local_hour_from_due_str(t.get("due_at"), tz) or 0) >= 12]
    if afternoon and len(afternoon) < len(tasks):
        return afternoon if len(afternoon) > 1 else afternoon
    return tasks


def _normalize_edits(raw_edits: list, tz: ZoneInfo, user_message: str) -> list[dict]:
    out: list[dict] = []
    for e in raw_edits[:4]:
        if not isinstance(e, dict):
            continue
        match_title = (e.get("match_title") or e.get("title") or "").strip()
        if not match_title and not e.get("task_id"):
            continue
        new_due = e.get("new_due_at")
        new_due_dt = None
        if new_due and isinstance(new_due, str):
            try:
                new_due_dt = _localize_due_at(
                    datetime.fromisoformat(new_due.replace("Z", "+00:00")), tz
                )
            except ValueError:
                new_due_dt = None
        new_mins = e.get("new_estimated_minutes")
        if new_mins is not None:
            try:
                new_mins = int(new_mins)
            except (TypeError, ValueError):
                new_mins = None
        out.append(
            {
                "match_title": match_title[:80] if match_title else None,
                "task_id": e.get("task_id"),
                "new_due_at": new_due_dt.isoformat() if new_due_dt else None,
                "new_estimated_minutes": new_mins,
                "new_title": (str(e["new_title"]).strip()[:80] if e.get("new_title") else None),
            }
        )
    if out and user_message:
        fixed = _fix_pm_confusion(
            [{"due_at": x["new_due_at"], "title": x.get("match_title") or ""} for x in out if x.get("new_due_at")],
            user_message,
            tz,
        )
        for i, item in enumerate(out):
            if i < len(fixed) and fixed[i].get("due_at"):
                item["new_due_at"] = fixed[i]["due_at"]
    return out


def _regex_booking_fallback(user_message: str, today: date, tz: ZoneInfo) -> dict | None:
    """Regex-first booking when user says book/schedule with time (incl. tomorrow)."""
    msg = user_message or ""
    has_book = re.search(r"\b(book|schedule)\b", msg, re.IGNORECASE)
    has_add_event = re.search(
        r"\badd\b.+\b(meeting|appointment|breakfast|call|task)\b", msg, re.IGNORECASE
    )
    if not (has_book or has_add_event):
        return None
    time_m = re.search(r"(\d{1,2})\s*(?::|\.)(\d{2})\s*(am|pm)\b", msg, re.IGNORECASE)
    if not time_m:
        time_m = re.search(r"(\d{1,2})\s*(?::(\d{2}))?\s*(am|pm)\b", msg, re.IGNORECASE)
    if not time_m:
        time_m = re.search(
            r"(?:at|for)\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b",
            msg,
            re.IGNORECASE,
        )
    if not time_m:
        return None
    hour = int(time_m.group(1))
    minute = int(time_m.group(2) or 0)
    ampm = (time_m.group(3) or "").lower()
    if hour > 23:
        return None
    if ampm == "pm" and hour < 12:
        hour += 12
    if ampm == "am" and hour == 12:
        hour = 0
    if not ampm and re.search(r"\bmorning\b", msg, re.IGNORECASE) and hour <= 11:
        pass
    target = _target_day_for_message(msg, today)
    due_dt = datetime(target.year, target.month, target.day, hour, minute, tzinfo=tz)
    title_m = re.search(
        r"(?:book|schedule|add)\s+(?:a\s+)?(?:team\s+)?(meeting|appointment|call)(?:\s+for)?",
        msg,
        re.IGNORECASE,
    )
    title = (title_m.group(1).title() if title_m else "Meeting")
    if title_m and title_m.group(1).lower() == "meeting":
        title = "Team meeting"
    duration_m = re.search(r"(\d+)\s*(?:min|minutes|hour|hours)", msg, re.IGNORECASE)
    est = 60
    if duration_m:
        n = int(duration_m.group(1))
        unit = duration_m.group(0).lower()
        est = n * 60 if "hour" in unit else n
    return {
        "intent": "plan_day",
        "proposed_tasks": [
            {
                "title": title,
                "due_at": due_dt.isoformat(),
                "estimated_minutes": est,
                "priority": 1,
            }
        ],
        "edits": [],
        "clarifying_question": None,
    }


def _regex_edit_fallback(user_message: str, today: date, tz: ZoneInfo) -> dict | None:
    m = re.search(
        r"(?:move|reschedule|change|update)\s+(?:my\s+|the\s+)?([\w\s]{2,40}?)\s+(?:to|at)\s+"
        r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)?",
        user_message,
        re.IGNORECASE,
    )
    if not m:
        return None
    title = m.group(1).strip().title()
    hour = int(m.group(2))
    minute = int(m.group(3) or 0)
    ampm = (m.group(4) or "").lower()
    if ampm == "pm" and hour < 12:
        hour += 12
    if ampm == "am" and hour == 12:
        hour = 0
    if not ampm:
        pm_hours = _extract_explicit_pm_hours(user_message)
        if pm_hours:
            hour = sorted(pm_hours)[0]
    target = _target_day_for_message(user_message, today)
    due_dt = datetime(target.year, target.month, target.day, hour, minute, tzinfo=tz)
    return {
        "intent": "edit_task",
        "proposed_tasks": [],
        "edits": [{"match_title": title, "new_due_at": due_dt.isoformat(), "new_estimated_minutes": None, "new_title": None}],
        "clarifying_question": None,
    }


def _normalize_plan(raw: dict, today: date, tz: ZoneInfo, user_message: str = "") -> dict:
    intent = raw.get("intent") or "other"
    if intent == "edit_task":
        edits = _normalize_edits(raw.get("edits") or [], tz, user_message)
        return {
            "intent": "edit_task",
            "proposed_tasks": [],
            "edits": edits,
            "clarifying_question": raw.get("clarifying_question"),
        }
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

    normalized = _fix_pm_confusion(normalized, user_message, tz)
    normalized = _collapse_single_booking(normalized, user_message, tz)
    normalized = _apply_relative_day(normalized, user_message, today, tz)

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
        "edits": [],
        "clarifying_question": clarifying,
    }


def _regex_fallback(user_message: str, today: date, tz: ZoneInfo) -> dict:
    """Lightweight fallback when LLM JSON fails."""
    edit = _regex_edit_fallback(user_message, today, tz)
    if edit:
        return edit
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
            target = _target_day_for_message(user_message, today)
            due_dt = datetime(target.year, target.month, target.day, hour, minute, tzinfo=tz)
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
    tasks = _fix_pm_confusion(tasks, user_message, tz)
    tasks = _collapse_single_booking(tasks, user_message, tz)
    return {
        "intent": "plan_day" if tasks else "other",
        "proposed_tasks": tasks,
        "edits": [],
        "clarifying_question": clarifying,
    }
