from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, List, Optional

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
    AgentModelDefinition(
        id="glm-4",
        label="GLM-4",
        provider="glm",
        available=True,
    ),
    AgentModelDefinition(
        id="minimax-abab6.5",
        label="MiniMax abab6.5",
        provider="minimax",
        available=True,
    ),
    AgentModelDefinition(
        id="kimi-moonshot",
        label="Kimi (Moonshot)",
        provider="kimi",
        available=True,
    ),
)

DEFAULT_AGENT_MODEL_ID = "gemini-3.5"

_PROVIDER_LABELS = {
    "openai": "OpenAI",
    "anthropic": "Anthropic",
    "gemini": "Google Gemini",
    "deepseek": "DeepSeek",
    "qwen": "Alibaba Tongyi",
    "dashscope": "Alibaba Tongyi",
    "glm": "Zhipu GLM",
    "zhipu": "Zhipu GLM",
    "zhipuai": "Zhipu GLM",
    "moonshot": "Moonshot",
    "kimi": "Kimi",
    "ollama": "Ollama",
    "minimax": "MiniMax",
}


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
            model=model.api_model_id or model.id,
            available=model.available,
            unavailable_reason=None if model.available else "Provider is not configured",
        )
        for model in AGENT_MODEL_CATALOG
    ]


def _provider_label(provider: str) -> str:
    return _PROVIDER_LABELS.get(provider, provider)


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {
        "model": getattr(value, "model", ""),
        "base_url": getattr(value, "base_url", None),
        "api_key_env": getattr(value, "api_key_env", None),
        "api_key": getattr(value, "api_key", None),
    }


def list_configured_agent_models(llm_provider: Any) -> list[AgentModelItem]:
    providers = getattr(llm_provider, "providers", {}) or {}
    items: list[AgentModelItem] = []

    for provider_name, provider_config in providers.items():
        provider = str(provider_name)
        config = _as_dict(provider_config)
        model = str(config.get("model") or "").strip()
        if not model:
            continue
        items.append(
            AgentModelItem(
                id=provider,
                label=f"{_provider_label(provider)} · {model}",
                provider=provider,
                model=model,
                available=True,
                unavailable_reason=None,
            )
        )

    return items
