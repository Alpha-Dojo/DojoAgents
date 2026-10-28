from __future__ import annotations

import logging
import json
from functools import partial
from types import SimpleNamespace
from unittest.mock import AsyncMock

import anyio
import httpx
import openai
import pytest

from dojoagents.agent import providers
from dojoagents.agent.providers import OpenAICompatibleProvider
from dojoagents.agent.telemetry import bind_run_id


@pytest.fixture
def transport_client(monkeypatch):
    clients, requests = [], []
    actual_client = openai.AsyncOpenAI

    def install(handler):
        async def handle(request):
            requests.append(request)
            return await handler(request)

        def create(**kwargs):
            assert kwargs["max_retries"] == 0
            client = actual_client(**kwargs, http_client=httpx.AsyncClient(transport=httpx.MockTransport(handle)))
            clients.append(client)
            return client

        monkeypatch.setattr(openai, "AsyncOpenAI", create)
        return requests, clients

    return install


@pytest.fixture
def retry_sleep(monkeypatch):
    sleep = AsyncMock()
    monkeypatch.setattr(providers.anyio, "sleep", sleep)
    return sleep


def completion():
    return httpx.Response(200, json={"id": "chat-test", "choices": [{"finish_reason": "stop", "message": {"role": "assistant", "content": "done"}}]})


@pytest.mark.anyio
@pytest.mark.parametrize("failure", ["connect_timeout", "connect_error", 408, 409, 429, 500, 503])
async def test_owned_retries_recover_and_correlate_without_sdk_retries(transport_client, retry_sleep, caplog, failure):
    count = 0

    async def handler(request):
        nonlocal count
        count += 1
        if count == 1:
            if failure == "connect_timeout":
                raise httpx.ConnectTimeout("private-request-body", request=request)
            if failure == "connect_error":
                raise httpx.ConnectError("private-request-body", request=request)
            return httpx.Response(failure, json={"error": {"message": "private-request-body"}})
        return completion()

    requests, clients = transport_client(handler)
    provider = OpenAICompatibleProvider(api_key="private-test-key", max_retries=2)
    provider.name = "qwen"
    with caplog.at_level(logging.INFO, logger=providers.LOGGER.name), bind_run_id("canonical-run"):
        result = await provider.chat([], [], model="test-model", metadata={"_dojo_request": SimpleNamespace(session_id="session-test")})
    assert result.content == "done" and len(requests) == 2
    assert [r.headers["x-stainless-retry-count"] for r in requests] == ["0", "0"]
    assert clients[0].is_closed()
    retry_sleep.assert_awaited_once()
    records = [r.llm_request for r in caplog.records if hasattr(r, "llm_request")]
    assert len({r["call_id"] for r in records}) == 1
    assert all(r["run_id"] == "canonical-run" and r["session_id"] == "session-test" for r in records)
    assert [r["attempt"] for r in records if r["event"] == "llm_request_attempt"] == [1, 2]
    assert next(r for r in records if r["event"] == "llm_request_retry")["next_attempt"] == 2
    assert records[-1]["event"] == "llm_request_end" and records[-1]["outcome"] == "succeeded"
    assert "private-test-key" not in caplog.text and "private-request-body" not in caplog.text


@pytest.mark.anyio
@pytest.mark.parametrize("retries", [0, 2])
async def test_exhaustion_closes_client_and_preserves_original_exception(transport_client, retry_sleep, caplog, retries):
    async def handler(request):
        raise httpx.ConnectTimeout("timeout", request=request)

    requests, clients = transport_client(handler)
    with caplog.at_level(logging.INFO, logger=providers.LOGGER.name):
        with pytest.raises(openai.APITimeoutError):
            await OpenAICompatibleProvider(api_key="test-key", max_retries=retries).chat([], [], model="test-model")
    assert len(requests) == retries + 1
    assert retry_sleep.await_count == retries
    assert all(client.is_closed() for client in clients)
    end = next(r.llm_request for r in reversed(caplog.records) if hasattr(r, "llm_request") and r.llm_request["event"] == "llm_request_end")
    assert end["attempt"] == retries + 1 and end["outcome"] == "failed"
    assert end["error_type"] == "APITimeoutError"


