"""Portfolio ToolSpec provider bound to one financial service container."""

from __future__ import annotations

from typing import Any

from dojoagents.tools.registry import ToolRegistry, ToolSpec
from .portfolio_runtime import register_dashboard_portfolio_tools

PORTFOLIO_TOOL_NAMES = (
    "portfolio_read_list",
    "portfolio_read_search",
    "portfolio_read_detail",
    "portfolio_eval_submit",
    "portfolio_write_create",
    "portfolio_write_rename",
    "portfolio_write_delete",
    "portfolio_write_add_candidate",
    "portfolio_write_add_candidates",
    "portfolio_write_add_holding",
    "portfolio_write_add_holdings",
    "portfolio_write_create_order",
    "portfolio_write_create_orders",
    "portfolio_write_sync_positions",
    "portfolio_write_remove_holding",
    "portfolio_write_remove_candidates",
    "portfolio_write_auto_allocate",
)


def get_portfolio_tool_specs(container: Any) -> list[ToolSpec]:
    if container.registry is None:
        raise RuntimeError("financial service container is not ready")
    registry = ToolRegistry()
    register_dashboard_portfolio_tools(registry, container.registry)
    return registry.all()


__all__ = ["PORTFOLIO_TOOL_NAMES", "get_portfolio_tool_specs"]
