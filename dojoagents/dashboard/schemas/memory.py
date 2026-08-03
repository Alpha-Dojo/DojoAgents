from __future__ import annotations

from pydantic import BaseModel


class ClearGeneratedMemoryResponse(BaseModel):
    ok: bool = True
    directory: str
    deleted_count: int
