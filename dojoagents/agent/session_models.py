from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class DojoSessionRunHandle:
    session_id: str
    agent_id: str
    turn_id: str
    run_id: str | None
    model: str


@dataclass
class DojoSessionSummary:
    session_id: str
    agent_id: str
    title: str = ""
    user_id: str = "anonymous"
    channel: str = "dashboard"
    model: str = ""
    locale: str = "zh"
    created_at: str = ""
    updated_at: str = ""
    message_count: int = 0
    turn_count: int = 0
    run_count: int = 0
    last_run_id: str | None = None
    status: str = "idle"
    archived: bool = False
    token_state: dict[str, Any] = field(default_factory=dict)
    memory_state: dict[str, Any] = field(default_factory=dict)


@dataclass
class DojoSessionListResult:
    sessions: list[DojoSessionSummary]
    next_cursor: str | None = None


@dataclass
class DojoProjectedMessage:
    message_id: int
    role: str
    content: str
    created_at: str
    updated_at: str
    raw: dict[str, Any]
    raw_strands: dict[str, Any] = field(default_factory=dict)
    openai_messages: list[dict[str, Any]] = field(default_factory=list)
    tool_results: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class DojoSessionMessagesResult:
    session_id: str
    agent_id: str
    messages: list[DojoProjectedMessage]
    next_offset: int | None = None


@dataclass
class DojoSessionExportResult:
    ok: bool
    export_dir: str
    session_count: int
    message_count: int
    files: list[str]
