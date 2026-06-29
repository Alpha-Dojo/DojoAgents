from __future__ import annotations

import asyncio
import json
import os
import uuid
from contextlib import asynccontextmanager
from dataclasses import asdict, is_dataclass, replace
from pathlib import Path
from typing import Any

from dojo.client.async_client import AsyncDojo

from dojoagents.dashboard.routers import (
    dojo_core,
    dojo_folio,
    dojo_mesh,
    dojo_sphere,
    market,
    markets,
    portfolio,
    sector,
    sectors,
    ticker,
    utility,
)
from dojoagents.dashboard.frontend_builder import setup_frontend_static_files
from dojoagents.dashboard.agent_runs import AgentRunManager
from dojoagents.dashboard.services.market_refresh_jobs import start_refresh_loop  # noqa
from dojoagents.dashboard.services.financial_registry import FinancialDomainRegistry
from dojoagents.dashboard.tools import register_dashboard_domain_tools, register_dashboard_portfolio_tools

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from dojoagents.dashboard.middleware.profiler_middleware import PyInstrumentProfilerMiddleware

from dojoagents.agent.models import (
    AgentResponse,
    ChatCompletionResponse,
    ChatRequest,
)
from dojoagents.agent.events import AgentEventSink
from dojoagents.dashboard.sse import make_event_queue_sink, stream_completion_chunks
from dojoagents.quant.context import QuantContext
from dojoagents.config.models import FinancialDashboardConfig
from dojoagents.agent.providers import OpenAICompatibleProvider
from dojoagents.agent.gemini_provider import GeminiNativeProvider
from dojoagents.agent.model_context import ModelContextRegistry
from dojoagents.agent.token_ledger import SessionTokenLedger
from dojoagents.logging import LOGGER


def _jsonable(value: Any) -> Any:
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    return value


def _sync_agent_model_with_default_provider(config: dict[str, Any]) -> dict[str, Any]:
    llm_provider = config.get("llm_provider")
    if not isinstance(llm_provider, dict):
        return config
    default_provider = llm_provider.get("default")
    providers = llm_provider.get("providers")
    if not isinstance(default_provider, str) or not isinstance(providers, dict):
        return config
    provider = providers.get(default_provider)
    if not isinstance(provider, dict):
        return config
    model = provider.get("model")
    if not isinstance(model, str) or not model.strip():
        return config
    agent = config.setdefault("agent", {})
    if isinstance(agent, dict):
        agent["model"] = model
    return config


def _sync_runtime_agent_from_config(runtime: Any, provider_name: str | None) -> str:
    store = getattr(runtime, "config_store", None)
    agent = getattr(runtime, "agent", None)
    if store is None or agent is None:
        return provider_name or "default"

    config = store.snapshot()
    selected_provider = (provider_name or config.llm_provider.default or "").strip()
    if selected_provider == "default" or selected_provider not in config.llm_provider.providers:
        selected_provider = config.llm_provider.default
    provider_cfg = config.llm_provider.providers.get(selected_provider)
    if provider_cfg is None:
        return selected_provider or "default"

    if selected_provider == "gemini":
        llm_provider = GeminiNativeProvider(
            api_key=provider_cfg.api_key,
            api_key_env=provider_cfg.api_key_env,
            base_url=provider_cfg.base_url,
        )
    else:
        llm_provider = OpenAICompatibleProvider(api_key=provider_cfg.api_key, base_url=provider_cfg.base_url)
        llm_provider.name = selected_provider
    LOGGER.info(
        "Dashboard synced runtime agent provider: requested=%s selected=%s implementation=%s model=%s base_url=%s api_key_present=%s",
        provider_name,
        selected_provider,
        type(llm_provider).__name__,
        provider_cfg.model,
        getattr(provider_cfg, "base_url", None),
        bool(getattr(provider_cfg, "api_key", None) or getattr(provider_cfg, "api_key_env", None)),
    )
    agent.llm_provider = llm_provider
    agent.provider_config = provider_cfg
    if is_dataclass(getattr(agent, "config", None)):
        agent.config = replace(
            agent.config,
            model=provider_cfg.model,
            enable_context_compression=config.agent.enable_context_compression,
            compression_threshold_ratio=config.agent.compression_threshold_ratio,
            session_max_tokens_cap=config.agent.session_max_tokens_cap,
            default_context_window=config.agent.default_context_window,
        )
    elif hasattr(agent, "config"):
        agent.config.model = provider_cfg.model
        agent.config.enable_context_compression = config.agent.enable_context_compression
        agent.config.compression_threshold_ratio = config.agent.compression_threshold_ratio
        agent.config.session_max_tokens_cap = config.agent.session_max_tokens_cap
        agent.config.default_context_window = config.agent.default_context_window
    if hasattr(agent, "model_context_registry"):
        agent.model_context_registry = ModelContextRegistry(
            default_context_window=config.agent.default_context_window,
        )
    return provider_cfg.model


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


