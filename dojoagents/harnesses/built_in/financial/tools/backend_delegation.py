"""Build thin ToolSpecs that delegate through FinancialToolBackend."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from dojoagents.tools.process_registry import (
    active_session_id,
    active_session_principal,
)
from dojoagents.tools.registry import ToolSpec


def get_backend_tool_specs(
    backend: Any,
    names: Iterable[str],
) -> list[ToolSpec]:
    definitions = backend.tool_definitions
    specs: list[ToolSpec] = []
    for name in names:
        definition = definitions.get(name)
        if definition is None:
            continue

        async def execute(arguments: dict[str, Any], *, tool_name: str = name):
            principal = active_session_principal.get()
            if principal is None:
                raise RuntimeError(f"financial tool '{tool_name}' requires an active session principal")
            return await backend.execute(
                tool_name,
                arguments,
                principal=principal,
                session_id=active_session_id.get(),
            )

        specs.append(
            ToolSpec(
                name=definition.name,
                description=definition.description,
                parameters=dict(definition.parameters),
                handler=execute,
            )
        )
    return specs


__all__ = ["get_backend_tool_specs"]
