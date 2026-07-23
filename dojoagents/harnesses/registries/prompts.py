from __future__ import annotations

import inspect
from dataclasses import dataclass
from typing import Any

from ..capabilities import PromptContributorSpec
from ..errors import CapabilityConflictError, HarnessPolicyError

_PHASES = (
    "identity",
    "temporal",
    "harness_instructions",
    "skills",
    "memory",
    "request_context",
    "channel_policy",
    "task_context",
    "turn_policy",
)
_ORDER = {phase: index for index, phase in enumerate(_PHASES)}


@dataclass(frozen=True)
class PromptBlock:
    block_id: str
    phase: str
    content: str
    source: str
    priority: int = 0


async def _resolve(value: Any) -> Any:
    return await value if inspect.isawaitable(value) else value


@dataclass(frozen=True)
class PromptRegistry:
    contributors: tuple[PromptContributorSpec, ...] = ()

    async def compose(self, context: Any, *, core_safety: str) -> tuple[PromptBlock, ...]:
        seen: dict[str, PromptContributorSpec] = {}
        for spec in self.contributors:
            if spec.component_id == "core.safety":
                raise CapabilityConflictError("prompt block 'core.safety' is reserved by Core")
            existing = seen.get(spec.component_id)
            if existing is not None:
                raise CapabilityConflictError(f"duplicate prompt block '{spec.component_id}' from {existing.source} conflicts with {spec.source}")
            seen[spec.component_id] = spec

        blocks = [PromptBlock("core.safety", "core_safety", core_safety, "core", priority=10_000)]
        ordered = sorted(
            self.contributors,
            key=lambda spec: (_ORDER.get(spec.phase, len(_ORDER)), -spec.priority, spec.component_id),
        )
        for spec in ordered:
            predicate = spec.channel_predicate
            if predicate is not None:
                request = getattr(context, "request", None)
                channel = str(getattr(request, "channel", ""))
                if not predicate(channel):
                    continue
            contributor = spec.contributor
            if contributor is None:
                continue
            callback = getattr(contributor, "contribute", contributor)
            try:
                content = await _resolve(callback(context))
            except Exception as exc:
                raise HarnessPolicyError(f"prompt contributor '{spec.component_id}' from {spec.source} failed") from exc
            if content is None or content == "":
                continue
            if isinstance(content, PromptBlock):
                if content.block_id != spec.component_id:
                    raise HarnessPolicyError(f"prompt contributor '{spec.component_id}' returned mismatched block ID '{content.block_id}'")
                blocks.append(content)
            elif isinstance(content, str):
                blocks.append(PromptBlock(spec.component_id, spec.phase, content, spec.source, spec.priority))
            else:
                raise HarnessPolicyError(f"prompt contributor '{spec.component_id}' must return str, PromptBlock or None")
        return tuple(blocks)
