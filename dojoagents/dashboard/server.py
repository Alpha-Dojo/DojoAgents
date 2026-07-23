from __future__ import annotations

import asyncio
import inspect
import json
import os
import uuid
from contextlib import asynccontextmanager
from dataclasses import asdict, is_dataclass, replace
from pathlib import Path
from typing import Any

from dojoagents.dashboard.routers import chat_sessions
from dojoagents.dashboard.frontend_builder import setup_frontend_static_files
from dojoagents.dashboard.agent_runs import AgentRunManager, validate_request_modalities
from fastapi import Depends, FastAPI, Request
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
from dojoagents.dashboard.sse import (
    make_event_queue_sink,
    stream_completion_chunks,
    stream_persisted_run_events,
)
from dojoagents.dashboard.auth import get_session_principal
from dojoagents.sessions.models import SessionPrincipal
from dojoagents.config.loader import resolve_provider_config
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
    clean_provider_name = provider_name.strip() if provider_name else None
    selected_provider, provider_cfg = resolve_provider_config(config.llm_provider, requested_name=clean_provider_name)
    if provider_cfg is None:
        fallback = provider_name or getattr(config.llm_provider, "default", None)
        return (fallback or "default").strip()

    if selected_provider == "gemini":
        llm_provider = GeminiNativeProvider(
            api_key=provider_cfg.api_key,
            api_key_env=provider_cfg.api_key_env,
            base_url=provider_cfg.base_url,
        )
    else:
        llm_provider = OpenAICompatibleProvider(
            api_key=provider_cfg.api_key,
            base_url=provider_cfg.base_url,
            author=provider_cfg.author,
        )
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


def _decode_request_context(surface: Any, value: Any) -> Any:
    decoder = getattr(surface, "decode_request_context", None)
    return decoder(value) if callable(decoder) else value


def _chat_request(
    payload: dict[str, Any],
    *,
    surface: Any = None,
) -> ChatRequest:
    quant = payload.get("quant")
    quant = _decode_request_context(surface, quant)
    return ChatRequest(
        message=payload["message"],
        user_id=payload["user_id"],
        session_id=payload["session_id"],
        channel=payload.get("channel", "dashboard"),
        quant=quant,
        metadata=dict(payload.get("metadata", {})),
    )


def _normalize_openai_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    from dojoagents.agent.multimodal import normalize_openai_message_content, openai_content_has_payload

    normalized: list[dict[str, Any]] = []
    for message in messages:
        role = str(message.get("role") or "").strip()
        if not role:
            continue
        content = normalize_openai_message_content(message.get("content"))
        if role in {"user", "assistant"} and not openai_content_has_payload(content):
            continue
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


def _completion_request(
    payload: dict[str, Any],
    *,
    surface: Any = None,
) -> tuple[ChatRequest, dict[str, Any]]:
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

        from dojoagents.agent.multimodal import openai_content_has_payload, openai_content_text

        last_user_index = -1
        last_user_msg = ""
        last_user_content: str | list[dict[str, Any]] = ""
        for idx in range(len(messages) - 1, -1, -1):
            msg = messages[idx]
            if msg.get("role") == "user":
                content = msg.get("content")
                if not openai_content_has_payload(content):
                    continue
                last_user_index = idx
                last_user_content = content if isinstance(content, list) else str(content or "")
                last_user_msg = openai_content_text(content)
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

        quant = _decode_request_context(surface, metadata.get("quant"))
        metadata["history"] = messages[:last_user_index]
        metadata["user_content"] = last_user_content
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
        req = _chat_request(payload, surface=surface)
        req.metadata.setdefault("locale", payload.get("locale", "zh"))
        req.metadata.setdefault("event_format", "openai.v1")
        return req, {"stream": False, "model": "default", "messages": [{"role": "user", "content": req.message}], "event_format": "openai.v1"}


async def _run_agent(runtime: Any, req: ChatRequest, event_sink: AgentEventSink | None = None) -> AgentResponse:
    from dojoagents.tasks.runtime_helpers import run_agent_with_tasks

    async def _inner(request: ChatRequest, *, event_sink: AgentEventSink | None = None) -> AgentResponse:
        run = runtime.agent.run
        if event_sink is None:
            return await run(request)
        try:
            signature = inspect.signature(run)
        except (TypeError, ValueError):
            return await run(request, event_sink=event_sink)
        accepts_event_sink = "event_sink" in signature.parameters or any(param.kind is inspect.Parameter.VAR_KEYWORD for param in signature.parameters.values())
        if accepts_event_sink:
            return await run(request, event_sink=event_sink)
        return await run(request)

    return await run_agent_with_tasks(
        runtime,
        req,
        run_agent=_inner,
        event_sink=event_sink,
    )


