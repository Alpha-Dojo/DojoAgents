from __future__ import annotations

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
    artifacts: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
