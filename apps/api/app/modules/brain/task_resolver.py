"""Match user utterances to open Today tasks."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

from app.shared.schemas import TaskResponse, TodayViewResponse


@dataclass
class ResolvedTask:
    task_id: int
    title: str
    confidence: float
    due_at: datetime | None = None


def open_tasks(today_snap: TodayViewResponse) -> list[TaskResponse]:
    seen: set[int] = set()
    out: list[TaskResponse] = []
    for tasks in (today_snap.sections.now, today_snap.sections.upcoming):
        for t in tasks:
            if t.status in ("done", "skipped") or t.id in seen:
                continue
            seen.add(t.id)
            out.append(t)
    return out


def _title_score(needle: str, haystack: str) -> float:
    nl = needle.lower().strip()
    hl = haystack.lower().strip()
    if not nl or not hl:
        return 0.0
    if nl == hl:
        return 1.0
    if nl in hl or hl in nl:
        return 0.85
    nw = set(nl.split())
    hw = set(hl.split())
    overlap = len(nw & hw)
    if overlap == 0:
        return 0.0
    return min(0.8, overlap / max(len(nw), len(hw)))


def resolve_task(
    *,
    match_title: str | None,
    task_id: int | None,
    user_text: str,
    today_snap: TodayViewResponse,
) -> ResolvedTask | None:
    tasks = open_tasks(today_snap)
    if not tasks:
        return None

    if task_id is not None:
        for t in tasks:
            if t.id == task_id:
                return ResolvedTask(task_id=t.id, title=t.title, confidence=1.0, due_at=t.due_at)

    candidates: list[ResolvedTask] = []
    needles: list[str] = []
    if match_title:
        needles.append(match_title)
    needles.extend(re.findall(r"[A-Za-z][\w\s]{2,40}", user_text))
    for t in tasks:
        best = max((_title_score(n, t.title) for n in needles), default=0.0)
        if best >= 0.5:
            candidates.append(ResolvedTask(task_id=t.id, title=t.title, confidence=best, due_at=t.due_at))

    if not candidates:
        return None
    candidates.sort(key=lambda c: c.confidence, reverse=True)
    best = candidates[0]
    if len(candidates) > 1 and candidates[1].confidence >= best.confidence - 0.1:
        return None
    return best


def format_due_local(due_at: datetime | None, timezone: str) -> str:
    if due_at is None:
        return "no time"
    try:
        tz = ZoneInfo(timezone or "UTC")
    except Exception:
        tz = ZoneInfo("UTC")
    local = due_at.astimezone(tz) if due_at.tzinfo else due_at.replace(tzinfo=tz)
    return local.strftime("%I:%M %p").lstrip("0")