def create_app(  # noqa: C901
    runtime: Any,
    *,
    dashboard_surface: Any | None = None,
) -> FastAPI:
    if dashboard_surface is None:
        try:
            dashboard_surface = runtime.surface("dashboard")
        except (AttributeError, KeyError, RuntimeError):
            dashboard_surface = None
    configure_surface = getattr(
        dashboard_surface,
        "configure_runtime",
        None,
    )
    if callable(configure_surface):
        configure_surface(runtime)
    store = getattr(runtime, "config_store", None)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        from dojoagents.dashboard.auth import LegacyLocalPrincipalProvider

        app.state.config_store = getattr(runtime, "config_store", None)
        app.state.agent_run_manager = AgentRunManager()
        app.state.principal_provider = LegacyLocalPrincipalProvider()
        surface_lifespan = getattr(dashboard_surface, "lifespan", None)
        if not callable(surface_lifespan):
            yield
            return
        async with surface_lifespan(app, runtime):
            yield

    app = FastAPI(title="DojoAgents Dashboard", lifespan=lifespan)
    app.state.runtime = runtime
    app.state.config_store = store
    from dojoagents.dashboard.auth import LegacyLocalPrincipalProvider

    app.state.principal_provider = LegacyLocalPrincipalProvider()

    if dashboard_surface is not None:
        for router in dashboard_surface.routers():
            app.include_router(router, prefix="/api/v1")
    app.include_router(chat_sessions.router, prefix="/api/v1")

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
        restart_paths = (
            ("harness",),
            ("sessions", "store"),
            ("sessions", "blob_store"),
            ("sessions", "runtime", "require_user_id"),
            ("sessions", "runtime", "lease_seconds"),
            ("sessions", "runtime", "heartbeat_seconds"),
        )

        def _at_path(data: dict[str, Any], path: tuple[str, ...]) -> Any:
            current: Any = data
            for key in path:
                if not isinstance(current, dict) or key not in current:
                    return None
                current = current[key]
            return current

        requires_restart = any(_at_path(current_raw, path) != _at_path(merged, path) for path in restart_paths)
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
        response = store.redacted()
        response["requires_restart"] = requires_restart
        return response

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
            req, info = _completion_request(
                payload,
                surface=dashboard_surface,
            )
        except ValueError as exc:
            return JSONResponse(status_code=422, content={"error": str(exc)})
        is_stream = info["stream"]
        model = info["model"]
        event_format = info.get("event_format", "openai.v1")
        _sync_runtime_agent_from_config(runtime, model)
        sessions = getattr(runtime, "sessions", None)
        try:
            await validate_request_modalities(req, runtime.agent)
        except ValueError as exc:
            return JSONResponse(status_code=422, content={"error": str(exc)})

        if is_stream:
            # SSE streaming mode
            queue: asyncio.Queue = asyncio.Queue()
            run_id = f"run-{uuid.uuid4().hex[:8]}"
            event_sink = make_event_queue_sink(queue, run_id=run_id, session_id=req.session_id)
            session_handle = None
            if sessions is not None:
                session_handle = await sessions.begin_run(req, model=model, run_id=run_id)

            async def _stream_and_restore():
                try:
                    response = await _run_agent(runtime, req, event_sink=event_sink)
                    if sessions is not None and session_handle is not None:
                        await sessions.finish_run(session_handle, response, events=event_sink.events)
                    await asyncio.sleep(0)
                    await queue.put(None)
                except Exception as exc:
                    if sessions is not None and session_handle is not None:
                        await sessions.fail_run(session_handle, str(exc))
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
        run_id = f"run-{uuid.uuid4().hex[:8]}"
        if event_format == "dojo.v2":
            sink = AgentEventSink(run_id=run_id, session_id=req.session_id)
        session_handle = None
        if sessions is not None:
            session_handle = await sessions.begin_run(req, model=model, run_id=run_id)
        try:
            response: AgentResponse = await _run_agent(runtime, req, event_sink=sink)
        except Exception as exc:
            if sessions is not None and session_handle is not None:
                await sessions.fail_run(session_handle, str(exc))
            raise
        if sessions is not None and session_handle is not None:
            await sessions.finish_run(session_handle, response, events=(sink.events if sink is not None else []))
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
    async def create_chat_run(
        payload: dict[str, Any],
        principal: SessionPrincipal = Depends(get_session_principal),
    ) -> Any:
        try:
            req, info = _completion_request(
                payload,
                surface=dashboard_surface,
            )
        except ValueError as exc:
            return JSONResponse(status_code=422, content={"error": str(exc)})
        req = replace(req, principal=principal, user_id=principal.user_id)
        manager: AgentRunManager = app.state.agent_run_manager
        _sync_runtime_agent_from_config(runtime, info.get("model", "default"))
        sessions = getattr(runtime, "sessions", None)
        canonical_sessions = sessions is not None and hasattr(sessions, "history")
        session_handle_ref: dict[str, Any] = {}

        async def _on_started(record: Any) -> None:
            if sessions is None or canonical_sessions:
                return
            session_handle_ref["handle"] = await sessions.begin_run(req, model=info.get("model", "default"), run_id=record.id)

        async def _on_completed(record: Any, response: AgentResponse) -> None:
            if sessions is None or canonical_sessions:
                return
            handle = session_handle_ref.get("handle")
            if handle is not None:
                await sessions.finish_run(handle, response, events=record.events)

        async def _on_failed(record: Any, exc: Exception) -> None:
            if sessions is None or canonical_sessions:
                return
            handle = session_handle_ref.get("handle")
            if handle is not None:
                await sessions.fail_run(handle, str(exc))

        async def _on_cancelled(record: Any) -> None:
            if sessions is None or canonical_sessions:
                return
            handle = session_handle_ref.get("handle")
            if handle is not None:
                await sessions.cancel_run(handle)

        try:
            record = await manager.create_run(
                request=req,
                model=info.get("model", "default"),
                agent=runtime.agent,
                runtime=runtime,
                on_started=_on_started,
                on_completed=_on_completed,
                on_failed=_on_failed,
                on_cancelled=_on_cancelled,
            )
        except ValueError as exc:
            return JSONResponse(status_code=422, content={"error": str(exc)})
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
    async def get_chat_run(
        run_id: str,
        principal: SessionPrincipal = Depends(get_session_principal),
    ) -> Any:
        service = getattr(runtime, "session_service", None)
        if service is not None:
            try:
                record = await service.get_run(principal, run_id)
            except Exception:
                return JSONResponse(status_code=404, content={"error": f"Unknown run: {run_id}"})
            return {
                "run_id": record.run_id,
                "status": record.status,
                "model": record.model,
                "metadata": {},
            }
        manager: AgentRunManager = app.state.agent_run_manager
        record = manager.get(run_id)
        if record is None:
            return JSONResponse(status_code=404, content={"error": f"Unknown run: {run_id}"})
        return record.to_status_dict()

    @app.post("/api/chat/runs/{run_id}/cancel")
    async def cancel_chat_run(
        run_id: str,
        principal: SessionPrincipal = Depends(get_session_principal),
    ) -> Any:
        service = getattr(runtime, "session_service", None)
        if service is not None:
            try:
                await service.request_cancel(principal, run_id)
            except Exception:
                return JSONResponse(status_code=404, content={"error": f"Unknown run: {run_id}"})
            return {"cancelled": True}
        manager: AgentRunManager = app.state.agent_run_manager
        cancelled = await manager.cancel_run(run_id)
        if not cancelled:
            record = manager.get(run_id)
            if record is None:
                return JSONResponse(status_code=404, content={"error": f"Unknown run: {run_id}"})
            return JSONResponse(status_code=400, content={"error": f"Run is not active: {record.status}"})
        return {"cancelled": True}

    @app.get("/api/chat/runs/{run_id}/events")
    async def stream_chat_run_events(
        run_id: str,
        cursor: int = 0,
        principal: SessionPrincipal = Depends(get_session_principal),
    ) -> Any:
        service = getattr(runtime, "session_service", None)
        if service is not None:
            try:
                await service.get_run(principal, run_id)
            except Exception:
                return JSONResponse(status_code=404, content={"error": f"Unknown run: {run_id}"})

            async def _persisted():
                async for event in stream_persisted_run_events(service, principal, run_id, after_seq=max(0, cursor)):
                    yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

            return StreamingResponse(_persisted(), media_type="text/event-stream")
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

        favicon_path = static_dir / "favicon.svg"
        if favicon_path.is_file():

            @app.get("/favicon.svg")
            async def serve_favicon():
                return FileResponse(favicon_path, media_type="image/svg+xml")

        index_path = static_dir / "index.html"
        if index_path.is_file():

            @app.get("/")
            async def serve_spa():
                return FileResponse(index_path)

    return app
