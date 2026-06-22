import json
import logging
import re
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.brain.llm_provider import llm_chat
from app.shared.models import Task
from app.shared.schemas import TaskCreate
from app.modules.today import tasks as task_svc

log = logging.getLogger("aipal.task_planner")

BREAKDOWN_PROMPT = (
    "Break the following task into 2-6 concrete sub-steps for today. "
    "Return ONLY a JSON array of objects with keys title (string) and estimated_minutes (integer 5-60). "
    "No markdown, no explanation."
)


async def breakdown_task(db: AsyncSession, user_id: uuid.UUID, task: Task) -> list[Task]:
    existing = await task_svc._load_subtasks(db, user_id, [task.id])
    if existing.get(task.id):
        return existing[task.id]

    messages = [
        {"role": "user", "content": f"{BREAKDOWN_PROMPT}\n\nTask: {task.title}"},
    ]
    try:
        raw = await llm_chat(messages)
        items = _parse_breakdown_json(raw)
    except Exception as e:
        log.warning("breakdown failed: %s", e)
        items = [
            {"title": f"Start: {task.title[:40]}", "estimated_minutes": 15},
            {"title": f"Finish: {task.title[:40]}", "estimated_minutes": 15},
        ]

    created = []
    for idx, item in enumerate(items[:6]):
        sub = await task_svc.create_task(
            db,
            user_id,
            TaskCreate(
                title=str(item["title"])[:500],
                estimated_minutes=int(item.get("estimated_minutes", 15)),
                parent_task_id=task.id,
                sort_order=idx,
                source="breakdown",
                due_at=task.due_at,
                category=task.category,
            ),
        )
        created.append(sub)

    total_mins = sum(s.estimated_minutes or 0 for s in created)
    if total_mins and not task.estimated_minutes:
        await task_svc.update_task(db, user_id, task.id, estimated_minutes=total_mins)

    return created


def _parse_breakdown_json(raw: str) -> list[dict]:
    text = raw.strip()
    if m := re.search(r"\[[\s\S]*\]", text):
        text = m.group(0)
    data = json.loads(text)
    if not isinstance(data, list):
        raise ValueError("expected list")
    out = []
    for item in data:
        if isinstance(item, dict) and item.get("title"):
            mins = item.get("estimated_minutes", 15)
            out.append({"title": str(item["title"]), "estimated_minutes": max(5, min(60, int(mins)))})
    if len(out) < 2:
        raise ValueError("too few items")
    return out
