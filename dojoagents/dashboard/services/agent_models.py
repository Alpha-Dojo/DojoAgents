from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Optional

from dojoagents.dashboard.schemas.agent import AgentModelItem


@dataclass(frozen=True)
class AgentModelDefinition:
    id: str
    label: str
    provider: str
    available: bool
    api_model_id: Optional[str] = None


AGENT_MODEL_CATALOG: tuple[AgentModelDefinition, ...] = (
    AgentModelDefinition(
        id="gemini-3.5",
        label="Gemini-3.5",
        provider="google",
        available=True,
        api_model_id="gemini-3.5-flash",
    ),
    AgentModelDefinition(
        id="gpt-5.4",
        label="GPT-5.4",
        provider="openai",
        available=False,
    ),
    AgentModelDefinition(
        id="claude-sonnet-4.6",
        label="Claude Sonnet 4.6",
        provider="anthropic",
        available=False,
    ),
    AgentModelDefinition(
        id="grok-4",
        label="Grok-4",
        provider="xai",
        available=False,
    ),
    AgentModelDefinition(
        id="deepseek-r1",
        label="DeepSeek-R1",
        provider="deepseek",
        available=False,
    ),
)

DEFAULT_AGENT_MODEL_ID = "gemini-3.5"


def iter_agent_models() -> Iterable[AgentModelDefinition]:
    return AGENT_MODEL_CATALOG


def get_agent_model(model_id: str) -> Optional[AgentModelDefinition]:
    needle = model_id.strip().lower()
    for model in AGENT_MODEL_CATALOG:
        if model.id.lower() == needle:
            return model
    return None


def list_agent_model_items() -> List[AgentModelItem]:
    return [
        AgentModelItem(
            id=model.id,
            label=model.label,
            provider=model.provider,
            available=model.available,
        )
        for model in AGENT_MODEL_CATALOG
    ]
