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


class ChatSessionMessageResponse(BaseModel):
    message_id: int
    role: str
    content: str
    created_at: str
    updated_at: str
    raw: dict[str, Any] = Field(default_factory=dict)
