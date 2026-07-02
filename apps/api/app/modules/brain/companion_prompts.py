"""Warm companion copy for Live mode and prompts."""

import random

STARTER_LINES = [
    "Hi {name}, I am here with you. How are you feeling right now?",
    "Welcome back, {name}. Would you like a quick check-in, or a calm moment first?",
    "Hey {name}, I am listening. What feels most present for you right now?",
    "{name}, I am glad you are here. What would feel most helpful to talk through?",
]

WELLNESS_PROMPTS_OVERWHELMED = [
    "You sound like a lot on your plate. Want me to lighten your schedule for today?",
    "I sense you're feeling overwhelmed. Should we focus on just the 3 most important things?",
    "Take a breath. Want to reschedule some non-urgent tasks to later this week?",
    "You can do this, but let's be smart. Want me to push back anything that's not urgent?",
]

WELLNESS_PROMPTS_STRESSED = [
    "I'm picking up on some stress. Want me to help you prioritize what's truly urgent right now?",
    "Sounds like you're under pressure. Should we break one of these tasks into smaller steps?",
    "You've got this, but let's make it manageable. Want to defer anything to tomorrow?",
]

SMART_FOLLOW_UPS_TEMPLATES = [
    "Should I block focus time before this?",
    "Do you need travel time added?",
    "Anything you need to prep?",
    "Want a reminder to review notes beforehand?",
    "Should I set an earlier alert?",
]


def pick_starter(wake_name: str | None) -> str:
    name = (wake_name or "friend").strip() or "friend"
    line = random.choice(STARTER_LINES)
    return line.format(name=name)


def pick_wellness_prompt(mood_hint: str | None = None, is_overwhelmed: bool = False) -> str | None:
    """Return a wellness check-in prompt if user shows stress/overwhelm signals."""
    if is_overwhelmed:
        return random.choice(WELLNESS_PROMPTS_OVERWHELMED)
    if mood_hint == "gentle":
        return random.choice(WELLNESS_PROMPTS_STRESSED)
    return None


def pick_follow_up_prompt() -> str:
    """Return a smart follow-up question after task booking."""
    return random.choice(SMART_FOLLOW_UPS_TEMPLATES)