@pytest.mark.anyio
@pytest.mark.parametrize(
    "status,headers,attempts", [(400, {}, 1), (401, {}, 1), (403, {}, 1), (422, {}, 1), (503, {"x-should-retry": "false"}, 1), (400, {"x-should-retry": "true"}, 3)]
)
async def test_http_retry_boundary(transport_client, retry_sleep, status, headers, attempts):
    async def handler(request):
        return httpx.Response(status, headers=headers, json={"error": {"message": "denied"}})

    requests, clients = transport_client(handler)
    with pytest.raises(openai.APIStatusError):
        await OpenAICompatibleProvider(api_key="test-key", max_retries=2).chat([], [], model="test-model")
    assert len(requests) == attempts and retry_sleep.await_count == attempts - 1
    assert all(client.is_closed() for client in clients)


@pytest.mark.anyio
@pytest.mark.parametrize("headers,delay", [({"retry-after-ms": "1250"}, 1.25), ({"retry-after": "2.5"}, 2.5), ({"retry-after": "nan"}, None)])
async def test_retry_after_and_bounded_backoff(transport_client, retry_sleep, headers, delay):
    async def handler(request):
        return httpx.Response(429, headers=headers, json={"error": {"message": "rate limited"}})

    transport_client(handler)
    with pytest.raises(openai.RateLimitError):
        await OpenAICompatibleProvider(api_key="test-key", max_retries=1).chat([], [], model="test-model")
    waited = retry_sleep.await_args.args[0]
    assert waited == delay if delay is not None else 0.375 <= waited <= 0.5


@pytest.mark.anyio
async def test_cancellation_during_backoff_stops_attempts_and_closes_client(transport_client, monkeypatch, caplog):
    async def handler(request):
        raise httpx.ConnectTimeout("timeout", request=request)

    sleeping = anyio.Event()

    async def wait(_delay):
        sleeping.set()
        await anyio.sleep_forever()

    monkeypatch.setattr(providers.anyio, "sleep", wait)
    requests, clients = transport_client(handler)
    with caplog.at_level(logging.INFO, logger=providers.LOGGER.name):
        async with anyio.create_task_group() as group:
            group.start_soon(partial(OpenAICompatibleProvider(api_key="test-key").chat, [], [], model="test-model"))
            await sleeping.wait()
            group.cancel_scope.cancel()
    assert len(requests) == 1 and clients[0].is_closed()
    assert any(getattr(r, "llm_request", {}).get("outcome") == "cancelled" for r in caplog.records)


