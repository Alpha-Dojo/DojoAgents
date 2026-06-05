"""Tests for OpenAI Chat Completions protocol models (TDD)."""
from __future__ import annotations

import json
import time

import pytest

from dojoagents.agent.models import AgentResponse


# ── ChatCompletionRequest ──────────────────────────────────────────


def test_chat_completion_request_defaults():
    from dojoagents.agent.models import ChatCompletionRequest

    req = ChatCompletionRequest(
        model="gpt-4.1",
        messages=[{"role": "user", "content": "hi"}],
    )
    assert req.model == "gpt-4.1"
    assert req.stream is False
    assert req.tools is None
    assert req.tool_choice == "auto"
    assert req.temperature == 1.0
    assert req.user is None
    assert req.metadata == {}


def test_chat_completion_request_full_fields():
    from dojoagents.agent.models import ChatCompletionRequest

    req = ChatCompletionRequest(
        model="deepseek-chat",
        messages=[{"role": "user", "content": "analyze BTC"}],
        stream=True,
        tools=[{"type": "function", "function": {"name": "get_kline"}}],
        tool_choice="required",
        temperature=0.5,
        user="user-001",
        metadata={"session_id": "s1", "channel": "dashboard"},
    )
    assert req.stream is True
    assert len(req.tools) == 1
    assert req.tool_choice == "required"
    assert req.temperature == 0.5
    assert req.user == "user-001"
    assert req.metadata["session_id"] == "s1"


# ── ChatCompletionResponse ─────────────────────────────────────────


def test_chat_completion_response_from_agent_response():
    from dojoagents.agent.models import ChatCompletionResponse

    agent_resp = AgentResponse(
        content="hello world",
        session_id="s1",
        metadata={"iterations": 2},
    )
    resp = ChatCompletionResponse.from_agent_response(agent_resp, model="gpt-4.1")

    assert resp.id.startswith("chatcmpl-dojo-")
    assert resp.object == "chat.completion"
    assert isinstance(resp.created, int)
    assert resp.model == "gpt-4.1"
    assert len(resp.choices) == 1
    assert resp.choices[0]["message"]["role"] == "assistant"
    assert resp.choices[0]["message"]["content"] == "hello world"
    assert resp.choices[0]["finish_reason"] == "stop"
    assert resp.usage["prompt_tokens"] == 0
    assert resp.usage["completion_tokens"] == 0
    assert resp.usage["total_tokens"] == 0


def test_chat_completion_response_from_agent_response_with_usage():
    from dojoagents.agent.models import ChatCompletionResponse

    agent_resp = AgentResponse(
        content="reply",
        session_id="s2",
        metadata={
            "iterations": 1,
            "usage": {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
        },
    )
    resp = ChatCompletionResponse.from_agent_response(agent_resp, model="gpt-4.1")

    assert resp.usage["prompt_tokens"] == 100
    assert resp.usage["completion_tokens"] == 50
    assert resp.usage["total_tokens"] == 150


def test_chat_completion_response_to_dict():
    from dojoagents.agent.models import ChatCompletionResponse

    agent_resp = AgentResponse(content="test", session_id="s1")
    resp = ChatCompletionResponse.from_agent_response(agent_resp, model="gpt-4.1")
    d = resp.to_dict()

    assert d["id"].startswith("chatcmpl-dojo-")
    assert d["object"] == "chat.completion"
    assert d["choices"][0]["message"]["content"] == "test"
    assert "usage" in d


# ── ChatCompletionChunk ────────────────────────────────────────────


def test_chat_completion_chunk_structure():
    from dojoagents.agent.models import ChatCompletionChunk

    chunk = ChatCompletionChunk(
        id="chatcmpl-test",
        object="chat.completion.chunk",
        created=1000,
        model="gpt-4.1",
        choices=[{
            "index": 0,
            "delta": {"role": "assistant", "content": ""},
            "finish_reason": None,
        }],
    )
    assert chunk.object == "chat.completion.chunk"
    assert chunk.choices[0]["finish_reason"] is None


def test_chat_completion_chunk_to_sse_line():
    from dojoagents.agent.models import ChatCompletionChunk

    chunk = ChatCompletionChunk(
        id="chatcmpl-test",
        object="chat.completion.chunk",
        created=1000,
        model="gpt-4.1",
        choices=[{
            "index": 0,
            "delta": {"content": "hello"},
            "finish_reason": None,
        }],
    )
    line = chunk.to_sse_line()
    assert line.startswith("data: ")
    assert line.endswith("\n")
    payload = json.loads(line[6:])
    assert payload["choices"][0]["delta"]["content"] == "hello"


def test_chat_completion_chunk_done_sentinel():
    from dojoagents.agent.models import ChatCompletionChunk

    assert ChatCompletionChunk.done_sentinel() == "data: [DONE]\n"
