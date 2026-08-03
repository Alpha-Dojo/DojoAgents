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
async def test_openai_provider_builds_minimal_compatible_stream_request() -> None:
    provider = OpenAICompatibleProvider(
        api_key="test-key",
        base_url="https://api.example.com/v1",
        max_tokens=8192,
    )
    messages = [{"role": "user", "content": "分析市场"}]
    tools = [
        {
            "name": "market.quote",
            "description": "查询行情",
            "parameters": {"type": "object", "properties": {}},
        }
    ]

    async def _stream():
        yield MagicMock(
            choices=[
                MagicMock(
                    delta=MagicMock(
                        content="完成",
                        tool_calls=None,
                        reasoning_content=None,
                        reasoning=None,
                        model_extra=None,
                    )
                )
            ],
            usage=None,
        )

    with patch("openai.AsyncOpenAI") as client_cls:
        client_cls.return_value.chat.completions.create = AsyncMock(return_value=_stream())
        await provider.chat(
            messages,
            tools,
            model="Example-Model",
            stream=True,
            stream_callback=lambda _: None,
        )

    kwargs = client_cls.return_value.chat.completions.create.await_args.kwargs
    assert kwargs == {
        "model": "Example-Model",
        "messages": messages,
        "stream": True,
        "stream_options": {"include_usage": True},
        "max_tokens": 8192,
        "tools": [{"type": "function", "function": tools[0]}],
    }
    for forbidden_key in (
        "reasoning_effort",
        "reasoning",
        "thinking",
        "temperature",
        "prompt_cache_key",
        "extra_body",
    ):
        assert forbidden_key not in kwargs


@pytest.mark.asyncio
async def test_model_router_prefixes_author_without_double_prefixing() -> None:
    provider = OpenAICompatibleProvider(
        api_key="test-key",
        base_url="https://openrouter.ai/api/v1",
        author="z-ai",
    )
    provider.name = "model-router"
    response = MagicMock(
        choices=[
            MagicMock(
                message=MagicMock(
                    content="ok",
                    tool_calls=None,
                    reasoning_content=None,
                    reasoning=None,
                    model_extra=None,
                )
            )
        ],
        usage=None,
    )

    with patch("openai.AsyncOpenAI") as client_cls:
        client_cls.return_value.chat.completions.create = AsyncMock(return_value=response)
        await provider.chat([], [], model="glm-5.2", stream=False)
        first_model = client_cls.return_value.chat.completions.create.await_args.kwargs["model"]
        await provider.chat([], [], model="z-ai/glm-5.2", stream=False)
        second_model = client_cls.return_value.chat.completions.create.await_args.kwargs["model"]

    assert first_model == "z-ai/glm-5.2"
    assert second_model == "z-ai/glm-5.2"


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
async def test_openai_provider_preserves_tool_call_metadata_stream() -> None:
    provider = OpenAICompatibleProvider(api_key="test-key", base_url="http://example")

    async def _stream():
        function = MagicMock(
            name="portfolio_read_list",
            arguments='{"market":',
            model_extra={"thoughtSignature": "sig-stream"},
        )
        yield MagicMock(
            choices=[
                MagicMock(
                    delta=MagicMock(
                        content="",
                        tool_calls=[
                            MagicMock(
                                index=0,
                                id="call-stream",
                                function=function,
                                model_extra={"providerTag": "gemini"},
                            )
                        ],
                        reasoning_content=None,
                        reasoning=None,
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
                        tool_calls=[
                            MagicMock(
                                index=0,
                                id=None,
                                function=MagicMock(
                                    name=None,
                                    arguments='"us"}',
                                    model_extra=None,
                                ),
                                model_extra=None,
                            )
                        ],
                        reasoning_content=None,
                        reasoning=None,
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
            model="gpt-4.1",
            stream=True,
            stream_callback=lambda _text: None,
        )

    tool_call = result.tool_calls[0]
    assert tool_call.arguments == {"market": "us"}
    assert tool_call.metadata["thought_signature"] == "sig-stream"
    assert tool_call.metadata["tool_call_extra"]["providerTag"] == "gemini"


@pytest.mark.asyncio
async def test_openai_provider_parses_reasoning_response_field() -> None:
    provider = OpenAICompatibleProvider(api_key="test-key", base_url="http://example")
    message = MagicMock(
        content="最终答案",
        tool_calls=None,
        reasoning_content=None,
        reasoning="思考过程",
        model_extra=None,
    )
    response = MagicMock(choices=[MagicMock(message=message)], usage=None)

    with patch("openai.AsyncOpenAI") as client_cls:
        client_cls.return_value.chat.completions.create = AsyncMock(return_value=response)
        result = await provider.chat([], [], model="DeepSeek-V4-Flash", stream=False)

    assert result.content == "最终答案"
    assert result.metadata["reasoning_content"] == "思考过程"
