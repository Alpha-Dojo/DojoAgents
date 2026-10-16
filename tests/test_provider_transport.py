from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import anyio
import pytest

from dojoagents.agent.provider_response import OpenAIResponseAdapter
from dojoagents.agent.provider_transport import OpenAITransport, OpenAITransportResponse


def _client_with_create(create):
    client = SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(
                create=create,
                with_raw_response=SimpleNamespace(create=AsyncMock()),
            )
        ),
        close=AsyncMock(),
    )
    return client


@pytest.mark.anyio
async def test_transport_keeps_client_alive_until_response_is_closed() -> None:
    sdk_response = SimpleNamespace(choices=[], usage=None)
    create = AsyncMock(return_value=sdk_response)
    client = _client_with_create(create)

    with patch("openai.AsyncOpenAI", return_value=client):
        response = await OpenAITransport(api_key="key").send(
            {"model": "model-a", "messages": [], "stream": False}
        )

    client.close.assert_not_awaited()
    assert response.value is sdk_response

    await response.aclose()
    await response.aclose()

    client.close.assert_awaited_once()


@pytest.mark.anyio
async def test_transport_closes_client_when_send_fails() -> None:
    create = AsyncMock(side_effect=RuntimeError("send failed"))
    client = _client_with_create(create)

    with patch("openai.AsyncOpenAI", return_value=client):
        with pytest.raises(RuntimeError, match="send failed"):
            await OpenAITransport(api_key="key").send(
                {"model": "model-a", "messages": [], "stream": False}
            )

    client.close.assert_awaited_once()


@pytest.mark.anyio
async def test_transport_closes_client_when_payload_encoding_fails() -> None:
    client = _client_with_create(AsyncMock())

    with patch("openai.AsyncOpenAI", return_value=client):
        with pytest.raises(ValueError):
            await OpenAITransport(api_key="key").send(
                {
                    "model": "model-a",
                    "messages": [],
                    "stream": False,
                    "extra_body": "not-a-mapping",
                }
            )

    client.close.assert_awaited_once()


@pytest.mark.anyio
async def test_response_close_failure_does_not_skip_client_close() -> None:
    stream = SimpleNamespace(aclose=AsyncMock(side_effect=RuntimeError("close failed")))
    client = SimpleNamespace(close=AsyncMock())
    response = OpenAITransportResponse(
        value=stream,
        client=client,
        is_stream=True,
    )

    await response.aclose()

    stream.aclose.assert_awaited_once()
    client.close.assert_awaited_once()


@pytest.mark.anyio
async def test_transport_maps_logical_token_field_for_legacy_sdk() -> None:
    captured: dict = {}

    class LegacyCreate:
        async def __call__(
            self,
            *,
            model,
            messages,
            stream,
            extra_body=None,
        ):
            captured.update(
                model=model,
                messages=messages,
                stream=stream,
                extra_body=extra_body,
            )
            return SimpleNamespace(choices=[], usage=None)

    client = _client_with_create(LegacyCreate())
    with patch("openai.AsyncOpenAI", return_value=client):
        response = await OpenAITransport(api_key="key").send(
            {
                "model": "model-a",
                "messages": [],
                "stream": False,
                "max_completion_tokens": 123,
                "extra_body": {"enable_thinking": False},
            }
        )

    await response.aclose()

    assert captured["extra_body"] == {
        "enable_thinking": False,
        "max_completion_tokens": 123,
    }


@pytest.mark.anyio
async def test_direct_token_field_wins_over_duplicate_extra_body_value() -> None:
    create = AsyncMock(return_value=SimpleNamespace(choices=[], usage=None))
    client = _client_with_create(create)

    with patch("openai.AsyncOpenAI", return_value=client):
        response = await OpenAITransport(api_key="key").send(
            {
                "model": "model-a",
                "messages": [],
                "stream": False,
                "max_completion_tokens": 123,
                "extra_body": {
                    "max_completion_tokens": 999,
                    "enable_thinking": False,
                },
            }
        )

    await response.aclose()

    assert create.await_args.kwargs["max_completion_tokens"] == 123
    assert create.await_args.kwargs["extra_body"] == {
        "enable_thinking": False,
    }


@pytest.mark.anyio
async def test_stream_cancellation_closes_stream_and_client() -> None:
    started = anyio.Event()
    stream_closed = anyio.Event()

    class BlockingStream:
        def __aiter__(self):
            return self

        async def __anext__(self):
            started.set()
            await anyio.sleep_forever()

        async def aclose(self):
            stream_closed.set()

    stream = BlockingStream()
    client = _client_with_create(AsyncMock(return_value=stream))
    transport = OpenAITransport(api_key="key")
    adapter = OpenAIResponseAdapter()

    async def consume() -> None:
        response = await transport.send(
            {"model": "model-a", "messages": [], "stream": True}
        )
        await adapter.decode(response, provider_name="custom")

    with patch("openai.AsyncOpenAI", return_value=client):
        async with anyio.create_task_group() as task_group:
            task_group.start_soon(consume)
            await started.wait()
            task_group.cancel_scope.cancel()

    assert stream_closed.is_set()
    client.close.assert_awaited_once()
