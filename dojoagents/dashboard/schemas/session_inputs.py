from __future__ import annotations

from pydantic import BaseModel, Field


class SessionInputFileItem(BaseModel):
    filename: str
    path: str = ""
    object_id: str | None = None
    bytes: int
    kind: str
    updated_at: str
    summary: str | None = None
    preview_text: str | None = None
    truncated: bool = False


class SessionInputsResponse(BaseModel):
    session_id: str
    input_dir: str = ""
    files: list[SessionInputFileItem] = Field(default_factory=list)


class SessionInputUploadResponse(BaseModel):
    ok: bool = True
    file: SessionInputFileItem


class SessionInputRevealResponse(BaseModel):
    ok: bool = True
    path: str
