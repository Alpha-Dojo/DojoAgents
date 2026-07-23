"""In-process adapter from Agent financial tools to Dashboard services."""

from __future__ import annotations

from types import MappingProxyType
from typing import Any, Mapping

from dojoagents.harnesses.built_in.financial.backends.base import (
    FinancialToolDefinition,
)
from dojoagents.harnesses.built_in.financial.tools.sdk_runtime import (
    DojoSDKToolManager,
)
from dojoagents.tools.registry import ToolRegistry, ToolSpec

from .financial_domain_tools import register_dashboard_domain_tools
from .financial_portfolio_tools import register_dashboard_portfolio_tools


class DashboardFinancialAgentBackend:
    """Explicit in-process dispatch over one DashboardAppServices instance."""

    def __init__(self, app_services: Any) -> None:
        registry = ToolRegistry()
        register_dashboard_domain_tools(registry, app_services.registry)
        register_dashboard_portfolio_tools(registry, app_services.registry)
        sdk_manager = DojoSDKToolManager()
        sdk_manager._client = app_services.client
        for spec in sdk_manager.get_tool_specs():
            registry.register(spec)
        self._specs: dict[str, ToolSpec] = {spec.name: spec for spec in registry.all()}
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

    async def execute(
        self,
        tool_name: str,
        arguments: Mapping[str, Any],
        *,
        principal: Any,
        session_id: str,
    ) -> Mapping[str, Any]:
        if principal is None or not str(getattr(principal, "user_id", "")).strip():
            raise RuntimeError("financial tool execution requires an authenticated principal")
        if not session_id.strip():
            raise RuntimeError("financial tool execution requires a session_id")
        spec = self._specs.get(tool_name)
        if spec is None:
            raise RuntimeError(f"unsupported financial tool: {tool_name}")
        result = dict(await spec.handler(dict(arguments)))
        metadata = dict(result.get("metadata") or {})
        metadata.update(
            {
                "backend": "dashboard-in-process",
                "user_id": principal.user_id,
                "session_id": session_id,
            }
        )
        result["metadata"] = metadata
        return result


__all__ = ["DashboardFinancialAgentBackend"]
