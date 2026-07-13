"""Turn completion policy — stop agent cycles when the deliverable is ready.

Register rules via ``register_turn_completion_rule``. Primary enforcement runs in
``DojoStrandsModelBridge`` before tool blocks are emitted; ``TurnCompletionHook``
mirrors the policy on Strands ``AfterModelCallEvent`` for defense in depth.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

from dojoagents.agent.harness import HarnessLoopState, TaskHarness
from dojoagents.agent.models import ChatRequest, LLMResult, ToolCall
from dojoagents.agent.viz_policy import VizPolicyContext, check_agent_viz_build
from dojoagents.logging import get_logger

LOGGER = get_logger(__name__)

TurnCompletionAction = Literal["continue", "absorb_tools", "stop_loop"]
TurnCompletionRule = Callable[["TurnCompletionContext"], "TurnCompletionDecision | None"]

MIN_DELIVERABLE_CHARS = 60


@dataclass(frozen=True)
class TurnCompletionContext:
    channel: str
    user_message: str
    locale: str
    user_visible_text: str
    pending_tool_names: tuple[str, ...] = ()
    harness_state: HarnessLoopState | None = None
    active_harness: TaskHarness | None = None


@dataclass(frozen=True)
class TurnCompletionDecision:
    scene_id: str
    action: TurnCompletionAction
    absorb_all_pending_tools: bool = False
    absorb_tool_names: frozenset[str] = frozenset()
    stop_event_loop: bool = False
    priority: int = 0


_extra_rules: list[tuple[int, TurnCompletionRule]] = []


def register_turn_completion_rule(rule: TurnCompletionRule, *, priority: int = 10) -> None:
    _extra_rules.append((priority, rule))
    _extra_rules.sort(key=lambda item: item[0], reverse=True)


def has_deliverable(text: str) -> bool:
    stripped = str(text or "").strip()
    if len(stripped) >= MIN_DELIVERABLE_CHARS:
        return True
    if ("##" in stripped or "|" in stripped or "✅" in stripped) and len(stripped) >= 30:
        return True
    return False


def extract_text_from_strands_message(message: dict[str, Any]) -> str:
    parts: list[str] = []
    for block in message.get("content") or []:
        if isinstance(block, dict) and "text" in block:
            parts.append(str(block.get("text") or ""))
    return "".join(parts).strip()


def pending_tool_names_from_strands_message(message: dict[str, Any]) -> list[str]:
    names: list[str] = []
    for block in message.get("content") or []:
        if not isinstance(block, dict) or "toolUse" not in block:
            continue
        tool_use = block.get("toolUse")
        if isinstance(tool_use, dict) and tool_use.get("name"):
            names.append(str(tool_use["name"]))
    return names


def absorb_tools_from_strands_message(
    message: dict[str, Any],
    *,
    tool_names: set[str] | None = None,
    absorb_all: bool = False,
) -> list[str]:
    removed: list[str] = []
    content = message.get("content")
    if not isinstance(content, list):
        return removed
    kept: list[Any] = []
    allowed = tool_names or set()
    for block in content:
        if isinstance(block, dict) and "toolUse" in block:
            tool_use = block.get("toolUse")
            name = str((tool_use or {}).get("name") or "") if isinstance(tool_use, dict) else ""
            if absorb_all or name in allowed:
                if name:
                    removed.append(name)
                continue
        kept.append(block)
    message["content"] = kept
    return removed


def absorb_tools_from_llm_result(
    result: LLMResult,
    *,
    tool_names: set[str] | None = None,
    absorb_all: bool = False,
) -> list[str]:
    removed: list[str] = []
    allowed = tool_names or set()
    kept: list[ToolCall] = []
    for call in result.tool_calls:
        if absorb_all or call.name in allowed:
            removed.append(call.name)
        else:
            kept.append(call)
    result.tool_calls = kept
    return removed


def _resolve_active_harness(
    request: ChatRequest | None,
    harness_state: HarnessLoopState | None,
    task_harnesses: list[TaskHarness] | None,
) -> TaskHarness | None:
    if request is None or harness_state is None or not task_harnesses:
        return None
    for harness in task_harnesses:
        try:
            if harness.matches(request, harness_state):
                return harness
        except Exception:
            LOGGER.exception("Turn completion harness match failed: %s", getattr(harness, "name", harness))
    return None


def build_turn_completion_context_from_invocation(
    invocation_state: dict[str, Any],
    *,
    llm_result: LLMResult | None = None,
    strands_message: dict[str, Any] | None = None,
) -> TurnCompletionContext | None:
    request = invocation_state.get("_dojo_request")
    if not isinstance(request, ChatRequest):
        return None
    harness_state = invocation_state.get("_dojo_harness_state")
    if harness_state is not None and not isinstance(harness_state, HarnessLoopState):
        harness_state = None
    task_harnesses = invocation_state.get("_dojo_task_harnesses")
    if not isinstance(task_harnesses, list):
        task_harnesses = []

    if llm_result is not None:
        user_visible_text = str(llm_result.content or "").strip()
        pending_tool_names = tuple(call.name for call in llm_result.tool_calls)
    elif strands_message is not None:
        user_visible_text = extract_text_from_strands_message(strands_message)
        pending_tool_names = tuple(pending_tool_names_from_strands_message(strands_message))
    else:
        return None

    locale = str(request.metadata.get("locale") or "en")
    return TurnCompletionContext(
        channel=str(request.channel or ""),
        user_message=str(request.message or ""),
        locale=locale,
        user_visible_text=user_visible_text,
        pending_tool_names=pending_tool_names,
        harness_state=harness_state,
        active_harness=_resolve_active_harness(request, harness_state, task_harnesses),
    )


def _forbidden_viz_tools(ctx: TurnCompletionContext) -> frozenset[str]:
    if ctx.channel != "dashboard" or not ctx.harness_state:
        return frozenset()
    viz_ctx = VizPolicyContext(
        channel=ctx.channel,
        user_message=ctx.user_message,
        locale=ctx.locale,
        tool_results=tuple(ctx.harness_state.tool_results),
        tool_trace=tuple(ctx.harness_state.tool_trace),
    )
    if not check_agent_viz_build(viz_ctx).block_agent_viz_build:
        return frozenset()
    return frozenset(name for name in ctx.pending_tool_names if name == "agent_viz_build")


def _rule_harness_complete(ctx: TurnCompletionContext) -> TurnCompletionDecision | None:
    if not has_deliverable(ctx.user_visible_text) or not ctx.pending_tool_names:
        return None
    if ctx.active_harness is None or ctx.harness_state is None:
        return None
    try:
        harness_decision = ctx.active_harness.validate_progress(ctx.harness_state)
    except Exception:
        LOGGER.exception("Turn completion harness validation failed")
        return None
    if not harness_decision.complete:
        return None
    return TurnCompletionDecision(
        scene_id="harness_complete",
        action="absorb_tools",
        absorb_all_pending_tools=True,
        stop_event_loop=True,
        priority=100,
    )


def _rule_forbidden_viz_with_deliverable(ctx: TurnCompletionContext) -> TurnCompletionDecision | None:
    if not has_deliverable(ctx.user_visible_text) or not ctx.pending_tool_names:
        return None
    forbidden = _forbidden_viz_tools(ctx)
    if not forbidden:
        return None
    remaining = [name for name in ctx.pending_tool_names if name not in forbidden]
    if remaining:
        return TurnCompletionDecision(
            scene_id="forbidden_viz_absorb",
            action="absorb_tools",
            absorb_tool_names=forbidden,
            stop_event_loop=not remaining,
            priority=90,
        )
    return TurnCompletionDecision(
        scene_id="forbidden_viz_absorb",
        action="absorb_tools",
        absorb_all_pending_tools=True,
        stop_event_loop=True,
        priority=90,
    )


_BUILTIN_RULES: tuple[tuple[int, TurnCompletionRule], ...] = (
    (100, _rule_harness_complete),
    (90, _rule_forbidden_viz_with_deliverable),
)


def _all_rules() -> list[tuple[int, TurnCompletionRule]]:
    merged = list(_BUILTIN_RULES) + list(_extra_rules)
    merged.sort(key=lambda item: item[0], reverse=True)
    return merged


def resolve_turn_completion(ctx: TurnCompletionContext) -> TurnCompletionDecision:
    for _priority, rule in _all_rules():
        match = rule(ctx)
        if match is not None:
            return match
    return TurnCompletionDecision(scene_id="default", action="continue")


def apply_turn_completion_decision(
    decision: TurnCompletionDecision,
    invocation_state: dict[str, Any],
    *,
    llm_result: LLMResult | None = None,
    strands_message: dict[str, Any] | None = None,
) -> list[str]:
    if decision.action == "continue":
        return []

    removed: list[str] = []
    if llm_result is not None:
        if decision.absorb_all_pending_tools:
            removed = absorb_tools_from_llm_result(llm_result, absorb_all=True)
        elif decision.absorb_tool_names:
            removed = absorb_tools_from_llm_result(llm_result, tool_names=set(decision.absorb_tool_names))
    elif strands_message is not None:
        if decision.absorb_all_pending_tools:
            removed = absorb_tools_from_strands_message(strands_message, absorb_all=True)
        elif decision.absorb_tool_names:
            removed = absorb_tools_from_strands_message(strands_message, tool_names=set(decision.absorb_tool_names))

    if decision.stop_event_loop or decision.action == "stop_loop":
        invocation_state.setdefault("request_state", {})["stop_event_loop"] = True
        invocation_state["_dojo_turn_complete"] = True

    if removed:
        LOGGER.info(
            "Turn completion absorbed pending tools scene=%s removed=%s",
            decision.scene_id,
            removed,
        )
    return removed


def apply_turn_completion_after_model(
    llm_result: LLMResult,
    invocation_state: dict[str, Any],
) -> TurnCompletionDecision:
    ctx = build_turn_completion_context_from_invocation(invocation_state, llm_result=llm_result)
    if ctx is None:
        return TurnCompletionDecision(scene_id="default", action="continue")
    decision = resolve_turn_completion(ctx)
    apply_turn_completion_decision(decision, invocation_state, llm_result=llm_result)
    return decision


def apply_turn_completion_to_strands_stop_response(
    message: dict[str, Any],
    stop_response: Any,
    invocation_state: dict[str, Any],
) -> TurnCompletionDecision:
    ctx = build_turn_completion_context_from_invocation(invocation_state, strands_message=message)
    if ctx is None:
        return TurnCompletionDecision(scene_id="default", action="continue")
    decision = resolve_turn_completion(ctx)
    removed = apply_turn_completion_decision(decision, invocation_state, strands_message=message)
    if removed and getattr(stop_response, "stop_reason", None) == "tool_use":
        if not pending_tool_names_from_strands_message(message):
            stop_response.stop_reason = "end_turn"
    return decision
