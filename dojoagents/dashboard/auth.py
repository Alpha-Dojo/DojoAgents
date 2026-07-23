"""Dashboard authentication boundary for canonical session scope."""

from __future__ import annotations

from typing import Awaitable, Protocol

from fastapi import Request

from dojoagents.sessions.models import SessionPrincipal


class PrincipalProvider(Protocol):
    def resolve(self, request: Request) -> Awaitable[SessionPrincipal]: ...


class LegacyLocalPrincipalProvider:
    """Single-user file deployment identity; never trusts request payloads."""

    async def resolve(self, request: Request) -> SessionPrincipal:
        del request
        return SessionPrincipal(user_id="local", tenant_id="default")


async def get_session_principal(request: Request) -> SessionPrincipal:
    provider = getattr(request.app.state, "principal_provider", None)
    if provider is None:
        provider = LegacyLocalPrincipalProvider()
    principal = await provider.resolve(request)
    if not isinstance(principal, SessionPrincipal):
        raise TypeError("principal provider must return SessionPrincipal")
    return principal


__all__ = ["LegacyLocalPrincipalProvider", "PrincipalProvider", "get_session_principal"]
