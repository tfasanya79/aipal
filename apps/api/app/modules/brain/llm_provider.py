import json
import logging
import re
import time
from collections.abc import AsyncGenerator

import httpx

from app.shared.config import get_settings

log = logging.getLogger("aipal.llm")
settings = get_settings()

# Tokens allowed for voice turns (fast reply). JSON extraction callers keep 400.
_VOICE_MAX_TOKENS = 180
_JSON_MAX_TOKENS = 400

SYSTEM_PROMPT = (
    "You are AiPal, a warm, empathetic voice companion — not a medical professional or therapist. "
    "Use the user's wake name when you know it. Be ready to help with daily planning, tasks, "
    "check-ins, and calm encouragement. Keep replies concise (3–5 sentences). "
    "Mood or tone hints in context are for adapting warmth only — never diagnose or label emotions clinically. "
    "CRITICAL: In an ongoing conversation, never re-introduce yourself or repeat opening greetings. "
    "Reference what the user already said. When they mention times or activities, acknowledge each "
    "specifically. If a plan draft is pending confirmation, mention it once naturally — never nag. "
    "Never say a task is on Today or added to the schedule unless Tool results include "
    "'Confirmed plan:' or Today already lists it. "
    "Never say a task was moved, rescheduled, updated, or removed unless Tool results include "
    "'Updated task:', 'Completed:', or 'Deleted task:'. "
    "For pending drafts, invite the user to confirm (e.g. say yes to add) rather than implying it is already scheduled. "
    "When offering an edit, say 'say yes and I'll update it' — never claim it is already done. "
    "If the user already confirmed, declined, or said they finished something, accept it "
    "and move on without re-asking. Never be cold or argumentative. "
    "Today (tasks, up next, open count) in context is the app's operational state — use it when relevant. "
    "NEVER tell the user to hold, tap, or press to talk; they are already in voice or text mode. "
    "If wake word is enabled, they may say Hi Pal to start Live — do not insist on tapping the orb."
)


async def llm_chat(messages: list[dict[str, str]], *, max_tokens: int = _VOICE_MAX_TOKENS) -> str:
    provider = settings.llm_provider.lower()
    t0 = time.monotonic()
    try:
        if provider == "anthropic" and settings.anthropic_api_key:
            result = await _anthropic_chat(messages, max_tokens=max_tokens)
        elif provider == "deepseek" and settings.deepseek_api_key:
            result = await _deepseek_chat(messages, max_tokens=max_tokens)
        else:
            result = await _ollama_chat(messages, max_tokens=max_tokens)
    finally:
        elapsed_ms = int((time.monotonic() - t0) * 1000)
        log.info("llm_chat latency_ms=%d max_tokens=%d", elapsed_ms, max_tokens)
    return result


async def llm_stream(
    messages: list[dict[str, str]], *, max_tokens: int = _VOICE_MAX_TOKENS
) -> AsyncGenerator[str, None]:
    """Async generator yielding text tokens as they arrive from the LLM.

    Falls back to a single-shot yield when streaming is unavailable (Ollama local).
    Callers can collect the full response or act on the first complete sentence.
    """
    provider = settings.llm_provider.lower()
    if provider == "anthropic" and settings.anthropic_api_key:
        async for chunk in _anthropic_stream(messages, max_tokens=max_tokens):
            yield chunk
    elif provider == "deepseek" and settings.deepseek_api_key:
        async for chunk in _deepseek_stream(messages, max_tokens=max_tokens):
            yield chunk
    else:
        # Ollama: collect full response and yield as one chunk (streaming optional future work)
        full = await _ollama_chat(messages, max_tokens=max_tokens)
        yield full


async def llm_chat_json(messages: list[dict[str, str]]) -> dict:
    text = await llm_chat(messages, max_tokens=_JSON_MAX_TOKENS)
    text = text.strip()
    if m := re.search(r"\{[\s\S]*\}", text):
        text = m.group(0)
    return json.loads(text)


