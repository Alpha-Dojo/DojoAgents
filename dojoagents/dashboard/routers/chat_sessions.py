from __future__ import annotations

from pathlib import Path
from typing import Any
from dataclasses import asdict
from datetime import UTC, datetime
from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse

from dojoagents.dashboard.deps import get_chat_session_service
from dojoagents.dashboard.auth import get_session_principal
from dojoagents.dashboard.services.chat_session_service import ChatSessionService
from dojoagents.dashboard.schemas.chat_sessions import (
    ArchiveChatSessionResponse,
    ChatSessionExportRequest,
    ChatSessionExportResponse,
    ChatSessionListResponse,
    ChatSessionMessagesResponse,
    ChatSessionSummaryResponse,
)
from dojoagents.dashboard.schemas.session_inputs import (
    SessionInputRevealResponse,
    SessionInputsResponse,
    SessionInputUploadResponse,
)
from dojoagents.dashboard.schemas.session_outputs import SessionOutputRevealResponse, SessionOutputsResponse
from dojoagents.dashboard.services.session_inputs import (
    list_session_input_files,
    reveal_session_input_file,
    save_session_input_file,
)
from dojoagents.dashboard.services.session_outputs import (
    list_session_output_files,
    resolve_session_output_file,
    reveal_path_in_file_manager,
)
from dojoagents.logging import LOGGER
from dojoagents.sessions.errors import SessionNotFoundError
from dojoagents.sessions.models import (
    ContextUsageQuery,
    ObjectQuery,
    SessionPrincipal,
    UsageQuery,
)
from dojoagents.agent.context_usage import context_snapshot_projection
from dojoagents.sessions.paths import resolve_session_input_file

router = APIRouter(prefix="/chat/sessions", tags=["chat-sessions"])


def _sessions_root(request: Request) -> Path:
    store = getattr(request.app.state, "config_store", None)
    if store is None:
        runtime = getattr(request.app.state, "runtime", None)
        store = getattr(runtime, "config_store", None)
    if store is None:
        raise RuntimeError("config store is not initialized")
    return Path(store.snapshot().sessions.root).expanduser().resolve()


@router.get("", response_model=ChatSessionListResponse)
async def list_chat_sessions(
    limit: int = 50,
    cursor: str | None = None,
    include_archived: bool = False,
    service: ChatSessionService = Depends(get_chat_session_service),
    principal: SessionPrincipal = Depends(get_session_principal),
) -> Any:
    return (
        await service.scoped(principal).list_sessions(limit=limit, cursor=cursor, include_archived=include_archived)
        if service.canonical_backend
        else await service.list_sessions(limit=limit, cursor=cursor, include_archived=include_archived)
    )


@router.get("/{session_id}", response_model=ChatSessionSummaryResponse)
async def get_chat_session(
    session_id: str,
    service: ChatSessionService = Depends(get_chat_session_service),
    principal: SessionPrincipal = Depends(get_session_principal),
) -> Any:
    if service.canonical_backend:
        service = service.scoped(principal)
    result = await service.get_session(session_id)
    if result is None:
        return JSONResponse(status_code=404, content={"error": f"Unknown session: {session_id}"})
    return result


