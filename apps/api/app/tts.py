"""Text-to-speech: edge-tts with espeak-ng fallback."""

from __future__ import annotations

import asyncio
import io
import logging
import subprocess
import tempfile
from pathlib import Path

log = logging.getLogger("aipal.tts")

DEFAULT_VOICE = "en-US-JennyNeural"


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


async def synthesize_stream(text: str, voice: str | None = None):
    """Async generator yielding (audio_bytes, mime) as edge-tts chunks arrive."""
    text = (text or "").strip()
    if not text:
        return
    chosen = voice or DEFAULT_VOICE
    try:
        import edge_tts

        communicate = edge_tts.Communicate(text, chosen)
        yielded_any = False
        async for chunk in communicate.stream():
            if chunk.get("type") == "audio":
                data = chunk.get("data")
                if data:
                    yielded_any = True
                    yield data, "audio/mpeg"
        if yielded_any:
            return
    except Exception as e:
        log.warning("edge-tts stream failed: %s; trying batch synthesize", e)
    audio, mime = await synthesize(text, voice=voice)
    if audio:
        yield audio, mime

