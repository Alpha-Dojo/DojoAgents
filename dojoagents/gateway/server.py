from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import asdict
from typing import Any

from fastapi import FastAPI
from fastapi import HTTPException

from dojoagents.gateway.adapters import create_default_gateway_registry
from dojoagents.gateway.registry import GatewayRegistry
from dojoagents.gateway.runner import GatewayRunner


def create_app(
    registry: GatewayRegistry | None = None,
    *,
    runner: Any | None = None,
    autostart: bool = False,
) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if autostart and runner is not None and hasattr(runner, "start"):
            await runner.start()
        try:
            yield
        finally:
            if autostart and runner is not None and hasattr(runner, "stop"):
                await runner.stop()

    app = FastAPI(title="DojoAgents Gateway", lifespan=lifespan)
    platform_registry = registry or create_default_gateway_registry()
    gateway_runner = runner

    @app.get("/api/health")
    async def health() -> dict:
        if gateway_runner is not None:
            return {"ok": True, **gateway_runner.status()}
        return {"ok": True}

    @app.get("/api/status")
    async def status() -> dict:
        if gateway_runner is not None:
            return gateway_runner.status()
        return {"state": "facade", "platforms": {}}

    @app.get("/api/platforms")
    async def platforms() -> list[dict[str, Any]]:
        return platform_registry.status()

    @app.post("/api/webhook/{platform}")
    async def webhook(platform: str, payload: dict[str, Any]) -> dict[str, Any]:
        if gateway_runner is not None:
            return await gateway_runner.handle_webhook(platform, payload)
        try:
            adapter = platform_registry.create_adapter(platform, {})
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=f"Unknown platform: {platform}") from exc
        event = adapter.normalize_message(payload)
        return {
            "event": asdict(event),
            "chat_request": asdict(event.to_chat_request()),
        }

    @app.post("/api/send/{platform}/{target}")
    async def send(platform: str, target: str, payload: dict[str, Any]) -> dict[str, Any]:
        if gateway_runner is not None:
            return await gateway_runner.send(
                platform,
                target,
                str(payload.get("message", "")),
                thread_id=payload.get("thread_id"),
            )
        try:
            adapter = platform_registry.create_adapter(platform, payload.get("config", {}))
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=f"Unknown platform: {platform}") from exc
        result = await adapter.send(
            target,
            str(payload.get("message", "")),
            thread_id=payload.get("thread_id"),
        )
        return asdict(result)

    return app


def create_runner_app(
    runner: GatewayRunner | None = None,
    *,
    config_path: str | None = None,
) -> FastAPI:
    if runner is None and config_path:
        from dojoagents.config.loader import ConfigStore

        runner = GatewayRunner(config_store=ConfigStore(config_path))
    return create_app(runner=runner or GatewayRunner(), autostart=True)
