from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from dojoagents.quant.context import QuantContext


@dataclass(frozen=True)
class ChatRequest:
    message: str
    user_id: str
    session_id: str
    channel: str = "cli"
    quant: QuantContext | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class ToolResult:
    call_id: str
    name: str
    ok: bool
    content: str = ""
    error: str = ""
    latency_ms: int = 0
    truncated: bool = False
    data: Any = None
    viz_blocks: list[dict[str, Any]] = field(default_factory=list)
    artifacts: list[dict[str, Any]] = field(default_factory=list)
    resource_changes: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_message(self) -> dict[str, Any]:
        payload = self.content if self.ok else self.error
        return {
            "role": "tool",
            "tool_call_id": self.call_id,
            "name": self.name,
            "content": payload,
        }


class ToolResultList(list[ToolResult]):
    def to_messages(self) -> list[dict[str, Any]]:
        return [result.to_message() for result in self]


@dataclass
class LLMResult:
    content: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentResponse:
    content: str
    session_id: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    tool_results: list[ToolResult] = field(default_factory=list)
    artifacts: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


# ── OpenAI Chat Completions Protocol Models ────────────────────────


@dataclass
class ChatCompletionRequest:
    """OpenAI-compatible chat completion request."""

    model: str
    messages: list[dict[str, Any]]
    stream: bool = False
    tools: list[dict[str, Any]] | None = None
    tool_choice: str | dict = "auto"
    temperature: float = 1.0
    user: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ChatCompletionResponse:
    """OpenAI-compatible chat completion response."""

    id: str
    object: str  # "chat.completion"
    created: int
    model: str
    choices: list[dict[str, Any]]
    usage: dict[str, int] = field(
        default_factory=lambda: {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
        }
    )
    dojo: dict[str, Any] | None = None

    @classmethod
    def from_agent_response(
        cls,
        response: AgentResponse,
        *,
        model: str,
    ) -> ChatCompletionResponse:
        usage_data = response.metadata.get("usage")
        usage = {
            "prompt_tokens": usage_data.get("prompt_tokens", 0) if usage_data else 0,
            "completion_tokens": usage_data.get("completion_tokens", 0) if usage_data else 0,
            "total_tokens": usage_data.get("total_tokens", 0) if usage_data else 0,
        }
        return cls(
            id=f"chatcmpl-dojo-{uuid.uuid4().hex[:8]}",
            object="chat.completion",
            created=int(time.time()),
            model=model,
            choices=[
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": response.content,
                    },
                    "finish_reason": "stop",
                }
            ],
            usage=usage,
            dojo=response.metadata.get("dojo"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "object": self.object,
            "created": self.created,
            "model": self.model,
            "choices": self.choices,
            "usage": self.usage,
            **({"dojo": self.dojo} if self.dojo is not None else {}),
        }


@dataclass
class ChatCompletionChunk:
    """OpenAI-compatible streaming chat completion chunk."""

    id: str
    object: str  # "chat.completion.chunk"
    created: int
    model: str
    choices: list[dict[str, Any]]
    dojo_event: dict[str, Any] | None = None

    def to_sse_line(self) -> str:
        payload = {
            "id": self.id,
            "object": self.object,
            "created": self.created,
            "model": self.model,
            "choices": self.choices,
        }
        if self.dojo_event is not None:
            payload["dojo_event"] = self.dojo_event
        return f"data: {json.dumps(payload, ensure_ascii=False)}\n"

    @staticmethod
    def done_sentinel() -> str:
        return "data: [DONE]\n"