def _normalize_openai_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for message in messages:
        role = str(message.get("role") or "").strip()
        if not role:
            continue
        content = message.get("content")
        if isinstance(content, list):
            text_parts: list[str] = []
            for part in content:
                if isinstance(part, dict) and part.get("type") == "text":
                    text_parts.append(str(part.get("text") or ""))
            content = "".join(text_parts)
        elif content is None:
            content = ""
        else:
            content = str(content)
        normalized.append(
            {
                "role": role,
                "content": content,
                **({"tool_calls": message.get("tool_calls")} if message.get("tool_calls") else {}),
                **({"tool_call_id": message.get("tool_call_id")} if message.get("tool_call_id") else {}),
                **({"name": message.get("name")} if message.get("name") else {}),
            }
        )
    return normalized


def _completion_request(payload: dict[str, Any]) -> tuple[ChatRequest, dict[str, Any]]:
    """Parse payload into (ChatRequest, extra_info) with dual-format detection.

    Returns a tuple of (ChatRequest, info_dict) where info_dict contains:
    - ``stream``: bool
    - ``model``: str
    - ``messages``: list[dict]  (the raw messages array)

    Supports both:
    - **New OpenAI format**: ``{"messages": [...], "model": "...", ...}``
    - **Legacy format**: ``{"message": "...", "user_id": "...", "session_id": "..."}``
    """
    metadata = dict(payload.get("metadata", {}))

    if "messages" in payload:
        # New OpenAI-compatible format
        raw_messages = payload["messages"]
        if not isinstance(raw_messages, list) or not raw_messages:
            raise ValueError("messages must be a non-empty array")
        messages = _normalize_openai_messages(raw_messages)
        if not messages:
            raise ValueError("messages must contain at least one valid message")

        last_user_index = -1
        last_user_msg = ""
        for idx in range(len(messages) - 1, -1, -1):
            msg = messages[idx]
            if msg.get("role") == "user":
                content = str(msg.get("content") or "").strip()
                if not content:
                    continue
                last_user_index = idx
                last_user_msg = content
                break
        if last_user_index < 0:
            raise ValueError("messages must include at least one non-empty user message")

        user_id = payload.get("user", metadata.get("user_id", "anonymous"))
        session_id = metadata.get("session_id", uuid.uuid4().hex)
        channel = metadata.get("channel", "dashboard")
        stream = payload.get("stream", False)
        model = payload.get("model", "default")
        event_format = str(metadata.get("event_format") or "openai.v1")
        locale = str(metadata.get("locale") or payload.get("locale") or "zh")

        quant_data = metadata.get("quant")
        quant = QuantContext(**quant_data) if isinstance(quant_data, dict) else None
        metadata["history"] = messages[:last_user_index]
        metadata["locale"] = locale
        metadata["event_format"] = event_format

        req = ChatRequest(
            message=last_user_msg,
            user_id=user_id,
            session_id=session_id,
            channel=channel,
            quant=quant,
            metadata=metadata,
        )
        return req, {"stream": stream, "model": model, "messages": messages, "event_format": event_format}
    else:
        # Legacy format
        req = _chat_request(payload)
        req.metadata.setdefault("locale", payload.get("locale", "zh"))
        req.metadata.setdefault("event_format", "openai.v1")
        return req, {"stream": False, "model": "default", "messages": [{"role": "user", "content": req.message}], "event_format": "openai.v1"}


