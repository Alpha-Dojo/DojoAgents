"""Adapters that apply financial presentation after Core result normalization."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from dojoagents.agent.models import ToolResult
from .legacy_registry import ToolResultPresenterRegistry


class FinancialResultPresenter:
    """Convert normalized Core results into financial UI facts."""

    def __init__(self) -> None:
        self._legacy = ToolResultPresenterRegistry()

    def present(self, result: ToolResult, _context: Any) -> ToolResult:
        presenter_name = result.name
        data = result.data
        if result.name == "portfolio_read_detail" and isinstance(data, dict):
            # Canonical portfolio reads call holdings ``positions`` while the
            # visualization contract calls them ``holdings``.
            data = {**data, "holdings": data.get("holdings") or data.get("positions") or []}
            presenter_name = "get_portfolio_analysis"
        raw = {
            "content": result.content,
            "data": data,
            "truncated": result.truncated,
            "viz_blocks": list(result.viz_blocks),
            "artifacts": list(result.artifacts),
            "resource_changes": list(result.resource_changes),
            "metadata": dict(result.metadata),
            "arguments": dict(result.metadata.get("tool_arguments") or {}),
        }
        normalized = self._legacy.normalize(presenter_name, raw)
        return replace(
            result,
            content=str(normalized.get("content", result.content)),
            data=normalized.get("data"),
            truncated=bool(normalized.get("truncated", result.truncated)),
            viz_blocks=list(normalized.get("viz_blocks") or ()),
            artifacts=list(normalized.get("artifacts") or ()),
            resource_changes=list(normalized.get("resource_changes") or ()),
            metadata=dict(normalized.get("metadata") or result.metadata),
        )