async def _anthropic_messages_payload(messages: list[dict[str, str]], *, max_tokens: int) -> dict:
    """Anthropic's Messages API takes `system` as a top-level field, not a system-role message."""
    return {
        "model": settings.anthropic_model,
        "system": SYSTEM_PROMPT,
        "messages": messages,
        "max_tokens": max_tokens,
    }


async def _anthropic_chat(messages: list[dict[str, str]], *, max_tokens: int) -> str:
    payload = await _anthropic_messages_payload(messages, max_tokens=max_tokens)
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": settings.anthropic_api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json=payload,
        )
        resp.raise_for_status()
        data = resp.json()
        return "".join(block.get("text", "") for block in data.get("content", []))


async def _anthropic_stream(
    messages: list[dict[str, str]], *, max_tokens: int
) -> AsyncGenerator[str, None]:
    payload = await _anthropic_messages_payload(messages, max_tokens=max_tokens)
    payload["stream"] = True
    t_first: float | None = None
    t0 = time.monotonic()
    async with httpx.AsyncClient(timeout=60.0) as client:
        async with client.stream(
            "POST",
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": settings.anthropic_api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json=payload,
        ) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line.startswith("data:"):
                    continue
                raw = line[5:].strip()
                if not raw:
                    continue
                try:
                    data = json.loads(raw)
                except Exception:
                    continue
                if data.get("type") != "content_block_delta":
                    continue
                token = data.get("delta", {}).get("text") or ""
                if token:
                    if t_first is None:
                        t_first = time.monotonic()
                        log.info(
                            "llm_stream(anthropic) time_to_first_token_ms=%d",
                            int((t_first - t0) * 1000),
                        )
                    yield token
    elapsed_ms = int((time.monotonic() - t0) * 1000)
    log.info("llm_stream(anthropic) total_latency_ms=%d max_tokens=%d", elapsed_ms, max_tokens)


async def _deepseek_chat(messages: list[dict[str, str]], *, max_tokens: int) -> str:
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(
            "https://api.deepseek.com/chat/completions",
            headers={"Authorization": f"Bearer {settings.deepseek_api_key}"},
            json={
                "model": "deepseek-chat",
                "messages": [{"role": "system", "content": SYSTEM_PROMPT}, *messages],
                "max_tokens": max_tokens,
            },
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]


async def _deepseek_stream(
    messages: list[dict[str, str]], *, max_tokens: int
) -> AsyncGenerator[str, None]:
    t_first: float | None = None
    t0 = time.monotonic()
    async with httpx.AsyncClient(timeout=60.0) as client:
        async with client.stream(
            "POST",
            "https://api.deepseek.com/chat/completions",
            headers={"Authorization": f"Bearer {settings.deepseek_api_key}"},
            json={
                "model": "deepseek-chat",
                "messages": [{"role": "system", "content": SYSTEM_PROMPT}, *messages],
                "max_tokens": max_tokens,
                "stream": True,
            },
        ) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line.startswith("data:"):
                    continue
                raw = line[5:].strip()
                if raw == "[DONE]":
                    break
                try:
                    data = json.loads(raw)
                    token = data["choices"][0].get("delta", {}).get("content") or ""
                except Exception:
                    continue
                if token:
                    if t_first is None:
                        t_first = time.monotonic()
                        log.info("llm_stream time_to_first_token_ms=%d", int((t_first - t0) * 1000))
                    yield token
    elapsed_ms = int((time.monotonic() - t0) * 1000)
    log.info("llm_stream total_latency_ms=%d max_tokens=%d", elapsed_ms, max_tokens)


async def _ollama_chat(messages: list[dict[str, str]], *, max_tokens: int) -> str:
    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.post(
            f"{settings.ollama_base_url}/api/chat",
            json={
                "model": settings.ollama_model,
                "messages": [{"role": "system", "content": SYSTEM_PROMPT}, *messages],
                "stream": False,
                "options": {"num_predict": max_tokens},
            },
        )
        resp.raise_for_status()
        return resp.json()["message"]["content"]
