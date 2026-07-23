"""Dependency accessors for the generic Dashboard host."""

from __future__ import annotations

from typing import Any

from fastapi import Request


def get_session_manager(request: Request) -> Any:
    runtime = getattr(request.app.state, "runtime", None)
    if runtime is None:
        raise RuntimeError("runtime is not initialized")
    sessions = getattr(runtime, "sessions", None)
    if sessions is None:
        raise RuntimeError("session manager is not initialized")
    return sessions


def get_chat_session_service(request: Request) -> Any:
    from dojoagents.dashboard.services.chat_session_service import ChatSessionService

    return ChatSessionService(get_session_manager(request))


__all__ = ["get_chat_session_service", "get_session_manager"]
