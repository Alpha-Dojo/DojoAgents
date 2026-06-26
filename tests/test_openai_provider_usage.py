import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from dojoagents.agent.providers import OpenAICompatibleProvider


@pytest.mark.asyncio
async def test_openai_provider_non_stream_usage():
    provider = OpenAICompatibleProvider(api_key="test-key", base_url="http://example")
    usage = MagicMock(prompt_tokens=11, completion_tokens=7, total_tokens=18)
    message = MagicMock(content="hello", tool_calls=None, reasoning_content=None, model_extra=None)
    response = MagicMock(choices=[MagicMock(message=message)], usage=usage)

    with patch("openai.AsyncOpenAI") as client_cls:
        client_cls.return_value.chat.completions.create = AsyncMock(return_value=response)
        result = await provider.chat([], [], model="gpt-4.1", stream=False)

    assert result.metadata["usage"]["prompt_tokens"] == 11
    assert result.metadata["usage"]["completion_tokens"] == 7


@pytest.mark.asyncio
async def test_openai_provider_stream_usage():
    provider = OpenAICompatibleProvider(api_key="test-key", base_url="http://example")

    async def _stream():
        chunk_usage = MagicMock(prompt_tokens=20, completion_tokens=5, total_tokens=25)
        delta = MagicMock(content="hi", tool_calls=None, reasoning_content=None, model_extra=None)
        yield MagicMock(choices=[MagicMock(delta=delta)], usage=None)
        yield MagicMock(choices=[MagicMock(delta=MagicMock(content="", tool_calls=None, reasoning_content=None, model_extra=None))], usage=chunk_usage)

    with patch("openai.AsyncOpenAI") as client_cls:
        client_cls.return_value.chat.completions.create = AsyncMock(return_value=_stream())
        deltas: list[str] = []
        result = await provider.chat([], [], model="gpt-4.1", stream=True, stream_callback=deltas.append)

    assert result.metadata["usage"]["prompt_tokens"] == 20
    client_cls.return_value.chat.completions.create.assert_awaited_once()
    assert client_cls.return_value.chat.completions.create.await_args.kwargs["stream_options"] == {"include_usage": True}


@pytest.mark.asyncio
async def test_openai_provider_raises_context_length_exceeded():
    from dojoagents.agent.context_length import ContextLengthExceededError

    provider = OpenAICompatibleProvider(api_key="test-key", base_url="http://example")
    api_error = Exception("Error code: 400 - maximum context length is 1048565 tokens. However, you requested 3037564 tokens")

    with patch("openai.AsyncOpenAI") as client_cls:
        client_cls.return_value.chat.completions.create = AsyncMock(side_effect=api_error)
        with pytest.raises(ContextLengthExceededError) as exc_info:
            await provider.chat([], [], model="gpt-4.1", stream=False)

    assert exc_info.value.max_context == 1048565
    assert exc_info.value.requested_tokens == 3037564
