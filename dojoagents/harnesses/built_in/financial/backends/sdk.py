"""Standalone DojoSDK backend for non-Dashboard Runtime hosts."""

from __future__ import annotations

from types import MappingProxyType
from typing import Any, Mapping

from dojoagents.config.models import DojoSDKConfig
from dojoagents.tools.registry import ToolSpec

from ..tools.sdk_runtime import DojoSDKToolManager
from .base import FinancialToolDefinition


class SDKFinancialToolBackend:
    """Expose only capabilities implemented directly by DojoSDK."""

    def __init__(self, config: DojoSDKConfig) -> None:
        self._manager = DojoSDKToolManager(config)
        self._specs: dict[str, ToolSpec] = {spec.name: spec for spec in self._manager.get_tool_specs()}
        self._definitions = MappingProxyType(
            {
                name: FinancialToolDefinition(
                    name=name,
                    description=spec.description,
                    parameters=spec.parameters,
                )
                for name, spec in self._specs.items()
            }
        )

    @property
    def supported_tools(self) -> frozenset[str]:
        return frozenset(self._specs)

    @property
    def tool_definitions(self) -> Mapping[str, FinancialToolDefinition]:
        return self._definitions

    async def health(self) -> bool:
        return True

    async def execute(
        self,
        tool_name: str,
        arguments: Mapping[str, Any],
        *,
        principal: Any,
        session_id: str,
    ) -> Mapping[str, Any]:
        del principal, session_id
        spec = self._specs.get(tool_name)
        if spec is None:
            raise RuntimeError(f"financial tool '{tool_name}' is unavailable in the standalone SDK backend")
        return await spec.handler(dict(arguments))

    async def shutdown(self) -> None:
        client = self._manager._client
        if client is None:
            return
        close = getattr(client, "aclose", None)
        if callable(close):
            await close()
        self._manager._client = None


__all__ = ["SDKFinancialToolBackend"]
