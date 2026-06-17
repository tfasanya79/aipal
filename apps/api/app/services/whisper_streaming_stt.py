"""Self-hosted streaming STT via faster-whisper."""

from __future__ import annotations

import asyncio
import logging
import time

import numpy as np

from ..config import Settings
from ..stt import _get_model

log = logging.getLogger("aipal.whisper_stream")

# One CPU inference job at a time across connections.
_inference_semaphore: asyncio.Semaphore | None = None


def _semaphore() -> asyncio.Semaphore:
    global _inference_semaphore
    if _inference_semaphore is None:
        _inference_semaphore = asyncio.Semaphore(1)
    return _inference_semaphore


class WhisperStreamingSTT:
    SAMPLE_RATE = 16000

    def __init__(self, settings: Settings) -> None:
        self._partial_interval_ms = settings.whisper_stream_partial_interval_ms
        self._buffer = bytearray()
        self._last_partial_text = ""
        self._last_partial_at = 0.0
        self._speech_active = False
        self._speech_t0: float | None = None
        self._first_partial_mono: float | None = None
        self._last_metrics: dict[str, int] = {}

    def reset(self) -> None:
        self._buffer.clear()
        self._last_partial_text = ""
        self._last_partial_at = 0.0
        self._speech_active = False
        self._speech_t0 = None
        self._first_partial_mono = None

    def consume_metrics(self) -> dict[str, int]:
        metrics = dict(self._last_metrics)
        self._last_metrics = {}
        return metrics

    async def on_speech_start(self) -> None:
        self._speech_active = True
        self._buffer.clear()
        self._last_partial_text = ""
        self._last_partial_at = 0.0
        self._speech_t0 = time.monotonic()
        self._first_partial_mono = None
        self._last_metrics = {}

    async def feed_audio(self, pcm: bytes) -> str | None:
        if not pcm:
            return None
        self._buffer.extend(pcm)
        if not self._speech_active:
            return None
        now = time.monotonic() * 1000
        if now - self._last_partial_at < self._partial_interval_ms:
            return None
        text = await self._transcribe(beam_size=1)
        if text and text != self._last_partial_text:
            if self._first_partial_mono is None:
                self._first_partial_mono = time.monotonic()
            self._last_partial_text = text
            self._last_partial_at = now
            return text
        self._last_partial_at = now
        return None

    async def on_speech_end(self) -> str:
        self._speech_active = False
        if self._speech_t0 is not None and self._first_partial_mono is not None:
            self._last_metrics["stt_partial_ms"] = int(
                (self._first_partial_mono - self._speech_t0) * 1000
            )
        if not self._buffer:
            self.reset()
            return ""
        text = await self._transcribe(beam_size=5)
        self.reset()
        return text

    async def _transcribe(self, *, beam_size: int) -> str:
        pcm = bytes(self._buffer)
        if len(pcm) < 320:  # ~10 ms at 16 kHz
            return ""

        async with _semaphore():
            return await asyncio.to_thread(self._transcribe_sync, pcm, beam_size)

    def _transcribe_sync(self, pcm: bytes, beam_size: int) -> str:
        audio = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0
        model = _get_model()
        try:
            segments, _ = model.transcribe(
                audio,
                language="en",
                beam_size=beam_size,
                vad_filter=True,
            )
            return " ".join(s.text.strip() for s in segments if s.text.strip()).strip()
        except Exception as e:
            log.warning("Whisper streaming transcribe failed: %s", e)
            return ""
