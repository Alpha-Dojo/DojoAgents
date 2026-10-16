from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from dojoagents.agent.provider_response import OpenAIResponseAdapter
from dojoagents.agent.provider_transport import OpenAITransportResponse


@pytest.mark.anyio
async def test_normal_response_decodes_finish_reason_usage_and_tool_metadata() -> None:
    function = SimpleNamespace(
        name="quote",
        arguments='{"symbol":"AAPL"}',
        model_extra={"thoughtSignature": "signature-1"},
    )
    tool_call = SimpleNamespace(
        id="call-1",
        function=function,
        model_extra={"providerTag": "gateway"},
    )
    message = SimpleNamespace(
        content="done",
        tool_calls=[tool_call],
        reasoning_content="reasoning",
        model_extra=None,
    )
    choice = SimpleNamespace(message=message, finish_reason="tool_calls")
    usage = SimpleNamespace(
        prompt_tokens=4,
        completion_tokens=2,
        total_tokens=6,
        prompt_tokens_details=None,
        completion_tokens_details=None,
    )
    client = SimpleNamespace(close=AsyncMock())
    response = OpenAITransportResponse(
        value=SimpleNamespace(choices=[choice], usage=usage),
        client=client,
    )

    result = await OpenAIResponseAdapter().decode(
        response,
        provider_name="custom",
    )

    assert result.content == "done"
    assert result.metadata["finish_reason"] == "tool_calls"
    assert result.metadata["usage"]["total_tokens"] == 6
    assert result.tool_calls[0].name == "quote"
    assert result.tool_calls[0].metadata["thought_signature"] == "signature-1"
    client.close.assert_awaited_once()


@pytest.mark.anyio
async def test_stream_decodes_without_callback_and_closes_lifecycle() -> None:
    class Stream:
        def __init__(self) -> None:
            self.closed = False

        async def __aiter__(self):
            yield SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        delta=SimpleNamespace(
                            content="hello",
                            reasoning_content=None,
                            model_extra=None,
                            tool_calls=None,
                        ),
                        finish_reason="stop",
                    )
                ],
                usage=None,
            )

        async def aclose(self) -> None:
            self.closed = True

    stream = Stream()
    client = SimpleNamespace(close=AsyncMock())
    response = OpenAITransportResponse(
        value=stream,
        client=client,
        is_stream=True,
    )

    result = await OpenAIResponseAdapter().decode(
        response,
        provider_name="custom",
    )

    assert result.content == "hello"
    assert result.metadata["finish_reason"] == "stop"
    assert result.metadata["usage_available"] is False
    assert stream.closed is True
    client.close.assert_awaited_once()
