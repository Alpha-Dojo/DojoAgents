from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from dojoagents.config.loader import (
    provider_model_candidates,
    resolve_provider_config,
)
from dojoagents.dashboard.deps import get_config_store
from dojoagents.dashboard.schemas.model_options import (
    ModelOption,
    ModelOptionsResponse,
)

router = APIRouter(prefix="/models", tags=["models"])
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


@router.get("", response_model=ModelOptionsResponse)
async def list_model_options(
    store: Any | None = Depends(get_config_store),
) -> ModelOptionsResponse:
    if store is None:
        return ModelOptionsResponse()
    llm = store.snapshot().llm_provider
    default_provider, default_config = resolve_provider_config(llm)
    options: list[ModelOption] = []
    default_id = ""
    providers = sorted(
        llm.providers.items(),
        key=lambda item: (item[0] != default_provider, item[0]),
    )
    for provider_name, provider in providers:
        for model in provider_model_candidates(provider):
            selection_id = f"{provider_name}:{model}"
            _, selected = resolve_provider_config(
                llm,
                requested_name=selection_id,
            )
            is_default = (
                provider_name == default_provider
                and selected is not None
                and default_config is not None
                and selected.model == default_config.model
                and selected.author == default_config.author
            )
            if is_default:
                default_id = selection_id
            available = bool(provider.api_key) or provider_name == "ollama"
            options.append(
                ModelOption(
                    id=selection_id,
                    label=f"{_PROVIDER_LABELS.get(provider_name, provider_name)} · {model}",
                    provider=provider_name,
                    model=model,
                    available=available,
                    unavailable_reason=None if available else "API key is not configured",
                )
            )
    available_providers = {option.provider for option in options if option.available}
    return ModelOptionsResponse(
        default_model_id=default_id,
        gemini_configured="gemini" in available_providers,
        zhipu_configured=bool({"glm", "zhipu", "zhipuai"} & available_providers),
        agent_ready=bool(available_providers),
        models=options,
    )
