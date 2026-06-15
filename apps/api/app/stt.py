"""Local STT via faster-whisper."""

from __future__ import annotations

import subprocess
import tempfile
from functools import lru_cache
from pathlib import Path
from typing import Any

from .config import get_settings


@lru_cache
def _get_model() -> Any:
    from faster_whisper import WhisperModel

    settings = get_settings()
    return WhisperModel(settings.whisper_model, device="cpu", compute_type="int8")


def _ffmpeg_to_wav16_mono(path: str) -> str:
    if path.lower().endswith(".wav"):
        return path
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        out = f.name
    try:
        from imageio_ffmpeg import get_ffmpeg_exe

        ff = get_ffmpeg_exe()
        subprocess.run([ff, "-y", "-i", path, "-ac", "1", "-ar", "16000", out], check=True, capture_output=True)
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        Path(out).unlink(missing_ok=True)
        raise RuntimeError(f"ffmpeg conversion failed: {e!s}") from e
    return out


def transcribe_path(path: str) -> str:
    model = _get_model()
    try:
        segments, _ = model.transcribe(path, language="en", beam_size=5, vad_filter=True)
        text = " ".join(s.text.strip() for s in segments if s.text.strip()).strip()
        if text:
            return text
    except Exception:
        pass

    converted = _ffmpeg_to_wav16_mono(path) if not path.lower().endswith(".wav") else path
    try:
        segments, _ = model.transcribe(converted, language="en", beam_size=5, vad_filter=True)
        return " ".join(s.text.strip() for s in segments if s.text.strip()).strip()
    finally:
        if converted != path:
            Path(converted).unlink(missing_ok=True)
