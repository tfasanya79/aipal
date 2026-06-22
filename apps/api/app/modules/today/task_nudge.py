import logging
import random

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.brain.llm_provider import llm_chat
from app.shared.models import Task, User

log = logging.getLogger("aipal.task_nudge")

_TEMPLATES = (
    "Hi {name}, {minutes} minutes to {title} — hope you're ready.",
    "Hey {name}, {title} is in about {minutes} minutes.",
    "{name}, just a heads up — {minutes} minutes until {title}.",
    "Hi {name}, coming up: {title} in {minutes} minutes.",
)


async def build_nudge_message(
    db: AsyncSession,
    user: User,
    task: Task,
    minutes: int,
) -> str:
    name = user.wake_name or user.display_name or "friend"
    title = task.title
    prompt = (
        f"Write ONE short spoken sentence ({name}'s wake name is {name}) reminding them "
        f"that '{title}' is in {minutes} minutes. Warm, not pushy. No quotes. Max 20 words."
    )
    try:
        text = (await llm_chat([{"role": "user", "content": prompt}])).strip()
        if text and len(text) < 200:
            return text
    except Exception as e:
        log.warning("nudge LLM failed: %s", e)
    return random.choice(_TEMPLATES).format(name=name, minutes=minutes, title=title)
