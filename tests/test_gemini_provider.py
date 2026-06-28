from __future__ import annotations

from unittest.mock import patch

import pytest

from dojoagents.agent.gemini_provider import GeminiNativeProvider
from dojoagents.agent.provider_state import ProviderConversationState


class _FakeResponse:
    def __init__(self, payload: dict, status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code
        self.text = str(payload)

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            import httpx

            request = httpx.Request("POST", "https://example.com")
            raise httpx.HTTPStatusError("error", request=request, response=httpx.Response(self.status_code, request=request, text=self.text))

    def json(self) -> dict:
        return dict(self._payload)


class _FakeAsyncClient:
    last_url: str | None = None
    last_params: dict | None = None
    last_json: dict | None = None

    def __init__(self, *args, **kwargs) -> None:
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    async def post(self, url: str, *, params: dict | None = None, json: dict | None = None):
        type(self).last_url = url
        type(self).last_params = params
        type(self).last_json = json
        return _FakeResponse(
            {
                "candidates": [
                    {
                        "content": {
                            "role": "model",
                            "parts": [
                                {"thought": True, "text": "thinking"},
                                {
                                    "functionCall": {
                                        "name": "portfolio_read_list",
                                        "args": {"market": "us"},
                                        "thoughtSignature": "sig-123",
                                    }
                                },
                            ],
                        }
                    }
                ],
                "usageMetadata": {
                    "promptTokenCount": 11,
                    "candidatesTokenCount": 7,
                    "totalTokenCount": 18,
                },
            }
        )


class _FakeStreamResponse:
    def __init__(self, lines: list[str], status_code: int = 200) -> None:
        self._lines = list(lines)
        self.status_code = status_code
        self.text = "\n".join(lines)

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            import httpx

            request = httpx.Request("POST", "https://example.com")
            raise httpx.HTTPStatusError("error", request=request, response=httpx.Response(self.status_code, request=request, text=self.text))

    async def aiter_lines(self):
        for line in self._lines:
            yield line


class _FakeStreamingAsyncClient(_FakeAsyncClient):
    stream_url: str | None = None
    stream_params: dict | None = None
    stream_json: dict | None = None

    def stream(self, method: str, url: str, *, params: dict | None = None, json: dict | None = None):
        assert method == "POST"
        type(self).stream_url = url
        type(self).stream_params = params
        type(self).stream_json = json
        return _FakeStreamResponse(
            [
                'data: {"candidates":[{"content":{"role":"model","parts":[{"thought":true,"text":"think "},{"text":"Hel"}]}}]}',
                "",
                'data: {"candidates":[{"content":{"role":"model","parts":[{"thought":true,"text":"think more"},{"text":"Hello"}]}}],"usageMetadata":{"promptTokenCount":3,"candidatesTokenCount":2,"totalTokenCount":5}}',  # noqa
                "",
            ]
        )


class _FakeStreamingAggregateAsyncClient(_FakeAsyncClient):
    stream_url: str | None = None
    stream_params: dict | None = None
    stream_json: dict | None = None

    def stream(self, method: str, url: str, *, params: dict | None = None, json: dict | None = None):
        assert method == "POST"
        type(self).stream_url = url
        type(self).stream_params = params
        type(self).stream_json = json
        return _FakeStreamResponse(
            [
                'data: {"candidates":[{"content":{"role":"model","parts":[{"text":"Hel"}]}}]}',
                "",
                'data: {"candidates":[{"content":{"role":"model","parts":[]}}],"usageMetadata":{"promptTokenCount":3,"candidatesTokenCount":2,"totalTokenCount":5}}',
                "",
            ]
        )


class _FakeEventSink:
    def __init__(self) -> None:
        self.events: list[tuple[str, str]] = []

    def thinking_start(self, summary: str = "") -> None:
        self.events.append(("think_start", summary))

    def thinking_delta(self, text: str) -> None:
        self.events.append(("think_delta", text))

    def thinking_end(self, summary: str = "") -> None:
        self.events.append(("think_end", summary))


@pytest.mark.asyncio
async def test_gemini_native_provider_reuses_native_history_and_records_state() -> None:
    provider_state = ProviderConversationState()
    native_content = {
        "role": "model",
        "parts": [
            {
                "functionCall": {
                    "name": "portfolio_read_list",
                    "args": {"market": "cn"},
                    "thoughtSignature": "prior-sig",
                }
            }
        ],
    }
    provider_state.record_tool_call(
        provider="gemini",
        model="gemini-2.5-pro",
        session_id="s1",
        tool_call_id="call-prev",
        tool_name="portfolio_read_list",
        arguments={"market": "cn"},
        native_model_content=native_content,
    )
    provider = GeminiNativeProvider(api_key="test-key", base_url="https://generativelanguage.googleapis.com/v1beta/openai")

    with patch("dojoagents.agent.gemini_provider.httpx.AsyncClient", _FakeAsyncClient):
        result = await provider.chat(
            [
                {"role": "system", "content": "System prompt"},
                {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {
                            "id": "call-prev",
                            "type": "function",
                            "function": {"name": "portfolio_read_list", "arguments": '{"market":"cn"}'},
                        }
                    ],
                },
                {"role": "tool", "tool_call_id": "call-prev", "name": "portfolio_read_list", "content": "[]"},
            ],
            [{"name": "portfolio_read_list", "description": "List portfolios", "parameters": {"type": "object"}}],
            model="gemini-2.5-pro",
            metadata={"session_id": "s1", "_dojo_provider_state": provider_state},
        )

    assert _FakeAsyncClient.last_url == "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-pro:generateContent"
    assert _FakeAsyncClient.last_params == {"key": "test-key"}
    assert _FakeAsyncClient.last_json["systemInstruction"]["parts"][0]["text"] == "System prompt"
    assert _FakeAsyncClient.last_json["contents"][0] == native_content
    assert _FakeAsyncClient.last_json["contents"][1]["parts"][0]["functionResponse"]["name"] == "portfolio_read_list"
    assert result.content == ""
    assert result.metadata["reasoning_content"] == "thinking"
    assert result.metadata["usage"]["total_tokens"] == 18
    assert result.tool_calls[0].name == "portfolio_read_list"
    assert result.tool_calls[0].arguments == {"market": "us"}
    assert result.tool_calls[0].metadata["thought_signature"] == "sig-123"
    stored = provider_state.get_tool_call(
        provider="gemini",
        model="gemini-2.5-pro",
        session_id="s1",
        tool_call_id=result.tool_calls[0].id,
    )
    assert stored is not None
    assert stored.native_model_content["parts"][1]["functionCall"]["thoughtSignature"] == "sig-123"


