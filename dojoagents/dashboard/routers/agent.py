from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

from dojoagents.dashboard.schemas.agent import AgentModelsResponse
from dojoagents.dashboard.services.agent_models import DEFAULT_AGENT_MODEL_ID, list_configured_agent_models

router = APIRouter(prefix="/agent", tags=["agent"])


@router.get(
    "/models",
    response_model=AgentModelsResponse,
    operation_id="get_agent_models",
    summary="Get available agent models and provider configuration status",
)
async def get_agent_models(request: Request) -> dict[str, Any]:
    store = getattr(request.app.state, "config_store", None)
    if store is None:
        return {
            "default_model_id": DEFAULT_AGENT_MODEL_ID,
            "gemini_configured": False,
            "zhipu_configured": False,
            "agent_ready": False,
            "models": [],
        }

    config = store.snapshot()
    models = list_configured_agent_models(config.llm_provider)
    any_configured = any(model.available for model in models)

    return {
        "default_model_id": config.llm_provider.default,
        "gemini_configured": "gemini" in config.llm_provider.providers,
        "zhipu_configured": any(provider in config.llm_provider.providers for provider in ("glm", "zhipu", "zhipuai")),
        "agent_ready": any_configured,
        "models": models,
    }
