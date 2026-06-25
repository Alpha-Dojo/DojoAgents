from __future__ import annotations

from typing import List, Literal

from pydantic import BaseModel, Field


class AgentModelItem(BaseModel):
    id: str = Field(..., description="Stable model identifier for API requests")
    label: str = Field(..., description="Display name, e.g. Gemini-3.5")
    provider: str = Field(..., description="Provider slug: google, openai, anthropic, …")
    model: str = Field("", description="Concrete provider model id")
    available: bool = Field(..., description="Whether the model can be selected and used")
    unavailable_reason: str | None = Field(None, description="Reason the model cannot be selected")


class AgentModelsResponse(BaseModel):
    default_model_id: str = Field(..., description="Default selected model id")
    gemini_configured: bool = Field(
        False,
        description="True when GEMINI_API_KEY is set on the server",
    )
    zhipu_configured: bool = Field(
        False,
        description="True when a Zhipu/GLM provider is configured on the server",
    )
    agent_ready: bool = Field(
        False,
        description="True when at least one model is available",
    )
    models: List[AgentModelItem] = Field(default_factory=list)


class AgentChatMessage(BaseModel):
    role: Literal["user", "assistant"] = Field(..., description="Conversation role")
    content: str = Field(..., min_length=1, description="Plain-text message body")


class AgentChatRequest(BaseModel):
    model_id: str = Field(..., min_length=1, description="Model id from /agent/models")
    messages: List[AgentChatMessage] = Field(..., min_length=1, max_length=50)


class AgentChatResponse(BaseModel):
    model_id: str
    message: AgentChatMessage
