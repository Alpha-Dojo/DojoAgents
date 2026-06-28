from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any


@dataclass
class ProviderTurnState:
    provider: str
    model: str
    session_id: str
    tool_call_id: str
    tool_name: str
    arguments: dict[str, Any]
    native_model_content: dict[str, Any]
    created_at: float


class ProviderConversationState:
    def __init__(self, *, ttl_seconds: float = 60 * 60) -> None:
        self._ttl_seconds = ttl_seconds
        self._entries: dict[tuple[str, str, str, str], ProviderTurnState] = {}

    def _key(
        self,
        *,
        provider: str,
        model: str,
        session_id: str,
        tool_call_id: str,
    ) -> tuple[str, str, str, str]:
        return (provider, model, session_id, tool_call_id)

    def _prune(self) -> None:
        cutoff = time.time() - self._ttl_seconds
        stale = [key for key, value in self._entries.items() if value.created_at < cutoff]
        for key in stale:
            self._entries.pop(key, None)

    def record_tool_call(
        self,
        *,
        provider: str,
        model: str,
        session_id: str,
        tool_call_id: str,
        tool_name: str,
        arguments: dict[str, Any],
        native_model_content: dict[str, Any],
    ) -> None:
        self._prune()
        self._entries[
            self._key(
                provider=provider,
                model=model,
                session_id=session_id,
                tool_call_id=tool_call_id,
            )
        ] = ProviderTurnState(
            provider=provider,
            model=model,
            session_id=session_id,
            tool_call_id=tool_call_id,
            tool_name=tool_name,
            arguments=dict(arguments),
            native_model_content=dict(native_model_content),
            created_at=time.time(),
        )

    def get_tool_call(
        self,
        *,
        provider: str,
        model: str,
        session_id: str,
        tool_call_id: str,
    ) -> ProviderTurnState | None:
        self._prune()
        return self._entries.get(
            self._key(
                provider=provider,
                model=model,
                session_id=session_id,
                tool_call_id=tool_call_id,
            )
        )

    def metadata_for_tool_call(
        self,
        *,
        provider: str,
        model: str,
        session_id: str,
        tool_call_id: str,
    ) -> dict[str, Any]:
        entry = self.get_tool_call(
            provider=provider,
            model=model,
            session_id=session_id,
            tool_call_id=tool_call_id,
        )
        if entry is None:
            return {}
        return {
            "provider": entry.provider,
            "native_state_key": entry.tool_call_id,
            "native_model_content": dict(entry.native_model_content),
        }
