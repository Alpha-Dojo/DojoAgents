from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from dojoagents.agent.models import (
    AgentResponse,
    ChatCompletionResponse,
    ChatRequest,
)
from dojoagents.dashboard.sse import make_stream_delta_callback, stream_completion_chunks
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
        messages = payload["messages"]
        last_user_msg = ""
        for msg in reversed(messages):
            if msg.get("role") == "user":
                content = msg.get("content", "")
                last_user_msg = content if isinstance(content, str) else str(content)
                break

        user_id = payload.get("user", metadata.get("user_id", "anonymous"))
        session_id = metadata.get("session_id", uuid.uuid4().hex)
        channel = metadata.get("channel", "dashboard")
        stream = payload.get("stream", False)
        model = payload.get("model", "default")

        quant_data = metadata.get("quant")
        quant = QuantContext(**quant_data) if isinstance(quant_data, dict) else None

        req = ChatRequest(
            message=last_user_msg,
            user_id=user_id,
            session_id=session_id,
            channel=channel,
            quant=quant,
            metadata=metadata,
        )
        return req, {"stream": stream, "model": model, "messages": messages}
    else:
        # Legacy format
        req = _chat_request(payload)
        return req, {"stream": False, "model": "default", "messages": [{"role": "user", "content": req.message}]}


def create_app(runtime: Any) -> FastAPI:
    app = FastAPI(title="DojoAgents Dashboard")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

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
        store.save_raw(merged)
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
        req, info = _completion_request(payload)
        is_stream = info["stream"]
        model = info["model"]

        if is_stream:
            # SSE streaming mode
            queue: asyncio.Queue = asyncio.Queue()
            callback = make_stream_delta_callback(queue)

            # Attach callback to agent loop dynamically
            agent_loop = runtime.agent
            prev_callback = getattr(agent_loop, "stream_delta_callback", None)
            agent_loop.stream_delta_callback = callback

            async def _stream_and_restore():
                try:
                    response: AgentResponse = await agent_loop.run(req)
                    # Yield to let call_soon_threadsafe callbacks drain
                    await asyncio.sleep(0)
                    await queue.put(None)
                    return response
                except Exception as exc:
                    await asyncio.sleep(0)
                    await queue.put(exc)
                    raise

            # Start agent run as background task
            task = asyncio.ensure_future(_stream_and_restore())

            async def _generate():
                try:
                    async for chunk_line in stream_completion_chunks(queue, model=model):
                        yield chunk_line
                finally:
                    # Restore previous callback
                    agent_loop.stream_delta_callback = prev_callback
                    # Ensure task is done
                    if not task.done():
                        await task

            return StreamingResponse(
                _generate(),
                media_type="text/event-stream",
                headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
            )

        # Non-streaming mode
        response: AgentResponse = await runtime.agent.run(req)
        openai_resp = ChatCompletionResponse.from_agent_response(response, model=model)
        body = openai_resp.to_dict()
        # Backward-compat: add legacy fields
        body["content"] = response.content
        body["session_id"] = response.session_id
        return body

    # Serve built frontend SPA from dashboard/web/dist if present; otherwise fall back to static/
    static_dir = Path(__file__).parent / "web" / "dist"
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
