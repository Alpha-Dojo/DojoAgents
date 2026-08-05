from __future__ import annotations

from pydantic import BaseModel, Field


class ModelOption(BaseModel):
    id: str
    label: str
    provider: str
    model: str
    available: bool
    unavailable_reason: str | None = None


class ModelOptionsResponse(BaseModel):
    default_model_id: str = ""
    gemini_configured: bool = False
    zhipu_configured: bool = False
    agent_ready: bool = False
    models: list[ModelOption] = Field(default_factory=list)
