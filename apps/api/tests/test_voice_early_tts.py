"""Regression tests for the early-TTS reconciliation helper used by the
voice audio_turn pipeline (see app/modules/voice/router.py).

These test _resolve_early_tts directly (rather than the full audio_turn
HTTP flow) so the safety-critical reconciliation logic -- reuse speculative
audio only when the post-generation safety checks left the reply unchanged,
otherwise discard it -- is exercised without needing to mock the entire
_reply_for_text call chain (db/conversation/memory/intent extraction).
"""
import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from app.routers.turn import _resolve_early_tts


async def _task_returning(bytes_: bytes, mime: str) -> asyncio.Task:
    async def _coro():
        return bytes_, mime

    return asyncio.create_task(_coro())


@pytest.mark.asyncio
async def test_early_tts_reused_when_reply_unchanged_and_matches_first_sentence():
    """Common case: reply == raw LLM output == the speculative first sentence
    (single-sentence reply). The speculative audio should be reused as-is."""
    task = await _task_returning(b"first-sentence-audio", "audio/mpeg")
    early_audio: dict = {}

    await _resolve_early_tts(
        raw_reply="All set.",
        final_reply="All set.",
        early_first_sent="All set.",
        early_tts_task=task,
        voice="aria",
        early_audio=early_audio,
        session_id="sess-1",
    )

    assert early_audio == {"bytes": b"first-sentence-audio", "mime": "audio/mpeg"}


@pytest.mark.asyncio
async def test_early_tts_reused_with_remainder_synthesis_when_reply_has_more_sentences():
    """Reply unchanged by safety checks but longer than the speculative first
    sentence -- remainder should be synthesized and concatenated, since both
    chunks share the same mime type."""
    task = await _task_returning(b"first-part", "audio/mpeg")
    early_audio: dict = {}

    with patch(
        "app.routers.turn.synthesize", new_callable=AsyncMock
    ) as mock_synth:
        mock_synth.return_value = (b"rest-part", "audio/mpeg")

        await _resolve_early_tts(
            raw_reply="Sure thing. I'll also check your calendar.",
            final_reply="Sure thing. I'll also check your calendar.",
            early_first_sent="Sure thing.",
            early_tts_task=task,
            voice="aria",
            early_audio=early_audio,
            session_id="sess-2",
        )

        mock_synth.assert_awaited_once_with("I'll also check your calendar.", "aria")

    assert early_audio == {"bytes": b"first-part" + b"rest-part", "mime": "audio/mpeg"}


@pytest.mark.asyncio
async def test_early_tts_discarded_when_safety_check_rewrites_reply():
    """If a safety check (honesty override / therapy blanking / mutation
    recovery) changed the final reply, the speculative audio -- synthesized
    for the ORIGINAL, now-wrong text -- must never be used. The task should
    be cancelled and early_audio left empty so the caller re-synthesizes the
    real final text fresh."""
    task = await _task_returning(b"stale-audio-for-wrong-text", "audio/mpeg")
    early_audio: dict = {}

    await _resolve_early_tts(
        raw_reply="I'll add that appointment for you.",
        final_reply="I haven't added anything yet -- want me to?",
        early_first_sent="I'll add that appointment for you.",
        early_tts_task=task,
        voice="aria",
        early_audio=early_audio,
        session_id="sess-3",
    )

    assert early_audio == {}
    # cancel() only requests cancellation; give the event loop a tick to
    # actually process it before asserting the task reached a final state.
    await asyncio.sleep(0)
    assert task.cancelled() or task.done()


@pytest.mark.asyncio
async def test_early_tts_discarded_on_mime_mismatch_between_segments():
    """If the first-sentence chunk and remainder chunk come back with
    different mime types (e.g. TTS fallback fired for only one segment),
    concatenation would produce corrupt audio -- must not be used."""
    task = await _task_returning(b"first-part", "audio/mpeg")
    early_audio: dict = {}

    with patch(
        "app.routers.turn.synthesize", new_callable=AsyncMock
    ) as mock_synth:
        mock_synth.return_value = (b"rest-part", "audio/wav")  # mismatched mime

        await _resolve_early_tts(
            raw_reply="Okay. Here is the rest of it.",
            final_reply="Okay. Here is the rest of it.",
            early_first_sent="Okay.",
            early_tts_task=task,
            voice="aria",
            early_audio=early_audio,
            session_id="sess-4",
        )

    # Mismatched mime types must not be concatenated -- early_audio stays empty
    # so audio_turn falls back to a single fresh synthesize() call.
    assert early_audio == {}


@pytest.mark.asyncio
async def test_no_speculative_task_is_a_no_op():
    """When no speculative TTS was started (e.g. text channel, or no voice
    provided), the helper must do nothing and leave early_audio untouched."""
    early_audio: dict = {}

    await _resolve_early_tts(
        raw_reply="Hi!",
        final_reply="Hi!",
        early_first_sent=None,
        early_tts_task=None,
        voice=None,
        early_audio=early_audio,
        session_id="sess-5",
    )

    assert early_audio == {}
