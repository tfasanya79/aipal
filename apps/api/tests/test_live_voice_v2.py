"""Live Voice v2 unit tests."""

import asyncio
import base64
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest

from app.voice_pipeline import TurnCancellationRegistry, split_sentences, strip_plan_json_block


def test_split_sentences():
    complete, rest = split_sentences("Hello there. How are")
    assert complete == ["Hello there."]
    assert rest == "How are"
    complete2, rest2 = split_sentences("Done.", flush=True)
    assert complete2 == ["Done."]
    assert rest2 == ""


def test_strip_plan_json_block():
    text = 'Sure thing.\n```json\n{"intent":"plan_day","proposed_tasks":[]}\n```'
    visible, raw = strip_plan_json_block(text)
    assert "Sure thing" in visible
    assert raw is not None
    assert "plan_day" in raw


@pytest.mark.asyncio
async def test_turn_cancellation_registry():
    reg = TurnCancellationRegistry()

    async def slow():
        await asyncio.sleep(10)

    task = asyncio.create_task(slow())
    reg.register("t1", task)
    assert reg.cancel("t1") is True
    with pytest.raises(asyncio.CancelledError):
        await task


@pytest.mark.asyncio
async def test_whisper_streaming_stt_partial_dedupe():
    from app.services.whisper_streaming_stt import WhisperStreamingSTT
    from app.config import Settings

    settings = Settings(whisper_stream_partial_interval_ms=0)
    stt = WhisperStreamingSTT(settings)

    pcm = (np.zeros(16000, dtype=np.int16)).tobytes()

    with patch.object(stt, "_transcribe", new_callable=AsyncMock) as mock_tx:
        mock_tx.return_value = "hello"
        await stt.on_speech_start()
        first = await stt.feed_audio(pcm)
        second = await stt.feed_audio(pcm)
        assert first == "hello"
        assert second is None


@pytest.mark.asyncio
async def test_whisper_streaming_stt_partial_metrics():
    from app.services.whisper_streaming_stt import WhisperStreamingSTT
    from app.config import Settings

    settings = Settings(whisper_stream_partial_interval_ms=0)
    stt = WhisperStreamingSTT(settings)
    pcm = (np.zeros(16000, dtype=np.int16)).tobytes()

    with patch.object(stt, "_transcribe", new_callable=AsyncMock) as mock_tx:
        mock_tx.return_value = "hello"
        await stt.on_speech_start()
        await stt.feed_audio(pcm)
        await stt.on_speech_end()
        metrics = stt.consume_metrics()
        assert "stt_partial_ms" in metrics
        assert metrics["stt_partial_ms"] >= 0


@pytest.mark.asyncio
async def test_run_voice_turn_stream_yields_deltas():
    from app.services.voice_turn import run_voice_turn_stream

    async def fake_stream(_messages):
        yield "Hi "
        yield "there."

    user = MagicMock()
    user.id = "user-1"
    user.timezone = "UTC"
    user.wake_name = "Alex"
    user.display_name = "Alex"
    user.about_me = None

    db = AsyncMock()

    with (
        patch("app.services.voice_turn.build_turn_context", new_callable=AsyncMock) as mock_ctx,
        patch("app.services.voice_turn.llm_chat_stream", side_effect=fake_stream),
        patch("app.services.voice_turn.conv_svc.append_turn", new_callable=AsyncMock),
        patch("app.services.voice_turn.draft_svc.get_draft", new_callable=AsyncMock, return_value=None),
        patch("app.services.voice_turn.memory_add"),
    ):
        mock_ctx.return_value = {
            "early_reply": None,
            "messages": [{"role": "user", "content": "hi"}],
            "tool_actions": [],
        }
        events = []
        async for ev in run_voice_turn_stream(db, user, "hi", "sess-1"):
            events.append(ev)
        deltas = [e for e in events if e["type"] == "reply_delta"]
        assert any("Hi" in d["text"] for d in deltas)
        meta = [e for e in events if e["type"] == "turn_meta"]
        assert meta and meta[0]["reply"]


@pytest.mark.asyncio
async def test_llm_chat_stream_deepseek_parses_sse():
    from app.llm_provider import llm_chat_stream

    lines = [
        'data: {"choices":[{"delta":{"content":"Hello"}}]}',
        "data: [DONE]",
    ]

    class FakeResp:
        def raise_for_status(self):
            return None

        async def aiter_lines(self):
            for line in lines:
                yield line

    class FakeStream:
        async def __aenter__(self):
            return FakeResp()

        async def __aexit__(self, *args):
            return None

    class FakeClient:
        def stream(self, *args, **kwargs):
            return FakeStream()

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

    with patch("app.llm_provider.settings") as mock_settings:
        mock_settings.llm_provider = "deepseek"
        mock_settings.deepseek_api_key = "test-key"
        with patch("app.llm_provider.httpx.AsyncClient", return_value=FakeClient()):
            chunks = []
            async for c in llm_chat_stream([{"role": "user", "content": "hi"}]):
                chunks.append(c)
            assert chunks == ["Hello"]
