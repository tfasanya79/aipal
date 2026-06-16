import logging

import httpx

from .config import get_settings

log = logging.getLogger("aipal.llm")
settings = get_settings()

SYSTEM_PROMPT = (
    "You are AiPal, a warm, empathetic voice companion — not a medical professional or therapist. "
    "Use the user's wake name when you know it. Be ready to help with daily planning, tasks, "
    "check-ins, and calm encouragement. Keep replies concise (3–5 sentences). "
    "CRITICAL: In an ongoing conversation, never re-introduce yourself or repeat opening greetings. "
    "Reference what the user already said. When they mention times or activities, acknowledge each "
    "specifically. If a plan draft is pending confirmation, mention it once naturally — never nag. "
    "If the user already confirmed, declined, or said they finished something, accept it "
    "and move on without re-asking. Never be cold or argumentative. "
    "Today (tasks, up next, open count) in context is the app's operational state — use it when relevant. "
    "NEVER tell the user to hold, tap, or press to talk; they are already in voice or text mode. "
    "If wake word is enabled, they may say Hi Pal to start Live — do not insist on tapping the orb."
)


async def llm_chat(messages: list[dict[str, str]]) -> str:
    provider = settings.llm_provider.lower()
    if provider == "deepseek" and settings.deepseek_api_key:
        return await _deepseek_chat(messages)
    return await _ollama_chat(messages)


async def _deepseek_chat(messages: list[dict[str, str]]) -> str:
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(
            "https://api.deepseek.com/chat/completions",
            headers={"Authorization": f"Bearer {settings.deepseek_api_key}"},
            json={
                "model": "deepseek-chat",
                "messages": [{"role": "system", "content": SYSTEM_PROMPT}, *messages],
                "max_tokens": 400,
            },
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]


async def llm_chat_json(messages: list[dict[str, str]]) -> dict:
    import json
    import re

    text = await llm_chat(messages)
    text = text.strip()
    if m := re.search(r"\{[\s\S]*\}", text):
        text = m.group(0)
    return json.loads(text)


async def _ollama_chat(messages: list[dict[str, str]]) -> str:
    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.post(
            f"{settings.ollama_base_url}/api/chat",
            json={
                "model": settings.ollama_model,
                "messages": [{"role": "system", "content": SYSTEM_PROMPT}, *messages],
                "stream": False,
            },
        )
        resp.raise_for_status()
        return resp.json()["message"]["content"]
