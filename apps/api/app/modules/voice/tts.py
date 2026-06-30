"""Text-to-speech: edge-tts with espeak-ng fallback."""

from __future__ import annotations

import asyncio
import io
import logging
import subprocess
import tempfile
from pathlib import Path

log = logging.getLogger("aipal.tts")

DEFAULT_VOICE = "en-US-AriaNeural"

# Curated voice catalogue — free for all users via edge-tts (no API key required).
VOICE_CATALOGUE: list[dict] = [
    {
        "id": "aria",
        "display_name": "Aria",
        "gender": "Female",
        "style": "Warm, clear",
        "edge_voice": "en-US-AriaNeural",
        "is_default": True,
        "sample_phrase": "Hi, I'm your AiPal Companion — ready when you are.",
    },
    {
        "id": "jenny",
        "display_name": "Jenny",
        "gender": "Female",
        "style": "Bright, friendly",
        "edge_voice": "en-US-JennyNeural",
        "is_default": False,
        "sample_phrase": "Hi, I'm your AiPal Companion — ready when you are.",
    },
    {
        "id": "emma",
        "display_name": "Emma",
        "gender": "Female",
        "style": "Calm, natural",
        "edge_voice": "en-US-EmmaNeural",
        "is_default": False,
        "sample_phrase": "Hi, I'm your AiPal Companion — ready when you are.",
    },
    {
        "id": "andrew",
        "display_name": "Andrew",
        "gender": "Male",
        "style": "Deep, calm",
        "edge_voice": "en-US-AndrewNeural",
        "is_default": False,
        "sample_phrase": "Hi, I'm your AiPal Companion — ready when you are.",
    },
    {
        "id": "brian",
        "display_name": "Brian",
        "gender": "Male",
        "style": "Warm, steady",
        "edge_voice": "en-US-BrianNeural",
        "is_default": False,
        "sample_phrase": "Hi, I'm your AiPal Companion — ready when you are.",
    },
    {
        "id": "sonia",
        "display_name": "Sonia (British)",
        "gender": "Female",
        "style": "Clear, British",
        "edge_voice": "en-GB-SoniaNeural",
        "is_default": False,
        "sample_phrase": "Hi, I'm your AiPal Companion — ready when you are.",
    },
]

_VOICE_MAP: dict[str, str] = {v["id"]: v["edge_voice"] for v in VOICE_CATALOGUE}


def get_voice_id(voice_pref: str | None) -> str:
    """Resolve a user voice preference ID to an edge-tts voice name."""
    return _VOICE_MAP.get(voice_pref or "aria", DEFAULT_VOICE)


async def _edge_synth(text: str, voice: str) -> bytes:
    import edge_tts

    out = io.BytesIO()
    communicate = edge_tts.Communicate(text, voice)
    async for chunk in communicate.stream():
        if chunk.get("type") == "audio":
            data = chunk.get("data")
            if data:
                out.write(data)
    return out.getvalue()


def _espeak_synth(text: str) -> bytes:
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        out_path = f.name
    try:
        subprocess.run(
            ["espeak-ng", "-v", "en", "-s", "170", "-w", out_path, text],
            check=True,
            capture_output=True,
        )
        return Path(out_path).read_bytes()
    finally:
        Path(out_path).unlink(missing_ok=True)


async def synthesize(text: str, voice: str | None = None) -> tuple[bytes, str]:
    text = (text or "").strip()
    if not text:
        return b"", "audio/mpeg"
    chosen = voice or DEFAULT_VOICE
    try:
        audio = await _edge_synth(text, chosen)
        if audio:
            return audio, "audio/mpeg"
    except Exception as e:
        log.warning("edge-tts failed: %s; trying espeak-ng", e)
    try:
        audio = await asyncio.to_thread(_espeak_synth, text)
        return audio, "audio/wav"
    except (OSError, subprocess.CalledProcessError) as e:
        log.error("espeak-ng failed: %s", e)
        return b"", "audio/mpeg"