@router.get("/{session_id}/usage")
async def get_chat_session_usage(
    session_id: str,
    run_id: str | None = None,
    turn_id: str | None = None,
    provider: str | None = None,
    model: str | None = None,
    category: str | None = None,
    quality: str | None = None,
    status: str | None = None,
    agent_id: str | None = None,
    from_time: datetime | None = None,
    to_time: datetime | None = None,
    include_children: bool = True,
    group_by: str = "",
    include_records: bool = False,
    limit: int = 100,
    cursor: str | None = None,
    view: str = "all",
    context_scope: str = "latest",
    context_detail: str = "category",
    context_limit: int = 50,
    context_cursor: str | None = None,
    service: ChatSessionService = Depends(get_chat_session_service),
    principal: SessionPrincipal = Depends(get_session_principal),
) -> Any:
    if not service.canonical_backend:
        raise HTTPException(
            status_code=501,
            detail="usage aggregation requires the canonical SessionService",
        )
    if view not in {"all", "consumption", "context"}:
        raise HTTPException(
            status_code=422,
            detail="view must be all, consumption, or context",
        )
    if context_scope not in {
        "latest",
        "turn_last",
        "turn_peak",
        "session_peak",
        "history",
    }:
        raise HTTPException(
            status_code=422,
            detail=("context_scope must be latest, turn_last, turn_peak, " "session_peak, or history"),
        )
    dimensions = tuple(item.strip() for item in group_by.split(",") if item.strip())
    if from_time is not None and from_time.tzinfo is not None:
        from_time = from_time.astimezone(UTC)
    if to_time is not None and to_time.tzinfo is not None:
        to_time = to_time.astimezone(UTC)
    try:
        summary = None
        turn_summary = None
        if view in {"all", "consumption"}:
            query = UsageQuery(
                run_id=run_id,
                turn_id=turn_id,
                provider=provider,
                model=model,
                category=category,
                quality=quality,
                status=status,
                agent_id=agent_id,
                from_time=from_time,
                to_time=to_time,
                include_children=include_children,
                include_records=include_records,
                group_by=dimensions,
                limit=limit,
                cursor=cursor,
            )
            summary = await service.session_manager.usage(
                principal,
                session_id,
                query,
            )
            turn_summary = await service.session_manager.usage(
                principal,
                session_id,
                UsageQuery(
                    run_id=run_id,
                    turn_id=turn_id,
                    provider=provider,
                    model=model,
                    category=category,
                    quality=quality,
                    status=status,
                    agent_id=agent_id,
                    from_time=from_time,
                    to_time=to_time,
                    include_children=include_children,
                    include_records=False,
                    group_by=("turn_id", "run_id"),
                    limit=1,
                ),
            )
        context_summary = None
        if view in {"all", "context"}:
            context_summary = await service.session_manager.context_usage(
                principal,
                session_id,
                ContextUsageQuery(
                    run_id=run_id,
                    turn_id=turn_id,
                    provider=provider,
                    model=model,
                    agent_id=agent_id,
                    from_time=from_time,
                    to_time=to_time,
                    include_children=include_children,
                    include_history=context_scope == "history",
                    detail=context_detail,
                    limit=context_limit,
                    cursor=context_cursor,
                ),
            )
    except SessionNotFoundError:
        return JSONResponse(
            status_code=404,
            content={"error": f"Unknown session: {session_id}"},
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    consumption = None
    if summary is not None and turn_summary is not None:
        consumption = {
            "totals": {
                "input_tokens": summary.input_tokens,
                "output_tokens": summary.output_tokens,
                "total_tokens": summary.total_tokens,
                "reasoning_tokens": summary.reasoning_tokens,
                "cache_read_tokens": summary.cache_read_tokens,
                "cache_write_tokens": summary.cache_write_tokens,
                "calls": summary.calls,
                "cost_microunits": summary.cost_microunits,
            },
            "groups": [asdict(group) for group in summary.groups],
            "turns": [
                {
                    **group.dimensions,
                    "totals": asdict(group.totals),
                }
                for group in turn_summary.groups
            ],
            "coverage": {
                "actual_calls": summary.actual_calls,
                "estimated_calls": summary.estimated_calls,
                "unavailable_calls": summary.unavailable_calls,
                "has_legacy_unattributed": (summary.has_legacy_unattributed),
                "tracking_started_at": (summary.tracking_started_at.isoformat() if summary.tracking_started_at is not None else None),
            },
            "records": [asdict(record) for record in summary.records],
            "next_cursor": summary.next_cursor,
        }

    context = None
    if context_summary is not None:
        latest = context_snapshot_projection(
            context_summary.latest,
            detail=context_detail,
        )
        context = {
            "latest": latest,
            "turn_peak": context_snapshot_projection(
                context_summary.turn_peak,
                detail=context_detail,
            ),
            "session_peak": context_snapshot_projection(
                context_summary.session_peak,
                detail=context_detail,
            ),
            "history": [
                context_snapshot_projection(
                    snapshot,
                    detail=context_detail,
                )
                for snapshot in context_summary.history
            ],
            "next_cursor": context_summary.next_cursor,
            "has_breakdown": latest is not None,
        }

    return {
        "schema_version": 3,
        "session_id": session_id,
        "filters": {
            "run_id": run_id,
            "turn_id": turn_id,
            "provider": provider,
            "model": model,
            "category": category,
            "quality": quality,
            "status": status,
            "agent_id": agent_id,
            "from_time": from_time.isoformat() if from_time else None,
            "to_time": to_time.isoformat() if to_time else None,
            "include_children": include_children,
            "group_by": list(dimensions),
            "view": view,
            "context_scope": context_scope,
            "context_detail": context_detail,
        },
        "consumption": consumption,
        "context": context,
    }


@router.get("/{session_id}/messages", response_model=ChatSessionMessagesResponse)
async def get_chat_session_messages(
    session_id: str,
    limit: int = 200,
    offset: int = 0,
    service: ChatSessionService = Depends(get_chat_session_service),
    principal: SessionPrincipal = Depends(get_session_principal),
) -> Any:
    if service.canonical_backend:
        service = service.scoped(principal)
    result = await service.get_messages(session_id, limit=limit, offset=offset)
    if result is None:
        return JSONResponse(status_code=404, content={"error": f"Unknown session: {session_id}"})
    turns = await service.get_turns(session_id) if offset == 0 else []
    result.turns = turns
    return result


@router.post("/{session_id}/archive", response_model=ArchiveChatSessionResponse)
async def archive_chat_session(
    session_id: str,
    service: ChatSessionService = Depends(get_chat_session_service),
    principal: SessionPrincipal = Depends(get_session_principal),
) -> Any:
    if service.canonical_backend:
        service = service.scoped(principal)
    result = await service.archive_session(session_id)
    if result is None:
        return JSONResponse(status_code=404, content={"error": f"Unknown session: {session_id}"})
    return result


@router.post("/export", response_model=ChatSessionExportResponse)
async def export_chat_sessions(
    payload: ChatSessionExportRequest,
    service: ChatSessionService = Depends(get_chat_session_service),
    principal: SessionPrincipal = Depends(get_session_principal),
) -> Any:
    if service.canonical_backend:
        service = service.scoped(principal)
    return await service.export_sessions(payload)


@router.get("/{session_id}/outputs", response_model=SessionOutputsResponse)
async def get_chat_session_outputs(
    request: Request,
    session_id: str,
    service: ChatSessionService = Depends(get_chat_session_service),
    principal: SessionPrincipal = Depends(get_session_principal),
) -> Any:
    if service.canonical_backend:
        scoped = service.scoped(principal)
        if await scoped.get_session(session_id) is None:
            return JSONResponse(status_code=404, content={"error": f"Unknown session: {session_id}"})
        page = await service.session_manager.list_objects(principal, session_id, ObjectQuery(kind="output", status="committed", limit=200))
        return {
            "session_id": session_id,
            "output_dir": "",
            "files": [
                {
                    "filename": item.name,
                    "object_id": item.object_id,
                    "bytes_written": item.blob_ref.size_bytes if item.blob_ref else 0,
                    "updated_at": item.updated_at.isoformat(),
                }
                for item in page.items
            ],
        }
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
async def get_chat_session_inputs(
    request: Request,
    session_id: str,
    service: ChatSessionService = Depends(get_chat_session_service),
    principal: SessionPrincipal = Depends(get_session_principal),
) -> Any:
    if service.canonical_backend:
        scoped = service.scoped(principal)
        if await scoped.get_session(session_id) is None:
            return JSONResponse(status_code=404, content={"error": f"Unknown session: {session_id}"})
        page = await service.session_manager.list_objects(principal, session_id, ObjectQuery(kind="input", status="committed", limit=200))
        return {
            "session_id": session_id,
            "input_dir": "",
            "files": [
                {
                    "filename": item.name,
                    "object_id": item.object_id,
                    "bytes": item.blob_ref.size_bytes if item.blob_ref else 0,
                    "kind": item.content_type,
                    "updated_at": item.updated_at.isoformat(),
                }
                for item in page.items
            ],
        }
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
    service: ChatSessionService = Depends(get_chat_session_service),
    principal: SessionPrincipal = Depends(get_session_principal),
) -> Any:
    if service.canonical_backend:
        scoped = service.scoped(principal)
        if await scoped.get_session(session_id) is None:
            return JSONResponse(status_code=404, content={"error": f"Unknown session: {session_id}"})
        content = await file.read()
        record = await service.session_manager.write_named_object(
            principal,
            session_id,
            kind="input",
            name=file.filename or "upload.bin",
            content_type=file.content_type or "application/octet-stream",
            data=content,
            metadata={"overwrite": overwrite},
        )
        return {
            "ok": True,
            "file": {
                "filename": record.name,
                "object_id": record.object_id,
                "bytes": len(content),
                "kind": record.content_type,
                "updated_at": record.updated_at.isoformat(),
            },
        }
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
