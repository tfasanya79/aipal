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


async def _dispatch_chat(provider: str, messages: list[dict[str, str]], *, max_tokens: int) -> str:
    if provider == "anthropic" and settings.anthropic_api_key:
        return await _anthropic_chat(messages, max_tokens=max_tokens)
    if provider == "deepseek" and settings.deepseek_api_key:
        return await _deepseek_chat(messages, max_tokens=max_tokens)
    raise RuntimeError(f"LLM provider '{provider}' is not configured (missing API key or unsupported)")


async def llm_chat(messages: list[dict[str, str]], *, max_tokens: int = _VOICE_MAX_TOKENS) -> str:
    provider = settings.llm_provider.lower()
    used_provider = provider
    t0 = time.monotonic()
    try:
        result = await _dispatch_chat(provider, messages, max_tokens=max_tokens)
    except Exception as exc:
        fallback = settings.llm_fallback_provider.lower()
        if not fallback or fallback == provider:
            raise
        log.warning(
            "llm_chat primary provider=%s failed (%s); falling back to provider=%s",
            provider, exc, fallback,
        )
        used_provider = fallback
        result = await _dispatch_chat(fallback, messages, max_tokens=max_tokens)
    finally:
        elapsed_ms = int((time.monotonic() - t0) * 1000)
        log.info("llm_chat provider=%s latency_ms=%d max_tokens=%d", used_provider, elapsed_ms, max_tokens)
    return result


async def llm_stream(
    messages: list[dict[str, str]], *, max_tokens: int = _VOICE_MAX_TOKENS
) -> AsyncGenerator[str, None]:
    """Async generator yielding text tokens as they arrive from the LLM.

    Falls back automatically from the primary provider to the configured fallback
    provider (see settings.llm_fallback_provider) if the primary errors before yielding
    any tokens.
    Callers can collect the full response or act on the first complete sentence.
    """
    provider = settings.llm_provider.lower()
    started = False
    try:
        async for chunk in _dispatch_stream(provider, messages, max_tokens=max_tokens):
            started = True
            yield chunk
    except Exception as exc:
        if started:
            # Already yielded partial tokens (e.g. to early-TTS) - unsafe to restart the reply
            # from a different provider mid-stream, so surface the failure instead of retrying.
            log.error(
                "llm_stream provider=%s failed mid-stream after partial output: %s", provider, exc
            )
            raise
        fallback = settings.llm_fallback_provider.lower()
        if not fallback or fallback == provider:
            raise
        log.warning(
            "llm_stream primary provider=%s failed before first token (%s); falling back to provider=%s",
            provider, exc, fallback,
        )
        async for chunk in _dispatch_stream(fallback, messages, max_tokens=max_tokens):
            yield chunk


async def _dispatch_stream(
    provider: str, messages: list[dict[str, str]], *, max_tokens: int
) -> AsyncGenerator[str, None]:
    if provider == "anthropic" and settings.anthropic_api_key:
        async for chunk in _anthropic_stream(messages, max_tokens=max_tokens):
            yield chunk
    elif provider == "deepseek" and settings.deepseek_api_key:
        async for chunk in _deepseek_stream(messages, max_tokens=max_tokens):
            yield chunk
    else:
        raise RuntimeError(f"LLM provider '{provider}' is not configured (missing API key or unsupported)")


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
