import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from dojoagents.agent.providers import (
    OpenAICompatibleProvider,
    _redact_provider_metadata,
)


def test_provider_log_redaction_removes_image_data() -> None:
    value = {
        "content": [
            {
                "type": "image_url",
                "image_url": {"url": "data:image/png;base64,c2VjcmV0"},
            }
        ]
    }
    redacted = _redact_provider_metadata(value)
    serialized = str(redacted)
    assert "c2VjcmV0" not in serialized
    assert "[image-data mime=image/png encoded_chars=8]" in serialized


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
async def test_openai_provider_adds_configured_extra_headers():
    provider = OpenAICompatibleProvider(
        api_key="test-key",
        base_url="http://example",
        extra_headers={"X-Tenant-ID": "tenant-42"},
    )
    message = MagicMock(content="hello", tool_calls=None, reasoning_content=None, model_extra=None)
    response = MagicMock(choices=[MagicMock(message=message)], usage=None)

    with patch("openai.AsyncOpenAI") as client_cls:
        client_cls.return_value.chat.completions.create = AsyncMock(return_value=response)
        await provider.chat([], [], model="gpt-4.1", stream=False)

    assert client_cls.call_args.kwargs["default_headers"] == {"X-Tenant-ID": "tenant-42"}


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
async def test_openai_provider_streams_reasoning_before_content():
    provider = OpenAICompatibleProvider(api_key="test-key", base_url="http://example")
    order: list[tuple[str, str]] = []
    event_sink = MagicMock()
    event_sink.thinking_start.side_effect = lambda: order.append(("think_start", ""))
    event_sink.thinking_delta.side_effect = lambda text: order.append(("think_delta", text))
    event_sink.thinking_end.side_effect = lambda: order.append(("think_end", ""))

    async def _stream():
        yield MagicMock(
            choices=[
                MagicMock(
                    delta=MagicMock(
                        content="",
                        tool_calls=None,
                        reasoning_content="think ",
                        model_extra=None,
                    )
                )
            ],
            usage=None,
        )
        yield MagicMock(
            choices=[
                MagicMock(
                    delta=MagicMock(
                        content="",
                        tool_calls=None,
                        reasoning_content="first",
                        model_extra=None,
                    )
                )
            ],
            usage=None,
        )
        yield MagicMock(
            choices=[
                MagicMock(
                    delta=MagicMock(
                        content="answer",
                        tool_calls=None,
                        reasoning_content=None,
                        model_extra=None,
                    )
                )
            ],
            usage=None,
        )

    with patch("openai.AsyncOpenAI") as client_cls:
        client_cls.return_value.chat.completions.create = AsyncMock(return_value=_stream())
        result = await provider.chat(
            [],
            [],
            model="qwen3.7-plus",
            stream=True,
            stream_callback=lambda text: order.append(("content", text)),
            metadata={"_dojo_event_sink": event_sink},
        )

    assert order == [
        ("think_start", ""),
        ("think_delta", "think "),
        ("think_delta", "first"),
        ("think_end", ""),
        ("content", "answer"),
    ]
    assert result.metadata["reasoning_content"] == "think first"
    assert result.metadata["reasoning_streamed"] is True


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


@pytest.mark.asyncio
async def test_openai_provider_preserves_tool_call_metadata_non_stream() -> None:
    provider = OpenAICompatibleProvider(api_key="test-key", base_url="http://example")
    function = MagicMock(name="portfolio_read_list", arguments='{"market":"us"}', model_extra={"thoughtSignature": "sig-1"})
    tool_call = MagicMock(id="call-1", function=function, model_extra={"providerTag": "gemini"})
    message = MagicMock(content="", tool_calls=[tool_call], reasoning_content=None, model_extra=None)
    response = MagicMock(choices=[MagicMock(message=message)], usage=None)

    with patch("openai.AsyncOpenAI") as client_cls:
        client_cls.return_value.chat.completions.create = AsyncMock(return_value=response)
        result = await provider.chat([], [], model="gpt-4.1", stream=False)

    assert result.tool_calls[0].metadata["thought_signature"] == "sig-1"
    assert result.tool_calls[0].metadata["tool_call_extra"]["providerTag"] == "gemini"


@pytest.mark.asyncio
async def test_openrouter_provider_restores_selected_model_author_prefix():
    from dojoagents.agent.providers import OpenAICompatibleProvider

    provider = OpenAICompatibleProvider(
        api_key="test-key",
        base_url="https://openrouter.ai/api/v1",
        author="z-ai",
    )
    provider.name = "openrouter"
    response = MagicMock()
    response.choices = [MagicMock(message=MagicMock(content="ok", tool_calls=[]))]
    response.usage = None

    with patch("openai.AsyncOpenAI") as client_cls:
        client_cls.return_value.chat.completions.create = AsyncMock(return_value=response)
        await provider.chat([], [], model="glm-5.2")

    assert client_cls.return_value.chat.completions.create.await_args.kwargs["model"] == "z-ai/glm-5.2"


@pytest.mark.asyncio
async def test_orcarouter_provider_restores_selected_model_author_prefix():
    from dojoagents.agent.providers import OpenAICompatibleProvider

    provider = OpenAICompatibleProvider(
        api_key="test-key",
        base_url="https://api.orcarouter.ai/v1",
        author="openai",
    )
    provider.name = "orcarouter"
    response = MagicMock()
    response.choices = [MagicMock(message=MagicMock(content="ok", tool_calls=[]))]
    response.usage = None

    with patch("openai.AsyncOpenAI") as client_cls:
        client_cls.return_value.chat.completions.create = AsyncMock(return_value=response)
        await provider.chat([], [], model="gpt-5.5")

    assert client_cls.return_value.chat.completions.create.await_args.kwargs["model"] == "openai/gpt-5.5"