@pytest.mark.asyncio
async def test_gemini_native_provider_streams_text_and_thinking_deltas() -> None:
    provider = GeminiNativeProvider(api_key="test-key", base_url="https://generativelanguage.googleapis.com/v1beta")
    deltas: list[str] = []
    event_sink = _FakeEventSink()

    with patch("dojoagents.agent.gemini_provider.httpx.AsyncClient", _FakeStreamingAsyncClient):
        result = await provider.chat(
            [{"role": "user", "content": "Say hello"}],
            [],
            model="gemini-2.5-pro",
            stream=True,
            stream_callback=deltas.append,
            metadata={"session_id": "s1", "_dojo_event_sink": event_sink},
        )

    assert _FakeStreamingAsyncClient.stream_url == "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-pro:streamGenerateContent"
    assert _FakeStreamingAsyncClient.stream_params == {"alt": "sse", "key": "test-key"}
    assert _FakeStreamingAsyncClient.stream_json["contents"][0]["parts"][0]["text"] == "Say hello"
    assert deltas == ["Hel", "lo"]
    assert event_sink.events == [
        ("think_start", ""),
        ("think_delta", "think "),
        ("think_delta", "more"),
        ("think_end", ""),
    ]
    assert result.content == "Hello"
    assert result.metadata["reasoning_content"] == "think more"
    assert result.metadata["reasoning_streamed"] is True
    assert result.metadata["usage"]["total_tokens"] == 5


@pytest.mark.asyncio
async def test_gemini_native_provider_aggregates_stream_chunks_before_final_parse() -> None:
    provider = GeminiNativeProvider(api_key="test-key", base_url="https://generativelanguage.googleapis.com/v1beta")
    deltas: list[str] = []

    with patch("dojoagents.agent.gemini_provider.httpx.AsyncClient", _FakeStreamingAggregateAsyncClient):
        result = await provider.chat(
            [{"role": "user", "content": "Say hello"}],
            [],
            model="gemini-2.5-pro",
            stream=True,
            stream_callback=deltas.append,
            metadata={"session_id": "s1"},
        )

    assert deltas == ["Hel"]
    assert result.content == "Hel"
    assert result.metadata["usage"]["total_tokens"] == 5


@pytest.mark.asyncio
async def test_gemini_native_provider_uses_non_stream_for_tool_planning_even_when_stream_requested() -> None:
    provider = GeminiNativeProvider(api_key="test-key", base_url="https://generativelanguage.googleapis.com/v1beta")

    with patch("dojoagents.agent.gemini_provider.httpx.AsyncClient", _FakeAsyncClient):
        result = await provider.chat(
            [{"role": "user", "content": "Find portfolios"}],
            [{"name": "portfolio_read_list", "description": "List portfolios", "parameters": {"type": "object"}}],
            model="gemini-2.5-pro",
            stream=True,
            metadata={"session_id": "s1"},
        )

    assert _FakeAsyncClient.last_url == "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-pro:generateContent"
    assert result.tool_calls[0].name == "portfolio_read_list"
