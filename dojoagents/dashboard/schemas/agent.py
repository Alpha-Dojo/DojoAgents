from __future__ import annotations

from typing import List, Literal

from pydantic import BaseModel, Field


class AgentChatMessage(BaseModel):
    role: Literal["user", "assistant"] = Field(..., description="Conversation role")
    content: str = Field(..., min_length=1, description="Plain-text message body")


class AgentChatRequest(BaseModel):
    model_id: str = Field(..., min_length=1, description="Selected agent model id")
    messages: List[AgentChatMessage] = Field(..., min_length=1, max_length=50)


class AgentChatResponse(BaseModel):
    model_id: str
    message: AgentChatMessage
