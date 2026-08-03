from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse

from dojoagents.dashboard.schemas.memory import ClearGeneratedMemoryResponse
from dojoagents.dashboard.services.generated_memory_service import (
    GeneratedMemoryService,
    UnsafeGeneratedMemoryPathError,
)
from dojoagents.logging import LOGGER

router = APIRouter(prefix="/memory", tags=["memory"])


@router.delete("/generated-skills", response_model=ClearGeneratedMemoryResponse)
async def clear_generated_memory(request: Request) -> Any:
    store = getattr(request.app.state, "config_store", None)
    if store is None:
        return JSONResponse(
            status_code=503,
            content={"error": "Configuration store not available"},
        )

    generated_skill_dir = store.snapshot().memory.generated_skill_dir
    service = GeneratedMemoryService(generated_skill_dir)
    try:
        directory, deleted_count = await run_in_threadpool(service.clear)
    except UnsafeGeneratedMemoryPathError as exc:
        return JSONResponse(status_code=400, content={"error": str(exc)})
    except OSError as exc:
        LOGGER.exception("Failed to clear generated memory directory %s", generated_skill_dir)
        return JSONResponse(
            status_code=500,
            content={"error": f"Failed to clear generated memory: {exc}"},
        )

    return ClearGeneratedMemoryResponse(
        directory=str(directory),
        deleted_count=deleted_count,
    )
