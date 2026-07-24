from __future__ import annotations

import inspect
from dataclasses import dataclass
from typing import Any, Callable

from ..capabilities import FlowPolicySpec, ToolAuthorizerSpec, ToolTransformerSpec
from ..decisions import CompletionDecision, ToolControlDecision
from ..errors import HarnessPolicyError


async def _resolve(value: Any) -> Any:
    return await value if inspect.isawaitable(value) else value


@dataclass(frozen=True)
class PolicyRegistry:
    flow: tuple[FlowPolicySpec, ...] = ()
    authorizers: tuple[ToolAuthorizerSpec, ...] = ()
    transformers: tuple[ToolTransformerSpec, ...] = ()

    def __post_init__(self) -> None:
        def key(spec):
            return -spec.priority, spec.component_id

        object.__setattr__(self, "flow", tuple(sorted(self.flow, key=key)))
        object.__setattr__(self, "authorizers", tuple(sorted(self.authorizers, key=key)))
        object.__setattr__(self, "transformers", tuple(sorted(self.transformers, key=key)))

    async def transform_calls(
        self,
        calls: tuple[Any, ...] | list[Any],
        context: Any,
        *,
        revalidate: Callable[[Any], Any],
    ) -> tuple[Any, ...]:
        current = tuple(calls)
        for spec in self.transformers:
            transformer = spec.transformer
            batch_callback = getattr(transformer, "transform_calls", None)
            if batch_callback is not None:
                try:
                    current = tuple(await _resolve(batch_callback(current, context)))
                except Exception as exc:
                    raise HarnessPolicyError(f"tool transformer '{spec.component_id}' from {spec.source} failed") from exc
                continue
            transformed: list[Any] = []
            for call in current:
                callback = getattr(spec.transformer, "transform", spec.transformer)
                if callback is None:
                    transformed.append(call)
                    continue
                try:
                    call = await _resolve(callback(call, context))
                except Exception as exc:
                    raise HarnessPolicyError(f"tool transformer '{spec.component_id}' from {spec.source} failed") from exc
                transformed.append(call)
            current = tuple(transformed)
        for call in current:
            await _resolve(revalidate(call))
        return current

    async def authorize(
        self,
        call: Any,
        context: Any,
        *,
        core_authorizer: Callable[[Any, Any], Any],
    ) -> ToolControlDecision:
        try:
            core = await _resolve(core_authorizer(call, context))
        except Exception:
            return ToolControlDecision("halt", "core_policy_error", "Core tool safety evaluation failed")
        if not isinstance(core, ToolControlDecision):
            return ToolControlDecision("halt", "core_policy_error", "Core tool safety returned an invalid decision")
        if core.action != "allow":
            return core
        for spec in self.authorizers:
            callback = getattr(spec.authorizer, "authorize", spec.authorizer)
            if callback is None:
                continue
            try:
                decision = await _resolve(callback(call, context))
            except Exception:
                return ToolControlDecision(
                    "halt",
                    "harness_policy_error",
                    f"Harness tool policy '{spec.component_id}' failed",
                )
            if not isinstance(decision, ToolControlDecision):
                return ToolControlDecision(
                    "halt",
                    "harness_policy_error",
                    f"Harness tool policy '{spec.component_id}' returned an invalid decision",
                )
            if decision.action != "allow":
                return decision
        return core

    async def evaluate_completion(
        self,
        context: Any,
        *,
        hard_max_extra_turns: int,
    ) -> CompletionDecision:
        for spec in self.flow:
            policy = spec.policy
            callback = getattr(policy, "evaluate_completion", policy)
            if callback is None:
                continue
            try:
                decision = await _resolve(callback(context))
            except Exception:
                return CompletionDecision(
                    "blocked",
                    "harness_policy_error",
                    issues=(f"completion policy '{spec.component_id}' failed",),
                )
            if not isinstance(decision, CompletionDecision):
                return CompletionDecision(
                    "blocked",
                    "harness_policy_error",
                    issues=(f"completion policy '{spec.component_id}' returned an invalid decision",),
                )
            if decision.action == "continue":
                continue
            if decision.action == "recover":
                return CompletionDecision(
                    action=decision.action,
                    code=decision.code,
                    issues=decision.issues,
                    recovery_prompt=decision.recovery_prompt,
                    max_extra_turns=min(decision.max_extra_turns, max(0, hard_max_extra_turns)),
                    context=decision.context,
                )
            return decision
        return CompletionDecision("complete", "policies_satisfied")

    async def before_turn(self, context: Any) -> None:
        await self._invoke_flow_hook("before_turn", context)

    async def after_turn(self, context: Any) -> None:
        await self._invoke_flow_hook("after_turn", context)

    async def _invoke_flow_hook(self, hook_name: str, context: Any) -> None:
        for spec in self.flow:
            callback = getattr(spec.policy, hook_name, None)
            if callback is None:
                continue
            try:
                await _resolve(callback(context))
            except Exception as exc:
                raise HarnessPolicyError(f"flow policy '{spec.component_id}' {hook_name} failed") from exc
