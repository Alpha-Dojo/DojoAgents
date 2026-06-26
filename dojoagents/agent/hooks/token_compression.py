from __future__ import annotations

from typing import Any

from dojoagents.agent.compressor import ContextCompressor, _estimate_tokens_rough, flatten_messages_for_compress
from dojoagents.agent.model_context import ModelContextRegistry
from dojoagents.agent.token_ledger import SessionTokenLedger
from dojoagents.agent.token_policy import TokenCompressionPolicy
from dojoagents.logging import LOGGER


class TokenCompressionHook:
    def __init__(
        self,
        *,
        compressor: ContextCompressor,
        policy: TokenCompressionPolicy,
        llm_provider: Any,
        model: str,
        memory_manager: Any,
        enabled: bool,
        model_context_registry: ModelContextRegistry | None = None,
    ) -> None:
        self.compressor = compressor
        self.policy = policy
        self.llm_provider = llm_provider
        self.model = model
        self.memory_manager = memory_manager
        self.enabled = enabled
        self.model_context_registry = model_context_registry

    def register_hooks(self, registry: Any, **kwargs: Any) -> None:
        from strands.hooks.events import AfterModelCallEvent, BeforeModelCallEvent

        registry.add_callback(BeforeModelCallEvent, self._before_model_call)
        registry.add_callback(AfterModelCallEvent, self._after_model_call)

    async def _before_model_call(self, event: Any) -> None:
        invocation_state = event.invocation_state
        invocation_state["_dojo_agent"] = event.agent
        await self._maybe_compress(
            event.agent,
            invocation_state,
            prompt_tokens=self._projected_tokens(event),
        )

    async def _after_model_call(self, event: Any) -> None:
        invocation_state = event.invocation_state
        ledger: SessionTokenLedger | None = invocation_state.get("_dojo_token_ledger")
        if ledger is None or ledger.state is None:
            return

        usage = invocation_state.pop("_dojo_last_usage", None)
        if isinstance(usage, dict):
            ledger.state.record_loop(usage)
        elif usage is None:
            LOGGER.warning("LLM usage missing for session %s; skipping ledger update", ledger.session_id)

        event_sink = invocation_state.get("_dojo_event_sink")
        if event_sink is not None:
            event_sink.token_usage(ledger.state.snapshot())

        await self._maybe_compress(
            event.agent,
            invocation_state,
            prompt_tokens=ledger.state.last_prompt_tokens,
        )

    async def handle_context_length_exceeded(
        self,
        agent: Any,
        invocation_state: dict[str, Any],
        *,
        max_context: int | None,
        requested_tokens: int | None,
    ) -> bool:
        ledger: SessionTokenLedger | None = invocation_state.get("_dojo_token_ledger")
        if ledger is None or ledger.state is None:
            return False

        if isinstance(max_context, int) and max_context > 0:
            ledger.state.update_context_window(max_context)
            provider = str(ledger.state.provider or "")
            model_id = str(ledger.state.model_id or "")
            if self.model_context_registry is not None and provider and model_id:
                self.model_context_registry.note_context_window(provider, model_id, max_context)

        if isinstance(requested_tokens, int) and requested_tokens > 0:
            ledger.state.last_prompt_tokens = requested_tokens

        event_sink = invocation_state.get("_dojo_event_sink")
        if event_sink is not None:
            event_sink.token_usage(ledger.state.snapshot())

        return await self._maybe_compress(agent, invocation_state, prompt_tokens=requested_tokens, force=True)

    @staticmethod
    def _projected_tokens(event: Any) -> int | None:
        projected = getattr(event, "projected_input_tokens", None)
        if isinstance(projected, int) and projected > 0:
            return projected
        return None

    def _message_estimate(self, agent: Any) -> int:
        if agent is None or not getattr(agent, "messages", None):
            return 0
        return _estimate_tokens_rough(flatten_messages_for_compress(list(agent.messages)))

    async def _maybe_compress(
        self,
        agent: Any,
        invocation_state: dict[str, Any],
        *,
        prompt_tokens: int | None,
        force: bool = False,
    ) -> bool:
        ledger: SessionTokenLedger | None = invocation_state.get("_dojo_token_ledger")
        if ledger is None or ledger.state is None or agent is None or not getattr(agent, "messages", None):
            return False

        policy: TokenCompressionPolicy = invocation_state.get("_dojo_compression_policy") or self.policy
        estimated = self._message_estimate(agent)
        effective_tokens = max(int(prompt_tokens or 0), estimated)
        if not force and not policy.should_compress(
            effective_tokens,
            ledger.state.session_max_tokens,
            enabled=self.enabled,
        ):
            return False

        compressed = await self.compressor.compress(
            list(agent.messages),
            self.llm_provider,
            self.model,
            memory_manager=self.memory_manager,
            session_id=str(invocation_state.get("session_id", ledger.session_id)),
        )
        agent.messages = compressed
        ledger.state.note_compression(_estimate_tokens_rough(flatten_messages_for_compress(compressed)))

        event_sink = invocation_state.get("_dojo_event_sink")
        if event_sink is not None:
            event_sink.context_compacted(ledger.state.compression_count, ledger.state.last_prompt_tokens)
            event_sink.token_usage(ledger.state.snapshot())
        return True
