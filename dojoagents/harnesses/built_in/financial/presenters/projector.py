from __future__ import annotations

from typing import Any, Iterable

from dojoagents.agent.models import ToolResult
from dojoagents.harnesses.registries.presenters import PresenterRegistry


class FinancialResultProjector:
    """Project already-presented financial results for surface transports."""

    def __init__(self, registry: PresenterRegistry | None = None) -> None:
        self.registry = registry

    def project(self, results: Iterable[ToolResult]) -> dict[str, list[dict[str, Any]]]:
        materialized = tuple(results)
        return {
            "viz_blocks": [block for result in materialized for block in result.viz_blocks],
            "artifacts": [artifact for result in materialized for artifact in result.artifacts],
            "resource_changes": [change for result in materialized for change in result.resource_changes],
        }

    async def project_results(self, results: Iterable[ToolResult], context: Any = None) -> dict[str, list[dict[str, Any]]]:
        materialized = tuple(results)
        if self.registry is not None:
            materialized = await self.registry.present(materialized, context)
        return self.project(materialized)


__all__ = ["FinancialResultProjector"]
