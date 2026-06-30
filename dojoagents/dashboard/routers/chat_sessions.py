from __future__ import annotations

from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from dojoagents.dashboard.schemas.chat_sessions import ChatSessionExportRequest

router = APIRouter(prefix="/chat/sessions", tags=["chat-sessions"])


def _session_manager(request: Request) -> Any:
    runtime = getattr(request.app.state, "runtime", None)
    sessions = getattr(runtime, "sessions", None)
    if sessions is None:
        raise RuntimeError("session manager is not initialized")
    return sessions


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