async def _close_dojo_client(client: Any) -> None:
    close = getattr(client, "aclose", None)
    if callable(close):
        await close()
        return
    http_client = getattr(client, "_client", None)
    close = getattr(http_client, "aclose", None)
    if callable(close):
        await close()


def create_app(
    runtime: Any,
    *,
    dojo_client_factory=AsyncDojo,
    store_registry: Any | None = None,
    dashboard_data_root: Path | None = None,
) -> FastAPI:
    registry = store_registry or FinancialDomainRegistry()
    if hasattr(runtime, "agent") and hasattr(runtime.agent, "tool_executor"):
        register_dashboard_domain_tools(runtime.agent.tool_executor.registry, registry)
        register_dashboard_portfolio_tools(runtime.agent.tool_executor.registry, registry)

    store = getattr(runtime, "config_store", None)
    if store:
        snapshot = store.snapshot()
        sdk_cfg = getattr(snapshot, "dojosdk", None)
        offline_mode = getattr(snapshot, "offline_mode", True)
        financial_cfg = snapshot.dashboard.financial
    else:
        sdk_cfg = None
        offline_mode = True
        financial_cfg = FinancialDashboardConfig()

    sdk_cache_dir = financial_cfg.sdk_cache_path
    os.environ["DOJO_CACHE_DIR"] = str(sdk_cache_dir)
    resolved_data_root = (dashboard_data_root or financial_cfg.dashboard_data_path).expanduser()

    if offline_mode:
        os.environ["DOJO_ONLINE"] = "0"

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        kwargs = {
            "api_key": sdk_cfg.api_key if sdk_cfg else None,
            "base_url": sdk_cfg.base_url if sdk_cfg else None,
            "timeout": sdk_cfg.timeout if sdk_cfg else 60.0,
            "max_retries": sdk_cfg.max_retries if sdk_cfg else 1,
        }
        client = dojo_client_factory(**kwargs)
        refresh_task = None
        try:
            if hasattr(client, "preload_offline_data"):
                LOGGER.info("=== 阶段 1/2: 开始预加载 DojoSDK 离线数据 ===")
                await client.preload_offline_data()
                LOGGER.info("=== 阶段 1/2: DojoSDK 离线数据预加载完成 ===")

            LOGGER.info("=== 阶段 2/2: 开始预加载 Dashboard 内存服务 ===")
            await registry.init_and_load_all(
                client,
                data_root=resolved_data_root,
                preload=True,
            )
            LOGGER.info("=== 阶段 2/2: Dashboard 内存服务预加载完成 ===")
            app.state.dojo_client = client
            app.state.config_store = getattr(runtime, "config_store", None)
            app.state.financial_registry = registry
            app.state.agent_run_manager = AgentRunManager()

            # Start background refresh loop
            refresh_task = asyncio.create_task(start_refresh_loop(runtime_dir=resolved_data_root / "runtime", store_registry=registry))

            yield
        finally:
            if refresh_task:
                refresh_task.cancel()
                try:
                    await refresh_task
                except asyncio.CancelledError:
                    pass
            await _close_dojo_client(client)
            reset = getattr(registry, "reset", None)
            if callable(reset):
                reset()

    app = FastAPI(title="DojoAgents Dashboard", lifespan=lifespan)
    app.state.config_store = store
    app.state.financial_registry = registry

    app.include_router(utility.router, prefix="/api/v1")
    app.include_router(market.router, prefix="/api/v1")
    app.include_router(sector.router, prefix="/api/v1")
    app.include_router(ticker.router, prefix="/api/v1")
    app.include_router(portfolio.router, prefix="/api/v1")
    app.include_router(dojo_core.router, prefix="/api/v1")
    app.include_router(dojo_folio.router, prefix="/api/v1")
    app.include_router(dojo_mesh.router, prefix="/api/v1")
    app.include_router(dojo_sphere.router, prefix="/api/v1")
    app.include_router(markets.router, prefix="/api/v1")
    app.include_router(sectors.router, prefix="/api/v1")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.add_middleware(PyInstrumentProfilerMiddleware)

    @app.get("/api/health")
    async def health() -> dict:
        return {"ok": True}

    @app.get("/api/config")
    async def config() -> dict:
        store = getattr(runtime, "config_store", None)
        if store is None:
            return {}
        return store.redacted()

    @app.put("/api/config")
    async def update_config(request: Request) -> Any:
        store = getattr(runtime, "config_store", None)
        if store is None:
            return JSONResponse(
                status_code=503,
                content={"error": "Configuration store not available"},
            )
        try:
            payload = await request.json()
        except Exception:
            return JSONResponse(
                status_code=422,
                content={"error": "Invalid JSON body"},
            )
        if not isinstance(payload, dict):
            return JSONResponse(
                status_code=422,
                content={"error": "Request body must be a JSON object"},
            )
        # Deep-merge payload into existing raw config, then save
        from dojoagents.config.loader import _deep_merge

        current_raw = store.raw()
        merged = _deep_merge(current_raw, payload)
        _sync_agent_model_with_default_provider(merged)
        try:
            store.save_raw(merged)
        except PermissionError as exc:
            return JSONResponse(
                status_code=403,
                content={
                    "error": f"Configuration file is not writable: {store.path}",
                    "detail": str(exc),
                },
            )
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
    async def chat(payload: dict[str, Any]) -> Any:
        try:
            req, info = _completion_request(payload)
        except ValueError as exc:
            return JSONResponse(status_code=422, content={"error": str(exc)})
        is_stream = info["stream"]
        model = info["model"]
        event_format = info.get("event_format", "openai.v1")
        _sync_runtime_agent_from_config(runtime, model)

        if is_stream:
            # SSE streaming mode
            queue: asyncio.Queue = asyncio.Queue()
            run_id = f"run-{uuid.uuid4().hex[:8]}"
            event_sink = make_event_queue_sink(queue, run_id=run_id, session_id=req.session_id)

            async def _stream_and_restore():
                try:
                    await runtime.agent.run(req, event_sink=event_sink)
                    await asyncio.sleep(0)
                    await queue.put(None)
                except Exception as exc:
                    await asyncio.sleep(0)
                    await queue.put(exc)
                    raise

            # Start agent run as background task
            task = asyncio.ensure_future(_stream_and_restore())

            async def _generate():
                try:
                    async for chunk_line in stream_completion_chunks(
                        queue,
                        model=model,
                        event_format=event_format,
                    ):
                        yield chunk_line
                finally:
                    if not task.done():
                        await task

            return StreamingResponse(
                _generate(),
                media_type="text/event-stream",
                headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
            )

        # Non-streaming mode
        dojo_extension = None
        sink: AgentEventSink | None = None
        if event_format == "dojo.v2":
            sink = AgentEventSink(run_id=f"run-{uuid.uuid4().hex[:8]}", session_id=req.session_id)
        response: AgentResponse = await runtime.agent.run(req, event_sink=sink)
        if sink is not None:
            dojo_extension = {
                "schema_version": "2.0",
                "run_id": sink.run_id,
                "events": sink.events,
            }
            response.metadata["dojo"] = dojo_extension
        openai_resp = ChatCompletionResponse.from_agent_response(response, model=model)
        body = openai_resp.to_dict()
        # Backward-compat: add legacy fields
        body["content"] = response.content
        body["session_id"] = response.session_id
        return body

    @app.post("/api/chat/runs")
    async def create_chat_run(payload: dict[str, Any]) -> Any:
        try:
            req, info = _completion_request(payload)
        except ValueError as exc:
            return JSONResponse(status_code=422, content={"error": str(exc)})
        manager: AgentRunManager = app.state.agent_run_manager
        _sync_runtime_agent_from_config(runtime, info.get("model", "default"))
        record = await manager.create_run(
            request=req,
            model=info.get("model", "default"),
            agent=runtime.agent,
        )
        return {
            "run_id": record.id,
            "session_id": record.session_id,
            "status": record.status,
            "model": record.model,
        }

    @app.get("/api/chat/sessions/{session_id}/tokens")
    async def get_chat_session_tokens(session_id: str) -> Any:
        from dojoagents.agent.token_ledger import SessionTokenState

        ledger = SessionTokenLedger()
        path = ledger._store.path_for(session_id)
        if not path.exists():
            return JSONResponse(status_code=404, content={"error": f"Unknown session: {session_id}"})
        raw = ledger._store._read_sync(path, session_id)
        if not isinstance(raw, dict):
            return JSONResponse(status_code=404, content={"error": f"Unknown session: {session_id}"})
        return SessionTokenState(**raw).snapshot()

    @app.get("/api/chat/runs/{run_id}")
    async def get_chat_run(run_id: str) -> Any:
        manager: AgentRunManager = app.state.agent_run_manager
        record = manager.get(run_id)
        if record is None:
            return JSONResponse(status_code=404, content={"error": f"Unknown run: {run_id}"})
        return {
            "run_id": record.id,
            "session_id": record.session_id,
            "status": record.status,
            "event_count": len(record.events),
            "model": record.model,
        }

    @app.post("/api/chat/runs/{run_id}/cancel")
    async def cancel_chat_run(run_id: str) -> Any:
        manager: AgentRunManager = app.state.agent_run_manager
        cancelled = await manager.cancel_run(run_id)
        if not cancelled:
            record = manager.get(run_id)
            if record is None:
                return JSONResponse(status_code=404, content={"error": f"Unknown run: {run_id}"})
            return JSONResponse(status_code=400, content={"error": f"Run is not active: {record.status}"})
        return {"cancelled": True}

    @app.get("/api/chat/runs/{run_id}/events")
    async def stream_chat_run_events(run_id: str, cursor: int = 0) -> Any:
        manager: AgentRunManager = app.state.agent_run_manager
        record = manager.get(run_id)
        if record is None:
            return JSONResponse(status_code=404, content={"error": f"Unknown run: {run_id}"})

        safe_cursor = max(0, cursor)

        async def _generate():
            index = safe_cursor
            while True:
                current = manager.get(run_id)
                if current is None:
                    yield f'data: {{"type":"error","message":"Unknown run: {run_id}"}}\n\n'
                    return

                while index < len(current.events):
                    yield f"data: {json.dumps(current.events[index], ensure_ascii=False)}\n\n"
                    index += 1

                if current.status != "running":
                    return

                _, status = await current.wait_for_events(index)
                if status != "running" and index >= len(current.events):
                    return

        return StreamingResponse(
            _generate(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    # Set up and auto-build frontend static files
    web_dir = Path(__file__).parent / "web"
    default_dist = web_dir / "dist"

    # Read target directory from env, default to web/dist
    target_static_dir_env = os.environ.get("DOJO_DASHBOARD_STATIC_DIR")
    target_static_dir = Path(target_static_dir_env) if target_static_dir_env else default_dist

    # Trigger auto-build
    try:
        setup_frontend_static_files(source_dir=web_dir, target_dir=target_static_dir)
    except Exception as e:
        import logging

        logging.getLogger(__name__).error(f"Frontend auto-build failed: {e}")

    # Use target_static_dir as primary, fallback to static/ if not built properly
    static_dir = target_static_dir
    if not static_dir.is_dir():
        static_dir = Path(__file__).parent / "static"

    if static_dir.is_dir():
        assets_dir = static_dir / "assets"
        if assets_dir.is_dir():
            app.mount("/assets", StaticFiles(directory=assets_dir), name="static-assets")

        canvas_template_path = static_dir / "canvas-template.html"
        if canvas_template_path.is_file():

            @app.get("/canvas-template.html")
            async def serve_canvas_template():
                return FileResponse(canvas_template_path)

        index_path = static_dir / "index.html"
        if index_path.is_file():

            @app.get("/")
            async def serve_spa():
                return FileResponse(index_path)

    return app
