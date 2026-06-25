from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

from dojoagents.dashboard.schemas.agent import AgentModelsResponse
from dojoagents.dashboard.services.agent_models import AGENT_MODEL_CATALOG, DEFAULT_AGENT_MODEL_ID

router = APIRouter(prefix="/agent", tags=["agent"])


@router.get(
    "/models",
    response_model=AgentModelsResponse,
    operation_id="get_agent_models",
    summary="Get available agent models and provider configuration status",
)
async def get_agent_models(request: Request) -> dict[str, Any]:
    store = getattr(request.app.state, "config_store", None)
    raw_config = store.raw() if store else {}
    providers_config = raw_config.get("providers", {})

    models = []
    any_configured = False
    gemini_configured = "google" in providers_config

    for model_def in AGENT_MODEL_CATALOG:
        provider = model_def.provider
        # A model is available if its provider is configured in ~/.dojo/agents.yaml
        is_avail = provider in providers_config
        if is_avail:
            any_configured = True

        models.append(
            {
                "id": model_def.id,
                "label": model_def.label,
                "provider": provider,
                "available": is_avail,
            }
        )

    return {"default_model_id": DEFAULT_AGENT_MODEL_ID, "gemini_configured": gemini_configured, "agent_ready": any_configured, "models": models}
