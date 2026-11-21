import json
from types import SimpleNamespace

import anyio
import httpx
import pytest
from openai import APIStatusError
from openai.resources.chat.completions import AsyncCompletions

from dojoagents.agent.providers import OpenAICompatibleProvider, OpenAIStreamError


def frame(choice=None, *, usage=None):
    value = {"choices": [] if choice is None else [{"index": 0, **choice}]}
    if usage is not None:
        value["usage"] = usage
    return ("data: " + json.dumps(value, ensure_ascii=False) + "\r\n\r\n").encode()


class Stream(httpx.AsyncByteStream):
    def __init__(self, wire, chunk_size):
        self.wire = wire
        self.chunk_size = chunk_size
        self.read_started = False
        self.closed = False

    async def __aiter__(self):
        self.read_started = True
        for offset in range(0, len(self.wire), self.chunk_size):
            yield self.wire[offset:offset + self.chunk_size]

    async def aclose(self):
        self.closed = True


def mock_provider(monkeypatch, wire, *, status=200, max_response_bytes=4096, chunk_size=7, content_type="text/event-stream; charset=utf-8"):
    stream = Stream(wire, chunk_size)
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(status, headers={"Content-Type": content_type}, stream=stream)

    client_cls = httpx.AsyncClient

    class MockClient(client_cls):
        def __init__(self, **kwargs):
            super().__init__(transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", MockClient)
    return OpenAICompatibleProvider(
        api_key="test-key", base_url="https://model.invalid/compatible-mode/v1", timeout=120, connect_timeout=60, max_response_bytes=max_response_bytes
    ), requests, stream


@pytest.mark.anyio
@pytest.mark.parametrize("thinking", [True, False])
async def test_collect_chat_stream_keeps_only_translated_text(monkeypatch, thinking):
    usage = {"prompt_tokens": 1, "completion_tokens": 3, "completion_tokens_details": {"reasoning_tokens": 2}, "cost": 0.01, "vendor": {"📈": ["市場"]}}
    wire = (frame({"delta": {"reasoning_content": "private reasoning"}}) if thinking else b"")
    wire += frame({"delta": {"content": '{"title":'}})
    wire += frame({"delta": {"content": '"日本語"}'}, "finish_reason": "stop"})
    wire += b"data: " + json.dumps({"choices": [], "usage": usage}).encode() + b"\n\ndata: [DONE]\n\n"
    provider, requests, stream = mock_provider(monkeypatch, wire)
    metrics = {}
    result = await provider.collect_chat_stream(
        [], model="model", max_content_bytes=100, read_timeout=90, diagnostics=metrics,
        request_options={"max_completion_tokens": 48000, "extra_body": {"enable_thinking": thinking}},
    )
    request, = requests
    assert request.url.path == "/compatible-mode/v1/chat/completions"
    assert request.extensions["timeout"] == {"connect": 60, "read": 90, "write": 120, "pool": 120}
    body = json.loads(request.content)
    assert (body["model"], body["enable_thinking"], body["stream"], body["stream_options"], body["max_completion_tokens"]) == (
        "model", thinking, True, {"include_usage": True}, 48000
    )
    assert stream.closed
    assert json.loads(result.content) == {"title": "日本語"}
    assert metrics["finish_reason"] == "stop"
    assert metrics["http_status"] == 200
    assert metrics["reasoning_chunks"] == int(thinking)
    assert metrics["content_chunks"] == 2
    assert result.metadata["usage"] == usage
    assert "private reasoning" not in str(result.metadata)


@pytest.mark.anyio
@pytest.mark.parametrize(
    "wire,max_response_bytes,max_content_bytes,reason",
    [
        (frame({"delta": {"content": "{}"}, "finish_reason": "stop"}), 4096, 100, "stream_incomplete"),
        (frame({"delta": {"reasoning_content": "thinking"}}) + b"data: [DONE]\n\n", 4096, 100, "stream_incomplete"),
        (frame({"delta": {"content": "{}"}, "finish_reason": "stop"}) + b"data: [DONE]\n", 4096, 100, "stream_incomplete"),
        (b'event: error\ndata: {"error":{"message":"private"}}\n\n', 4096, 100, "stream_provider_error"),
        (frame({"finish_reason": None}), 4096, 100, "stream_invalid_event"),
        (frame({"delta": {"content": "{}"}, "finish_reason": "stop"}) + frame({"delta": {"content": "extra"}}), 4096, 100, "stream_invalid_event"),
        (frame({"delta": {"content": "too much"}}), 4096, 3, "stream_content_too_large"),
        (frame({"delta": {"content": "too much"}}), 20, 100, "stream_response_too_large"),
    ],
)
async def test_collect_chat_stream_rejects_incomplete_or_oversize_responses(monkeypatch, wire, max_response_bytes, max_content_bytes, reason):
    provider, requests, stream = mock_provider(monkeypatch, wire, max_response_bytes=max_response_bytes)
    metrics = {}
    with pytest.raises(OpenAIStreamError, match=f"^{reason}$"):
        await provider.collect_chat_stream([], model="model", max_content_bytes=max_content_bytes, diagnostics=metrics)
    assert metrics["http_status"] == 200
    assert len(requests) == 1 and stream.closed


@pytest.mark.anyio
@pytest.mark.parametrize("status", [200, 400, 504])
async def test_collect_chat_stream_preserves_truncation_and_http_errors(monkeypatch, status):
    wire = frame({"delta": {"content": "{}"}, "finish_reason": "length"}) + b"data: [DONE]\n\n"
    provider, requests, stream = mock_provider(monkeypatch, wire, status=status)
    result = await provider.collect_chat_stream([], model="model", max_content_bytes=100)
    assert result.metadata["http_status"] == status
    if status == 200:
        assert result.metadata["finish_reason"] == "length"
    assert len(requests) == 1 and stream.closed


@pytest.mark.anyio
@pytest.mark.parametrize("finish_reason", ["stop", "content_filter"])
async def test_collect_chat_stream_accepts_azure_filter_frames_without_delta(monkeypatch, finish_reason):
    annotation = {"content_filter_results": {"hate": {"filtered": False}}, "content_filter_offsets": {"check_offset": 2}}
    wire = frame({"delta": {"content": "ok"}}) + frame({"finish_reason": None, **annotation})
    if finish_reason == "stop":
        wire += frame({"delta": {}, "finish_reason": "stop"}) + frame({"delta": None, "finish_reason": None, **annotation})
    else:
        wire += frame({"finish_reason": "content_filter", "content_filter_results": {"hate": {"filtered": True}}})
    provider, requests, stream = mock_provider(monkeypatch, wire + b"data: [DONE]\n\n")

    result = await provider.collect_chat_stream([], model="model", max_content_bytes=100)

    assert result.content == "ok"
    assert result.metadata["finish_reason"] == finish_reason
    assert result.metadata["content_chunks"] == 1
    assert len(requests) == 1 and stream.closed


@pytest.mark.anyio
@pytest.mark.parametrize(
    "usage",
    [
        b'{"prompt_tokens":NaN}',
        b'{"completion_tokens_details":{"reasoning_tokens":Infinity}}',
        b'{"total_tokens":1e999}',
        b'{"prompt_tokens":-1}',
        b'{"completion_tokens_details":{"reasoning_tokens":true}}',
        rb'{"vendor":{"labels":["\ud800"]}}',
        rb'{"vendor":[{"\udc00":"label"}]}',
    ],
)
async def test_collect_chat_stream_rejects_invalid_usage(monkeypatch, usage):
    wire = frame({"delta": {"content": "ok"}, "finish_reason": "stop"})
    wire += b'data: {"choices":[],"usage":' + usage + b'}\n\ndata: [DONE]\n\n'
    provider, requests, stream = mock_provider(monkeypatch, wire)

    with pytest.raises(OpenAIStreamError, match="^stream_invalid_event$"):
        await provider.collect_chat_stream([], model="model", max_content_bytes=100)

    assert len(requests) == 1 and stream.closed


@pytest.mark.anyio
async def test_collect_chat_stream_replaces_previous_diagnostics(monkeypatch):
    diagnostics = {"request_id": "caller-context"}
    terminal = frame({"delta": {"content": "ok"}, "finish_reason": "stop"}) + b"data: [DONE]\n\n"

    with monkeypatch.context() as patches:
        provider, _, _ = mock_provider(patches, frame({"delta": {"reasoning_content": "plan"}}) + terminal)
        await provider.collect_chat_stream([], model="model", max_content_bytes=100, diagnostics=diagnostics)
    assert "first_reasoning_ms" in diagnostics

    with monkeypatch.context() as patches:
        provider, _, _ = mock_provider(patches, terminal)
        result = await provider.collect_chat_stream([], model="model", max_content_bytes=100, diagnostics=diagnostics)
    assert result.metadata["reasoning_chunks"] == 0
    assert "first_reasoning_ms" not in result.metadata
    assert "first_reasoning_ms" not in diagnostics
    assert "request_id" not in result.metadata

    provider, _, _ = mock_provider(monkeypatch, b"gateway timeout", status=504)
    reply = await provider.collect_chat_stream([], model="model", max_content_bytes=100, diagnostics=diagnostics)
    assert reply.metadata == {"http_status": 504}
    assert diagnostics == {"request_id": "caller-context", "http_status": 504}
    assert result.metadata["finish_reason"] == "stop"


@pytest.mark.anyio
@pytest.mark.parametrize("invalid_client", [True, False])
async def test_collect_chat_stream_clears_previous_diagnostics_on_setup_failure(invalid_client):
    diagnostics = {"request_id": "caller-context", "http_status": 200, "finish_reason": "stop", "first_content_ms": 10}
    provider = OpenAICompatibleProvider(
        api_key="test-key", base_url="https://model.invalid:bad-port/v1" if invalid_client else "https://model.invalid/v1", max_response_bytes=4096
    )
    options = None if invalid_client else {"unsupported": True}
    with pytest.raises(httpx.InvalidURL if invalid_client else ValueError):
        await provider.collect_chat_stream([], model="model", max_content_bytes=100, request_options=options, diagnostics=diagnostics)

    assert diagnostics == {"request_id": "caller-context"}


@pytest.mark.anyio
@pytest.mark.parametrize("stream_succeeds", [True, False])
@pytest.mark.parametrize("failed_operation", ["pop", "update"])
async def test_collect_chat_stream_keeps_outcome_when_diagnostics_write_fails(monkeypatch, caplog, stream_succeeds, failed_operation):
    class RejectingDiagnostics(dict):
        def pop(self, *args):
            if failed_operation == "pop":
                raise RuntimeError("private diagnostics value")
            return super().pop(*args)

        def update(self, *args):
            if failed_operation == "update":
                raise RuntimeError("private diagnostics value")
            return super().update(*args)

    wire = frame({"delta": {"content": "ok"}, "finish_reason": "stop"}) + b"data: [DONE]\n\n" if stream_succeeds else b"data: invalid JSON\n\n"
    provider, requests, stream = mock_provider(monkeypatch, wire)
    diagnostics = RejectingDiagnostics()
    clients = []
    make_client = provider._client

    def capture_client(**options):
        client = make_client(**options)
        clients.append(client)
        return client

    monkeypatch.setattr(provider, "_client", capture_client)
    if stream_succeeds:
        result = await provider.collect_chat_stream([], model="model", max_content_bytes=100, diagnostics=diagnostics)
        assert result.content == "ok"
        assert result.metadata["finish_reason"] == "stop"
    else:
        with pytest.raises(OpenAIStreamError, match="^stream_invalid_event$"):
            await provider.collect_chat_stream([], model="model", max_content_bytes=100, diagnostics=diagnostics)

    client, = clients
    assert client.is_closed()
    assert len(requests) == 1 and stream.closed
    assert caplog.messages.count("llm_stream_diagnostics_write_failed error_type=RuntimeError") == 1
    assert "private diagnostics value" not in caplog.text


@pytest.mark.anyio
@pytest.mark.parametrize("deadline", [True, False], ids=["asyncio-timeout", "task-cancel"])
async def test_collect_chat_stream_updates_diagnostics_when_close_is_cancelled(monkeypatch, deadline):
    # Model callers can interrupt the transport with native asyncio cancellation.
    import asyncio

    timeout = asyncio.timeout(None)
    wire = frame({"delta": {"content": "ok"}, "finish_reason": "stop"}) + b"data: [DONE]\n\n"
    provider, requests, stream = mock_provider(monkeypatch, wire)
    diagnostics = {"request_id": "caller-context", "http_status": 503, "first_reasoning_ms": 999, "finish_reason": "length"}
    close_started = False

    async def interrupt_close(_transport):
        nonlocal close_started
        close_started = True
        if deadline:
            timeout.reschedule(asyncio.get_running_loop().time())
        else:
            asyncio.current_task().cancel("caller cancelled")
        await anyio.sleep_forever()

    monkeypatch.setattr(httpx.MockTransport, "aclose", interrupt_close)

    async def collect():
        with pytest.raises(TimeoutError if deadline else asyncio.CancelledError) as error:
            async with timeout:
                await provider.collect_chat_stream([], model="model", max_content_bytes=100, diagnostics=diagnostics)
        if deadline:
            assert timeout.expired()
        else:
            assert error.value.args == ("caller cancelled",)

    async with anyio.create_task_group() as group:
        group.start_soon(collect)

    assert close_started and stream.closed and len(requests) == 1
    assert diagnostics["request_id"] == "caller-context"
    assert diagnostics["http_status"] == 200
    assert diagnostics["finish_reason"] == "stop"
    assert diagnostics["content_chunks"] == 1
    assert "first_reasoning_ms" not in diagnostics


@pytest.mark.anyio
@pytest.mark.parametrize("newline", [b"\r\n", b"\r", b"\n"])
async def test_collect_chat_stream_handles_bom_and_unicode_with_split_line_endings(monkeypatch, newline):
    content = "日本語\u2028中文\u2029한국어\u0085English"
    wire = b"\xef\xbb\xbf" + frame({"delta": {"content": content}, "finish_reason": "stop"}) + b"data: [DONE]\r\n\r\n"
    provider, _, stream = mock_provider(monkeypatch, wire.replace(b"\r\n", newline), chunk_size=1)
    result = await provider.collect_chat_stream([], model="model", max_content_bytes=100)

    assert result.content == content
    assert stream.closed


@pytest.mark.anyio
async def test_collect_chat_stream_returns_http_timeout_without_reading_error_body(monkeypatch):
    provider, requests, stream = mock_provider(monkeypatch, b"oversized gateway error", status=504, max_response_bytes=1)
    diagnostics = {}

    result = await provider.collect_chat_stream([], model="model", max_content_bytes=100, diagnostics=diagnostics)

    assert result.content == ""
    assert result.metadata == diagnostics == {"http_status": 504}
    assert not stream.read_started
    assert len(requests) == 1 and stream.closed


@pytest.mark.anyio
async def test_skip_error_body_works_without_diagnostics(monkeypatch):
    provider, requests, stream = mock_provider(monkeypatch, b"oversized gateway error", status=504, max_response_bytes=1)

    async with provider._client(skip_error_body=True) as client:
        with pytest.raises(APIStatusError) as error:
            async with client.chat.completions.with_streaming_response.create(model="model", messages=[], stream=True):
                pytest.fail("HTTP error should raise before yielding a response")

    assert error.value.status_code == 504
    assert not stream.read_started
    assert len(requests) == 1 and stream.closed


@pytest.mark.anyio
async def test_chat_raw_error_body_is_preserved_with_diagnostics(monkeypatch):
    wire = b'{"error":{"code":"bad_parameter","message":"Rejected test-key"}}'
    provider, requests, stream = mock_provider(monkeypatch, wire, status=400)
    diagnostics = {}
    make_client = provider._client
    monkeypatch.setattr(provider, "_client", lambda: make_client(diagnostics=diagnostics))

    result = await provider.chat([], [], model="model", include_raw_response=True)

    assert diagnostics == {"http_status": 400}
    assert result.metadata["raw_response"] == {
        "http_status": 400,
        "response": {"error": {"code": "bad_parameter", "message": "Rejected <credential omitted>"}},
    }
    assert stream.read_started
    assert len(requests) == 1 and stream.closed


@pytest.mark.anyio
async def test_chat_stream_collects_result_without_callback(monkeypatch):
    wire = frame({"delta": {"reasoning_content": "plan"}})
    wire += frame({"delta": {"content": "Looking "}})
    wire += frame({"delta": {"content": "up"}})
    first_tool_delta = {"index": 0, "id": "call-1", "type": "function", "function": {"name": "lookup", "arguments": '{"symbol":'}}
    last_tool_delta = {"index": 0, "function": {"arguments": '"AAPL"}'}}
    wire += frame({"delta": {"tool_calls": [first_tool_delta]}})
    wire += frame({"delta": {"tool_calls": [last_tool_delta]}, "finish_reason": "tool_calls"})
    usage = {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}
    usage_details = {"prompt_tokens_details": {"cached_tokens": 4}, "completion_tokens_details": {"reasoning_tokens": 2}}
    wire += frame(usage={**usage, **usage_details}) + b"data: [DONE]\n\n"
    provider, requests, stream = mock_provider(monkeypatch, wire)
    tools = [{"name": "lookup", "parameters": {"type": "object", "properties": {"symbol": {"type": "string"}}}}]

    result = await provider.chat([], tools, model="model", stream=True, metadata={"_dojo_request": SimpleNamespace(channel="job")})

    assert result.content == "Looking up"
    assert result.metadata["reasoning_content"] == "plan"
    assert result.metadata["usage"] == {**usage, "cache_read_tokens": 4, "reasoning_tokens": 2}
    tool_call, = result.tool_calls
    assert (tool_call.id, tool_call.name, tool_call.arguments) == ("call-1", "lookup", {"symbol": "AAPL"})
    request, = requests
    assert json.loads(request.content)["stream"] is True
    assert stream.closed


@pytest.mark.anyio
@pytest.mark.parametrize("stream", [True, False])
@pytest.mark.parametrize(
    "usage",
    [
        b'{"prompt_tokens":1e999,"completion_tokens":5}',
        b'{"prompt_tokens":-10,"completion_tokens":5}',
        b'{"prompt_tokens":"unavailable","completion_tokens":5}',
        b'{"prompt_tokens":true,"completion_tokens":5}',
        b'{"prompt_tokens":10,"completion_tokens_details":{"reasoning_tokens":1.5}}',
        b'{"prompt_tokens":10,"prompt_tokens_details":[]}',
    ],
)
async def test_chat_preserves_answer_when_usage_is_malformed(monkeypatch, stream, usage):
    if stream:
        wire = frame({"delta": {"content": "answer"}, "finish_reason": "stop"})
        wire += frame(usage={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15})
        wire += b'data: {"choices":[],"usage":' + usage + b'}\n\ndata: [DONE]\n\n'
    else:
        wire = b'{"choices":[{"message":{"role":"assistant","content":"answer"},"finish_reason":"stop"}],"usage":' + usage + b'}'
    provider, requests, response_stream = mock_provider(monkeypatch, wire, content_type="text/event-stream" if stream else "application/json")

    result = await provider.chat([], [], model="model", stream=stream)

    assert result.content == "answer"
    assert result.metadata["usage_available"] is False
    assert "usage" not in result.metadata
    assert len(requests) == 1 and response_stream.closed


@pytest.mark.anyio
@pytest.mark.parametrize("collect", [True, False])
async def test_streaming_requests_work_without_sdk_stream_options_argument(monkeypatch, collect):
    sdk_create = AsyncCompletions.create

    # The minimum supported SDK accepts extra_body but has no stream_options keyword.
    async def create(self, *, model, messages, stream, tools=None, extra_body=None, extra_headers=None):
        return await sdk_create(self, model=model, messages=messages, stream=stream, tools=tools, extra_body=extra_body, extra_headers=extra_headers)

    monkeypatch.setattr(AsyncCompletions, "create", create)
    wire = frame({"delta": {"content": "answer"}, "finish_reason": "stop"}) + b"data: [DONE]\n\n"
    provider, requests, _ = mock_provider(monkeypatch, wire)
    options = {"extra_body": {"enable_thinking": False, "stream_options": {"include_usage": False}}}
    deltas = []
    if collect:
        result = await provider.collect_chat_stream([], model="model", max_content_bytes=100, request_options=options)
    else:
        result = await provider.chat([], [], model="model", stream=True, stream_callback=deltas.append, request_options=options)
        assert deltas == ["answer"]

    request, = requests
    body = json.loads(request.content)
    assert result.content == "answer"
    assert body["stream_options"] == {"include_usage": False}
    assert body["enable_thinking"] is False
