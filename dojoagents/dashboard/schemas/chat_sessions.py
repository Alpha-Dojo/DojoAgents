from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ChatSessionExportRequest(BaseModel):
    session_id: str | None = None
    output_dir: str | None = None
    format: str = "jsonl"
    include_raw_strands: bool = True
    include_dojo_sidecars: bool = True
    include_memory: bool = True
    include_token_usage: bool = True
    include_archived: bool = False


class ChatSessionSummaryResponse(BaseModel):
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
    token_state: dict[str, Any] = Field(default_factory=dict)
    memory_state: dict[str, Any] = Field(default_factory=dict)


class ChatSessionListResponse(BaseModel):
    sessions: list[ChatSessionSummaryResponse]
    next_cursor: str | None = None


class ChatSessionMessageResponse(BaseModel):
    message_id: int | str | None = None
    role: str
    content: str
    created_at: str
    updated_at: str
    raw: dict[str, Any] = Field(default_factory=dict)
    raw_strands: dict[str, Any] = Field(default_factory=dict)
    openai_messages: list[dict[str, Any]] = Field(default_factory=list)


class ChatSessionMessagesResponse(BaseModel):
    session_id: str
    agent_id: str
    messages: list[ChatSessionMessageResponse]
    next_offset: int | None = None
    turns: list[dict[str, Any]] = Field(default_factory=list)


class ArchiveChatSessionResponse(BaseModel):
    archived: bool
    session_id: str


class ChatSessionExportResponse(BaseModel):
    ok: bool
    export_dir: str
    session_count: int
    message_count: int
    files: list[str]
