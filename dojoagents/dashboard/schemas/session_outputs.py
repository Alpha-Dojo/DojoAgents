from __future__ import annotations

from pydantic import BaseModel, Field


class SessionOutputFileItem(BaseModel):
    filename: str
    path: str = ""
    object_id: str | None = None
    bytes_written: int
    updated_at: str


class SessionOutputsResponse(BaseModel):
    session_id: str
    output_dir: str = ""
    files: list[SessionOutputFileItem] = Field(default_factory=list)


class SessionOutputRevealResponse(BaseModel):
    ok: bool = True
    path: str
