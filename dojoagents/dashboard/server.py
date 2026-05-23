from __future__ import annotations

from dataclasses import asdict, is_dataclass
from typing import Any

from fastapi import FastAPI

from dojoagents.agent.models import AgentResponse, ChatRequest
from dojoagents.quant.context import QuantContext


def _jsonable(value: Any) -> Any:
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    return value


def _chat_request(payload: dict[str, Any]) -> ChatRequest:
    quant = payload.get("quant")
    if isinstance(quant, dict):
        quant = QuantContext(**quant)
    return ChatRequest(
        message=payload["message"],
        user_id=payload["user_id"],
        session_id=payload["session_id"],
        channel=payload.get("channel", "dashboard"),
        quant=quant,
        metadata=dict(payload.get("metadata", {})),
    )


def create_app(runtime: Any) -> FastAPI:
    app = FastAPI(title="DojoAgents Dashboard")

    @app.get("/api/health")
    async def health() -> dict:
        return {"ok": True}

    @app.get("/api/config")
    async def config() -> dict:
        store = getattr(runtime, "config_store", None)
        if store is None:
            return {}
        return store.redacted()

    @app.get("/api/jobs")
    async def jobs() -> list[dict]:
        scheduler = getattr(runtime, "scheduler")
        if hasattr(scheduler, "list_jobs"):
            return _jsonable(scheduler.list_jobs())
        return []

    @app.get("/api/extensions")
    async def extensions() -> list[dict]:
        return _jsonable(runtime.extensions.status())

    @app.post("/api/chat")
    async def chat(payload: dict[str, Any]) -> dict:
        response: AgentResponse = await runtime.agent.run(_chat_request(payload))
        return _jsonable(response)

    return app
