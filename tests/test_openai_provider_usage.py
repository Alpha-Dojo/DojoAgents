import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import json
import httpx
from openai import APIConnectionError

from dojoagents.agent.providers import (
    OpenAICompatibleProvider,
    _redact_provider_metadata,
)


@pytest.mark.asyncio
async def test_optional_request_settings_preserve_legacy_defaults_and_metadata_extra_body():
    provider = OpenAICompatibleProvider(api_key="test-key", base_url="http://example")
    message = MagicMock(content="hello", tool_calls=None, reasoning_content=None, model_extra=None)
    response = MagicMock(choices=[MagicMock(message=message)], usage=None)
    with patch("openai.AsyncOpenAI") as client_cls:
        client_cls.return_value.chat.completions.create = AsyncMock(return_value=response)
        await provider.chat([], [], model="qwen", metadata={"_dojo_extra_body": {"enable_thinking": False}})
        assert "max_retries" not in client_cls.call_args.kwargs
        assert "timeout" not in client_cls.call_args.kwargs
        assert client_cls.return_value.chat.completions.create.await_args.kwargs["extra_body"] == {"enable_thinking": False}
        with pytest.raises(ValueError):
            await provider.chat([], [], model="qwen", request_options={"extra_body": {"model": "other"}})


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [200, 400, 429, 503])
async def test_raw_receipt_preserves_finish_reason_usage_and_http_errors_without_retry(monkeypatch, status):
    requests = []
    body = {
        "choices": [{"finish_reason": "length", "message": {"content": "answer"}}],
        "usage": {"prompt_tokens": 11, "completion_tokens": 7},
        "echo": "secret-key https://bucket/video?X-Amz-Signature=secret-signature",
    }

    def handler(request):
        requests.append(request)
        payload = json.loads(request.content)
        assert payload["enable_thinking"] is False
        assert payload["response_format"] == {"type": "json_object"}
        assert payload["max_completion_tokens"] == 4096
        assert payload["temperature"] == 0.1
        assert payload["messages"][0]["content"][0]["type"] == "video_url"
        return httpx.Response(status, json=body)

    actual_client = httpx.AsyncClient

    class MockClient(actual_client):
        def __init__(self, **kwargs):
            super().__init__(transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", MockClient)
    provider = OpenAICompatibleProvider(
        api_key="secret-key",
        base_url="https://example/v1",
        max_retries=0,
        timeout=3,
        max_response_bytes=4096,
    )
    result = await provider.chat(
        [
            {
                "role": "user",
                "content": [
                    {
                        "type": "video_url",
                        "video_url": {"url": "https://bucket/video?X-Amz-Signature=secret-signature"},
                    }
                ],
            }
        ],
        [],
        model="qwen",
        include_raw_response=True,
        request_options={
            "temperature": 0.1,
            "max_completion_tokens": 4096,
            "response_format": {"type": "json_object"},
            "extra_body": {"enable_thinking": False},
        },
    )
    assert len(requests) == 1
    assert result.metadata["raw_response"]["http_status"] == status
    raw = result.metadata["raw_response"]["response"]
    assert raw["choices"][0]["finish_reason"] == "length"
    assert raw["usage"] == body["usage"]
    assert "secret-key" not in json.dumps(raw)
    assert "secret-signature" not in json.dumps(raw)


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["invalid_json", "network", "oversize", "oversize_error"])
async def test_raw_transport_keeps_invalid_receipts_and_bounds_unknown_failures(monkeypatch, mode):
    calls = []
    closed = []

    class Chunks(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield b"x" * 64
            yield b"y" * 64

        async def aclose(self):
            closed.append(True)

    def handler(request):
        calls.append(request)
        if mode == "network":
            raise httpx.ReadTimeout("submission outcome unknown", request=request)
        if mode.startswith("oversize"):
            return httpx.Response(503 if mode.endswith("error") else 200, stream=Chunks())
        return httpx.Response(200, content=b"{bad-json")

    actual_client = httpx.AsyncClient

    class MockClient(actual_client):
        def __init__(self, **kwargs):
            super().__init__(transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", MockClient)
    provider = OpenAICompatibleProvider(
        api_key="key",
        base_url="https://example/v1",
        max_retries=0,
        max_response_bytes=100,
    )
    if mode == "invalid_json":
        result = await provider.chat([], [], model="qwen", include_raw_response=True)
        assert result.metadata["raw_response"]["response"] == {"_unparsed_response": "{bad-json"}
    else:
        with pytest.raises((APIConnectionError, ValueError)):
            await provider.chat([], [], model="qwen", include_raw_response=True)
    assert len(calls) == 1
    if mode.startswith("oversize"):
        assert closed


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


@pytest.mark.anyio
async def test_openai_provider_strips_only_top_level_message_name_and_omits_empty_tools():
    provider = OpenAICompatibleProvider(api_key="test-key", base_url="http://example")
    messages = [
        {
            "role": "assistant",
            "name": "research-agent",
            "content": "",
            "tool_calls": [
                {
                    "id": "call-1",
                    "type": "function",
                    "function": {"name": "lookup_quote", "arguments": "{}"},
                }
            ],
        }
    ]
    response_message = MagicMock(content="ok", tool_calls=None, reasoning_content=None, model_extra=None)
    response = MagicMock(choices=[MagicMock(message=response_message)], usage=None)

    with patch("openai.AsyncOpenAI") as client_cls:
        client_cls.return_value.chat.completions.create = AsyncMock(return_value=response)
        await provider.chat(messages, [], model="gpt-4.1")

    request = client_cls.return_value.chat.completions.create.await_args.kwargs
    assert "tools" not in request
    assert "name" not in request["messages"][0]
    assert request["messages"][0]["tool_calls"][0]["function"]["name"] == "lookup_quote"
    assert messages[0]["name"] == "research-agent"


@pytest.mark.anyio
async def test_openai_provider_includes_nonempty_tools():
    provider = OpenAICompatibleProvider(api_key="test-key", base_url="http://example")
    response_message = MagicMock(content="ok", tool_calls=None, reasoning_content=None, model_extra=None)
    response = MagicMock(choices=[MagicMock(message=response_message)], usage=None)
    tools = [
        {
            "name": "lookup_quote",
            "description": "Look up a quote",
            "parameters": {"type": "object", "properties": {}},
        }
    ]

    with patch("openai.AsyncOpenAI") as client_cls:
        client_cls.return_value.chat.completions.create = AsyncMock(return_value=response)
        await provider.chat([], tools, model="gpt-4.1")

    assert client_cls.return_value.chat.completions.create.await_args.kwargs["tools"] == [
        {"type": "function", "function": tools[0]}
    ]


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
    event_sink.wait_for_capacity = AsyncMock()
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