@pytest.mark.anyio
@pytest.mark.parametrize(
    "delta",
    [{"content": "partial"}, {"reasoning_content": "thinking"}, {"tool_calls": [{"index": 0, "id": "call-1", "type": "function", "function": {"name": "tool", "arguments": "{"}}]}],
)
async def test_interrupted_stream_never_replays(transport_client, retry_sleep, caplog, delta):
    class BrokenStream(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield ("data: " + json.dumps({"id": "chat-test", "choices": [{"index": 0, "delta": delta}]}) + "\n\n").encode()
            raise httpx.ReadError("stream interrupted")

        async def aclose(self):
            pass

    async def handler(request):
        return httpx.Response(200, headers={"content-type": "text/event-stream"}, stream=BrokenStream())

    requests, clients = transport_client(handler)
    with caplog.at_level(logging.INFO, logger=providers.LOGGER.name):
        with pytest.raises(httpx.ReadError):
            await OpenAICompatibleProvider(api_key="test-key", max_retries=2).chat([], [], model="test-model", stream=True, stream_callback=lambda _text: None)
    assert len(requests) == 1 and clients[0].is_closed()
    retry_sleep.assert_not_awaited()
    assert any(getattr(r, "llm_request", {}).get("stream_opened") and r.llm_request.get("outcome") == "failed" for r in caplog.records)


@pytest.mark.anyio
async def test_cancellation_during_http_request_is_not_retried(transport_client, retry_sleep, caplog):
    started = anyio.Event()

    async def handler(request):
        started.set()
        await anyio.sleep_forever()

    requests, clients = transport_client(handler)
    with caplog.at_level(logging.INFO, logger=providers.LOGGER.name):
        async with anyio.create_task_group() as group:
            group.start_soon(partial(OpenAICompatibleProvider(api_key="test-key").chat, [], [], model="test-model"))
            await started.wait()
            group.cancel_scope.cancel()
    assert len(requests) == 1 and clients[0].is_closed()
    retry_sleep.assert_not_awaited()
    assert any(getattr(record, "llm_request", {}).get("outcome") == "cancelled" for record in caplog.records)


@pytest.mark.anyio
async def test_concurrent_requests_keep_separate_attempt_counters(transport_client, retry_sleep, caplog):
    counts = {}

    async def handler(request):
        model = json.loads(request.content)["model"]
        counts[model] = counts.get(model, 0) + 1
        return httpx.Response(503, json={"error": {"message": "busy"}}) if counts[model] == 1 else completion()

    requests, clients = transport_client(handler)
    provider = OpenAICompatibleProvider(api_key="test-key", max_retries=1)
    with caplog.at_level(logging.INFO, logger=providers.LOGGER.name):
        async with anyio.create_task_group() as group:
            for model in ("model-a", "model-b"):
                group.start_soon(partial(provider.chat, [], [], model=model))
    assert len(requests) == 4 and len(clients) == 2 and all(client.is_closed() for client in clients)
    attempts = [record.llm_request for record in caplog.records if getattr(record, "llm_request", {}).get("event") == "llm_request_attempt"]
    assert len({event["call_id"] for event in attempts}) == 2
    for model in ("model-a", "model-b"):
        assert [event["attempt"] for event in attempts if event["model"] == model] == [1, 2]


@pytest.mark.anyio
@pytest.mark.parametrize("value", ["Wed, 21 Oct 999999999999999999999 07:28:00 GMT", "not-a-date", "-10"])
async def test_invalid_retry_after_does_not_replace_the_provider_error(transport_client, retry_sleep, value):
    async def handler(request):
        return httpx.Response(429, headers={"Retry-After": value}, json={"error": {"message": "limited"}})

    requests, _clients = transport_client(handler)
    with pytest.raises(openai.RateLimitError):
        await OpenAICompatibleProvider(api_key="test-key", max_retries=1).chat([], [], model="test-model")
    assert len(requests) == 2
    assert 0.375 <= retry_sleep.await_args.args[0] <= 0.5


def test_http_date_retry_after_and_backoff_cap(monkeypatch):
    monkeypatch.setattr(providers.time, "time", lambda: 1700000000)
    response = httpx.Response(429, request=httpx.Request("POST", "https://example.test"), headers={"Retry-After": "Tue, 14 Nov 2023 22:13:22 GMT"})
    error = openai.RateLimitError("limited", response=response, body=None)
    assert providers._model_retry_delay(error, 1) == 2
    assert 6 <= providers._model_retry_delay(RuntimeError(), 10000) <= 8


@pytest.mark.anyio
async def test_long_retry_after_stops_without_retrying_earlier(transport_client, retry_sleep, caplog):
    async def handler(request):
        return httpx.Response(429, headers={"Retry-After": "61"}, json={"error": {"message": "limited"}})

    requests, clients = transport_client(handler)
    with caplog.at_level(logging.INFO, logger=providers.LOGGER.name):
        with pytest.raises(openai.RateLimitError):
            await OpenAICompatibleProvider(api_key="test-key", max_retries=2).chat([], [], model="test-model")
    assert len(requests) == 1 and clients[0].is_closed()
    retry_sleep.assert_not_awaited()
    end = next(record.llm_request for record in reversed(caplog.records) if hasattr(record, "llm_request") and record.llm_request["event"] == "llm_request_end")
    assert end["stop_reason"] == "retry_after_exceeds_limit" and end["outcome"] == "failed"
