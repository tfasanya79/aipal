"""Local STT via faster-whisper."""

from __future__ import annotations

import json
import logging
import subprocess
import tempfile
import time
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.shared.config import get_settings

log = logging.getLogger("aipal.stt")
DEBUG_LOG = "/home/dev/.cursor/debug-60ce92.log"


@lru_cache
def _get_model() -> Any:
    from faster_whisper import WhisperModel

    settings = get_settings()
    return WhisperModel(settings.whisper_model, device="cpu", compute_type="int8")


def prewarm_model() -> None:
    """Load Whisper into memory (call once at API startup)."""
    _get_model()
    settings = get_settings()
    log.info("Whisper STT pre-warmed (model=%s device=cpu)", settings.whisper_model)


def _agent_debug(hypothesis_id: str, message: str, data: dict) -> None:
    # #region agent log
    try:
        with open(DEBUG_LOG, "a", encoding="utf-8") as f:
            f.write(
                json.dumps(
                    {
                        "sessionId": "60ce92",
                        "hypothesisId": hypothesis_id,
                        "location": "stt.py:transcribe_path",
                        "message": message,
                        "data": data,
                        "timestamp": int(time.time() * 1000),
                        "runId": "pre-fix",
                    }
                )
                + "\n"
            )
    except OSError:
        pass
    # #endregion


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


def _transcribe_file(model: Any, path: str, *, vad_filter: bool) -> str:
    segments, _ = model.transcribe(path, language="en", beam_size=5, vad_filter=vad_filter)
    return " ".join(s.text.strip() for s in segments if s.text.strip()).strip()


def transcribe_path(path: str) -> str:
    model = _get_model()
    suffix = Path(path).suffix

    for vad_filter in (True, False):
        try:
            text = _transcribe_file(model, path, vad_filter=vad_filter)
            _agent_debug(
                "H1",
                "stt_pass",
                {"vad_filter": vad_filter, "converted": False, "text_len": len(text), "suffix": suffix},
            )
            if text:
                return text
        except Exception as exc:
            _agent_debug(
                "H1",
                "stt_pass_error",
                {"vad_filter": vad_filter, "converted": False, "error": type(exc).__name__},
            )

    converted = _ffmpeg_to_wav16_mono(path) if not path.lower().endswith(".wav") else path
    try:
        for vad_filter in (True, False):
            try:
                text = _transcribe_file(model, converted, vad_filter=vad_filter)
                _agent_debug(
                    "H1",
                    "stt_pass",
                    {
                        "vad_filter": vad_filter,
                        "converted": converted != path,
                        "text_len": len(text),
                        "suffix": suffix,
                    },
                )
                if text:
                    return text
            except Exception as exc:
                _agent_debug(
                    "H1",
                    "stt_pass_error",
                    {
                        "vad_filter": vad_filter,
                        "converted": converted != path,
                        "error": type(exc).__name__,
                    },
                )
        return ""
    finally:
        if converted != path:
            Path(converted).unlink(missing_ok=True)
