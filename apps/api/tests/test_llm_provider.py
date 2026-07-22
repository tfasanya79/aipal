"""Regression tests for the Anthropic-primary / DeepSeek-fallback dispatch logic
in app.modules.brain.llm_provider (llm_chat / llm_stream).
"""
from unittest.mock import AsyncMock, patch

import pytest

from app.modules.brain import llm_provider


@pytest.mark.asyncio
async def test_llm_chat_uses_primary_provider_when_it_succeeds():
    with (
        patch.object(llm_provider.settings, "llm_provider", "anthropic"),
        patch.object(llm_provider.settings, "llm_fallback_provider", "deepseek"),
        patch.object(llm_provider.settings, "anthropic_api_key", "test-key"),
        patch.object(llm_provider, "_anthropic_chat", new_callable=AsyncMock) as mock_anthropic,
        patch.object(llm_provider, "_deepseek_chat", new_callable=AsyncMock) as mock_deepseek,
    ):
        mock_anthropic.return_value = "hello from anthropic"
        result = await llm_provider.llm_chat([{"role": "user", "content": "hi"}])
        assert result == "hello from anthropic"
        mock_anthropic.assert_awaited_once()
        mock_deepseek.assert_not_called()


@pytest.mark.asyncio
async def test_llm_chat_falls_back_to_deepseek_when_primary_raises():
    with (
        patch.object(llm_provider.settings, "llm_provider", "anthropic"),
        patch.object(llm_provider.settings, "llm_fallback_provider", "deepseek"),
        patch.object(llm_provider.settings, "anthropic_api_key", "test-key"),
        patch.object(llm_provider.settings, "deepseek_api_key", "test-key"),
        patch.object(llm_provider, "_anthropic_chat", new_callable=AsyncMock) as mock_anthropic,
        patch.object(llm_provider, "_deepseek_chat", new_callable=AsyncMock) as mock_deepseek,
    ):
        mock_anthropic.side_effect = RuntimeError("connection error")
        mock_deepseek.return_value = "hello from deepseek"
        result = await llm_provider.llm_chat([{"role": "user", "content": "hi"}])
        assert result == "hello from deepseek"
        mock_anthropic.assert_awaited_once()
        mock_deepseek.assert_awaited_once()


@pytest.mark.asyncio
async def test_llm_chat_reraises_when_no_fallback_configured():
    with (
        patch.object(llm_provider.settings, "llm_provider", "anthropic"),
        patch.object(llm_provider.settings, "llm_fallback_provider", ""),
        patch.object(llm_provider.settings, "anthropic_api_key", "test-key"),
        patch.object(llm_provider, "_anthropic_chat", new_callable=AsyncMock) as mock_anthropic,
        patch.object(llm_provider, "_deepseek_chat", new_callable=AsyncMock) as mock_deepseek,
    ):
        mock_anthropic.side_effect = RuntimeError("connection error")
        with pytest.raises(RuntimeError, match="connection error"):
            await llm_provider.llm_chat([{"role": "user", "content": "hi"}])
        mock_deepseek.assert_not_called()


@pytest.mark.asyncio
async def test_llm_chat_reraises_when_fallback_equals_primary():
    with (
        patch.object(llm_provider.settings, "llm_provider", "anthropic"),
        patch.object(llm_provider.settings, "llm_fallback_provider", "anthropic"),
        patch.object(llm_provider.settings, "anthropic_api_key", "test-key"),
        patch.object(llm_provider, "_anthropic_chat", new_callable=AsyncMock) as mock_anthropic,
    ):
        mock_anthropic.side_effect = RuntimeError("boom")
        with pytest.raises(RuntimeError, match="boom"):
            await llm_provider.llm_chat([{"role": "user", "content": "hi"}])
        assert mock_anthropic.await_count == 1


async def _fake_stream_ok(*_args, **_kwargs):
    yield "token1 "
    yield "token2"


async def _fake_stream_fail_before_first_token(*_args, **_kwargs):
    raise RuntimeError("connection error")
    yield  # pragma: no cover - unreachable, makes this a generator


async def _fake_stream_fail_after_first_token(*_args, **_kwargs):
    yield "partial "
    raise RuntimeError("stream dropped mid-reply")


@pytest.mark.asyncio
async def test_llm_stream_falls_back_when_primary_fails_before_first_token():
    with (
        patch.object(llm_provider.settings, "llm_provider", "anthropic"),
        patch.object(llm_provider.settings, "llm_fallback_provider", "deepseek"),
        patch.object(llm_provider.settings, "anthropic_api_key", "test-key"),
        patch.object(llm_provider.settings, "deepseek_api_key", "test-key"),
        patch.object(llm_provider, "_anthropic_stream", _fake_stream_fail_before_first_token),
        patch.object(llm_provider, "_deepseek_stream", _fake_stream_ok),
    ):
        chunks = [c async for c in llm_provider.llm_stream([{"role": "user", "content": "hi"}])]
        assert chunks == ["token1 ", "token2"]


@pytest.mark.asyncio
async def test_llm_stream_does_not_fall_back_after_partial_output():
    with (
        patch.object(llm_provider.settings, "llm_provider", "anthropic"),
        patch.object(llm_provider.settings, "llm_fallback_provider", "deepseek"),
        patch.object(llm_provider.settings, "anthropic_api_key", "test-key"),
        patch.object(llm_provider.settings, "deepseek_api_key", "test-key"),
        patch.object(llm_provider, "_anthropic_stream", _fake_stream_fail_after_first_token),
        patch.object(llm_provider, "_deepseek_stream", _fake_stream_ok),
    ):
        chunks = []
        with pytest.raises(RuntimeError, match="stream dropped mid-reply"):
            async for c in llm_provider.llm_stream([{"role": "user", "content": "hi"}]):
                chunks.append(c)
        # Got the partial chunk before the failure, and never fell back to deepseek.
        assert chunks == ["partial "]
