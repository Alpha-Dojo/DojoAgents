from __future__ import annotations

import inspect
from dataclasses import dataclass
from typing import Any

from dojoagents.agent.models import ToolResult

from ..capabilities import ResultPresenterSpec
from ..errors import CapabilityConflictError, HarnessPolicyError


async def _resolve(value: Any) -> Any:
    return await value if inspect.isawaitable(value) else value


@dataclass(frozen=True)
class PresenterRegistry:
    presenters: tuple[ResultPresenterSpec, ...] = ()

    def __post_init__(self) -> None:
        ordered = tuple(sorted(self.presenters, key=lambda spec: (-spec.priority, spec.component_id)))
        for index, first in enumerate(ordered):
            if not first.exclusive:
                continue
            for second in ordered[index + 1 :]:
                overlap = set(first.match_kinds).intersection(second.match_kinds)
                if second.exclusive and overlap:
                    raise CapabilityConflictError(f"exclusive presenter matcher '{sorted(overlap)[0]}' from {first.source} " f"conflicts with {second.source}")
        object.__setattr__(self, "presenters", ordered)

    async def present(self, results: tuple[ToolResult, ...] | list[ToolResult], context: Any) -> tuple[ToolResult, ...]:
        presented: list[ToolResult] = []
        for result in results:
            if not isinstance(result, ToolResult):
                raise HarnessPolicyError("presenters require normalized Core ToolResult values")
            current = result
            kind = str(current.metadata.get("kind", current.name))
            for spec in self.presenters:
                if spec.match_kinds and kind not in spec.match_kinds:
                    continue
                callback = getattr(spec.presenter, "present", spec.presenter)
                if callback is None:
                    continue
                try:
                    value = await _resolve(callback(current, context))
                except Exception as exc:
                    raise HarnessPolicyError(f"result presenter '{spec.component_id}' from {spec.source} failed") from exc
                if value is not None:
                    if not isinstance(value, ToolResult):
                        raise HarnessPolicyError(f"result presenter '{spec.component_id}' must return ToolResult or None")
                    current = value
            presented.append(current)
        return tuple(presented)
