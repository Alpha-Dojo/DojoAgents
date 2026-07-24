"""Domain-neutral execution facade over frozen harness registries."""

from __future__ import annotations

from typing import Any, Callable

from .capabilities import HarnessCapabilities, PromptContributorSpec
from .registries.policies import PolicyRegistry
from .registries.presenters import PresenterRegistry
from .registries.prompts import PromptBlock, PromptRegistry


class HarnessRuntime:
    def __init__(
        self,
        capabilities: HarnessCapabilities,
        *,
        core_safety_prompt: str,
        core_tool_authorizer: Callable[[Any, Any], Any],
        revalidate_tool_call: Callable[[Any], Any],
        max_recovery_turns: int = 3,
    ) -> None:
        self.capabilities = capabilities
        self._core_safety_prompt = core_safety_prompt
        self._core_tool_authorizer = core_tool_authorizer
        self._revalidate_tool_call = revalidate_tool_call
        self._max_recovery_turns = max(0, max_recovery_turns)
        prompt_specs = list(capabilities.prompts)
        if capabilities.identity is not None and capabilities.identity.identity is not None:
            identity = capabilities.identity
            prompt_specs.append(
                PromptContributorSpec(
                    component_id=identity.component_id,
                    source=identity.source,
                    priority=identity.priority,
                    dependencies=identity.dependencies,
                    required_services=identity.required_services,
                    required_tools=identity.required_tools,
                    channel_predicate=identity.channel_predicate,
                    phase="identity",
                    contributor=lambda _context, value=identity.identity: str(value),
                )
            )
        self.prompts = PromptRegistry(tuple(prompt_specs))
        self.policies = PolicyRegistry(
            flow=capabilities.flow_policies,
            authorizers=capabilities.tool_authorizers,
            transformers=capabilities.tool_transformers,
        )
        self.presenters = PresenterRegistry(capabilities.presenters)

    async def before_turn(self, context: Any) -> tuple[PromptBlock, ...]:
        resolved_contexts: dict[str, Any] = {}
        for spec in self.capabilities.request_context_codecs:
            codec = spec.codec
            callback = getattr(codec, "decode", codec)
            if callback is None:
                continue
            value = callback(context.request)
            if hasattr(value, "__await__"):
                value = await value
            if value is not None:
                resolved_contexts[spec.component_id] = value
        context.turn_state.values["request_contexts"] = resolved_contexts
        await self.policies.before_turn(context)
        return await self.prompts.compose(context, core_safety=self._core_safety_prompt)

    async def transform_calls(self, calls: tuple[Any, ...] | list[Any], context: Any) -> tuple[Any, ...]:
        return await self.policies.transform_calls(calls, context, revalidate=self._revalidate_tool_call)

    async def authorize(self, call: Any, context: Any):
        return await self.policies.authorize(call, context, core_authorizer=self._core_tool_authorizer)

    async def present_results(self, results: tuple[Any, ...] | list[Any], context: Any):
        return await self.presenters.present(results, context)

    async def evaluate_completion(self, context: Any):
        return await self.policies.evaluate_completion(
            context,
            hard_max_extra_turns=self._max_recovery_turns,
        )

    async def after_turn(self, context: Any) -> None:
        await self.policies.after_turn(context)
