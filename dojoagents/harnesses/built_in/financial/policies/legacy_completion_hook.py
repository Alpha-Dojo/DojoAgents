from __future__ import annotations

from typing import Any

from .legacy_completion import apply_turn_completion_to_strands_stop_response
from dojoagents.logging import get_logger

LOGGER = get_logger(__name__)


class TurnCompletionHook:
    """Apply turn-completion policy on Strands model-call boundaries."""

    def register_hooks(self, registry: Any, **kwargs: Any) -> None:
        from strands.hooks.events import AfterModelCallEvent, BeforeModelCallEvent

        registry.add_callback(AfterModelCallEvent, self._after_model_call)
        registry.add_callback(BeforeModelCallEvent, self._before_model_call)

    async def _after_model_call(self, event: Any) -> None:
        stop_response = getattr(event, "stop_response", None)
        if stop_response is None:
            return
        message = getattr(stop_response, "message", None)
        if not isinstance(message, dict):
            return
        invocation_state = getattr(event, "invocation_state", None)
        if not isinstance(invocation_state, dict):
            return
        request = invocation_state.get("_dojo_request")
        from dojoagents.agent.models import ChatRequest

        if not isinstance(request, ChatRequest) or request.channel != "dashboard":
            return
        apply_turn_completion_to_strands_stop_response(message, stop_response, invocation_state)

    async def _before_model_call(self, event: Any) -> None:
        invocation_state = getattr(event, "invocation_state", None)
        if not isinstance(invocation_state, dict):
            return
        if not invocation_state.get("_dojo_turn_complete"):
            return
        from dojoagents.agent.models import ChatRequest

        request = invocation_state.get("_dojo_request")
        if not isinstance(request, ChatRequest) or request.channel != "dashboard":
            return
        request_state = invocation_state.setdefault("request_state", {})
        if request_state.get("stop_event_loop"):
            LOGGER.debug("Turn completion: stop_event_loop already set before model call")
