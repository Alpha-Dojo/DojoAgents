from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, Request, UploadFile
from fastapi.responses import JSONResponse

from dojoagents.dashboard.schemas.chat_sessions import ChatSessionExportRequest
from dojoagents.dashboard.schemas.session_inputs import (
    SessionInputRevealResponse,
    SessionInputsResponse,
    SessionInputUploadResponse,
)
from dojoagents.dashboard.schemas.session_outputs import SessionOutputRevealResponse, SessionOutputsResponse
from dojoagents.dashboard.services.session_inputs import (
    list_session_input_files,
    resolve_session_input_file,
    reveal_session_input_file,
    save_session_input_file,
)
from dojoagents.dashboard.services.session_outputs import (
    list_session_output_files,
    resolve_session_output_file,
    reveal_path_in_file_manager,
)
from dojoagents.logging import LOGGER

router = APIRouter(prefix="/chat/sessions", tags=["chat-sessions"])


def _session_manager(request: Request) -> Any:
    runtime = getattr(request.app.state, "runtime", None)
    sessions = getattr(runtime, "sessions", None)
    if sessions is None:
        raise RuntimeError("session manager is not initialized")
    return sessions


def _sessions_root(request: Request) -> Path:
    store = getattr(request.app.state, "config_store", None)
    if store is None:
        runtime = getattr(request.app.state, "runtime", None)
        store = getattr(runtime, "config_store", None)
    if store is None:
        raise RuntimeError("config store is not initialized")
    return Path(store.snapshot().sessions.root).expanduser().resolve()


@router.get("")
async def list_chat_sessions(
    request: Request,
    limit: int = 50,
    cursor: str | None = None,
    include_archived: bool = False,
) -> Any:
    sessions = _session_manager(request)
    result = await sessions.list_sessions(limit=limit, cursor=cursor, include_archived=include_archived)
    return {"sessions": [asdict(item) for item in result.sessions], "next_cursor": result.next_cursor}


@router.get("/{session_id}")
async def get_chat_session(request: Request, session_id: str) -> Any:
    sessions = _session_manager(request)
    result = await sessions.get_session(session_id)
    if result is None:
        return JSONResponse(status_code=404, content={"error": f"Unknown session: {session_id}"})
    return asdict(result)


@router.get("/{session_id}/messages")
async def get_chat_session_messages(
    request: Request,
    session_id: str,
    limit: int = 200,
    offset: int = 0,
) -> Any:
    sessions = _session_manager(request)
    if await sessions.get_session(session_id) is None:
        return JSONResponse(status_code=404, content={"error": f"Unknown session: {session_id}"})
    result = await sessions.get_messages(session_id, limit=limit, offset=offset)
    return {
        "session_id": result.session_id,
        "agent_id": result.agent_id,
        "messages": [asdict(item) for item in result.messages],
        "next_offset": result.next_offset,
    }


@router.post("/{session_id}/archive")
async def archive_chat_session(request: Request, session_id: str) -> Any:
    sessions = _session_manager(request)
    archived = await sessions.archive_session(session_id)
    if not archived:
        return JSONResponse(status_code=404, content={"error": f"Unknown session: {session_id}"})
    return {"archived": True, "session_id": session_id}


@router.post("/export")
async def export_chat_sessions(request: Request, payload: ChatSessionExportRequest) -> Any:
    sessions = _session_manager(request)
    result = await sessions.export_all(payload.model_dump())
    return asdict(result)


@router.get("/{session_id}/outputs", response_model=SessionOutputsResponse)
async def get_chat_session_outputs(request: Request, session_id: str) -> Any:
    try:
        payload = list_session_output_files(_sessions_root(request), session_id)
    except ValueError as exc:
        return JSONResponse(status_code=400, content={"error": str(exc)})
    return payload


@router.post("/{session_id}/outputs/{filename}/reveal", response_model=SessionOutputRevealResponse)
async def reveal_chat_session_output(
    request: Request,
    session_id: str,
    filename: str,
) -> Any:
    try:
        target = resolve_session_output_file(_sessions_root(request), session_id, filename)
    except ValueError as exc:
        return JSONResponse(status_code=400, content={"error": str(exc)})

    if not target.is_file():
        return JSONResponse(status_code=404, content={"error": f"Output file not found: {filename}"})

    try:
        reveal_path_in_file_manager(target)
    except FileNotFoundError as exc:
        return JSONResponse(status_code=404, content={"error": str(exc)})
    except Exception as exc:
        LOGGER.exception("Failed to reveal session output %s for session %s", filename, session_id)
        return JSONResponse(status_code=500, content={"error": str(exc)})

    return SessionOutputRevealResponse(path=str(target))


@router.get("/{session_id}/inputs", response_model=SessionInputsResponse)
async def get_chat_session_inputs(request: Request, session_id: str) -> Any:
    try:
        payload = list_session_input_files(_sessions_root(request), session_id)
    except ValueError as exc:
        return JSONResponse(status_code=400, content={"error": str(exc)})
    return payload


@router.post("/{session_id}/inputs", response_model=SessionInputUploadResponse)
async def upload_chat_session_input(
    request: Request,
    session_id: str,
    file: UploadFile = File(...),
    overwrite: bool = False,
) -> Any:
    try:
        content = await file.read()
        payload = save_session_input_file(
            _sessions_root(request),
            session_id,
            file.filename or "upload.bin",
            content,
            overwrite=overwrite,
        )
    except ValueError as exc:
        return JSONResponse(status_code=400, content={"error": str(exc)})

    return SessionInputUploadResponse(file=payload)


@router.post("/{session_id}/inputs/{filename}/reveal", response_model=SessionInputRevealResponse)
async def reveal_chat_session_input(
    request: Request,
    session_id: str,
    filename: str,
) -> Any:
    try:
        target = resolve_session_input_file(_sessions_root(request), session_id, filename)
    except ValueError as exc:
        return JSONResponse(status_code=400, content={"error": str(exc)})

    if not target.is_file():
        return JSONResponse(status_code=404, content={"error": f"Input file not found: {filename}"})

    try:
        reveal_session_input_file(target)
    except FileNotFoundError as exc:
        return JSONResponse(status_code=404, content={"error": str(exc)})
    except Exception as exc:
        LOGGER.exception("Failed to reveal session input %s for session %s", filename, session_id)
        return JSONResponse(status_code=500, content={"error": str(exc)})

    return SessionInputRevealResponse(path=str(target))
