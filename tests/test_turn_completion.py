from __future__ import annotations

from unittest.mock import MagicMock

from dojoagents.harnesses.built_in.financial.policies.legacy_harness import HarnessLoopState
from dojoagents.agent.models import ChatRequest, LLMResult, ToolCall, ToolResult
from dojoagents.harnesses.built_in.financial.policies.legacy_completion import (
    TurnCompletionContext,
    absorb_tools_from_llm_result,
    absorb_tools_from_strands_message,
    apply_turn_completion_after_model,
    apply_turn_completion_to_strands_stop_response,
    has_deliverable,
    register_turn_completion_rule,
    resolve_turn_completion,
)
from dojoagents.harnesses.built_in.financial.policies import (
    legacy_completion as turn_completion_module,
)


def _request() -> ChatRequest:
    return ChatRequest(
        message="清仓腾讯",
        user_id="u1",
        session_id="s1",
        channel="dashboard",
        metadata={"locale": "zh"},
    )


def _invocation(**overrides) -> dict:
    state = HarnessLoopState(request=_request())
    base = {
        "_dojo_request": _request(),
        "_dojo_harness_state": state,
        "_dojo_task_harnesses": [],
        "request_state": {},
    }
    base.update(overrides)
    return base


def test_has_deliverable_detects_markdown_summary() -> None:
    text = "## ✅ 清仓完成\n\n| 标的 | 0700.HK |\n| 操作 | 卖出 |"
    assert has_deliverable(text)


def test_absorb_viz_from_llm_result_when_deliverable_and_viz_forbidden() -> None:
    inv = _invocation()
    inv["_dojo_harness_state"].tool_results = (
        ToolResult(
            call_id="e1",
            name="portfolio_eval_submit",
            ok=True,
            data={"accepted": True},
        ),
        ToolResult(
            call_id="o1",
            name="portfolio_write_create_order",
            ok=True,
            data={"order_result": {"order_side": "sell"}},
        ),
    )
    harness = MagicMock()
    harness.matches.return_value = True
    harness.validate_progress.return_value = MagicMock(complete=True)
    inv["_dojo_task_harnesses"] = [harness]

    llm = LLMResult(
        content="## ✅ 清仓完成\n\n腾讯已卖出，持仓为 0。" + ("详情补充。" * 10),
        tool_calls=[ToolCall(id="v1", name="agent_viz_build", arguments={"kind": "kpi_row", "data": {}})],
    )
    decision = apply_turn_completion_after_model(llm, inv)
    assert decision.scene_id == "harness_complete"
    assert llm.tool_calls == []
    assert inv["request_state"]["stop_event_loop"] is True


def test_no_absorb_without_deliverable() -> None:
    inv = _invocation()
    inv["_dojo_harness_state"].tool_results = (ToolResult(call_id="e1", name="portfolio_eval_submit", ok=True, data={"accepted": True}),)
    llm = LLMResult(
        content="",
        tool_calls=[ToolCall(id="v1", name="agent_viz_build", arguments={})],
    )
    decision = apply_turn_completion_after_model(llm, inv)
    assert decision.action == "continue"
    assert len(llm.tool_calls) == 1


def test_absorb_strands_message_updates_stop_reason() -> None:
    inv = _invocation()
    inv["_dojo_harness_state"].tool_results = (
        ToolResult(call_id="w1", name="portfolio_write_create_order", ok=True, data={}),
        ToolResult(call_id="e1", name="portfolio_eval_submit", ok=True, data={"accepted": True}),
    )
    harness = MagicMock()
    harness.matches.return_value = True
    harness.validate_progress.return_value = MagicMock(complete=True)
    inv["_dojo_task_harnesses"] = [harness]

    message = {
        "role": "assistant",
        "content": [
            {"text": "## 完成\n\n" + ("x" * 80)},
            {"toolUse": {"toolUseId": "v1", "name": "agent_viz_build", "input": {}}},
        ],
    }

    class StopResponse:
        stop_reason = "tool_use"

    stop_response = StopResponse()
    decision = apply_turn_completion_to_strands_stop_response(message, stop_response, inv)
    assert decision.scene_id == "harness_complete"
    assert stop_response.stop_reason == "end_turn"
    assert message["content"] == [{"text": message["content"][0]["text"]}]


def test_forbidden_viz_only_absorbs_viz_tool() -> None:
    harness_state = _invocation()["_dojo_harness_state"]
    harness_state.tool_results = (ToolResult(call_id="w1", name="portfolio_write_create_order", ok=True, data={}),)
    ctx = TurnCompletionContext(
        channel="dashboard",
        user_message="分析",
        locale="zh",
        user_visible_text="## 分析结论\n\n" + ("内容" * 30),
        pending_tool_names=("agent_viz_build", "portfolio_read_detail"),
        harness_state=harness_state,
    )
    decision = resolve_turn_completion(ctx)
    assert decision.scene_id == "forbidden_viz_absorb"
    assert decision.absorb_tool_names == frozenset({"agent_viz_build"})
    assert decision.stop_event_loop is False


def test_custom_turn_completion_rule() -> None:
    saved = list(turn_completion_module._extra_rules)

    def _rule(ctx: TurnCompletionContext):
        if "stop-after-text" in ctx.user_message and ctx.pending_tool_names:
            from dojoagents.harnesses.built_in.financial.policies.legacy_completion import (
                TurnCompletionDecision,
            )

            return TurnCompletionDecision(
                scene_id="custom_stop",
                action="absorb_tools",
                absorb_all_pending_tools=True,
                stop_event_loop=True,
                priority=200,
            )
        return None

    try:
        register_turn_completion_rule(_rule, priority=200)
        ctx = TurnCompletionContext(
            channel="dashboard",
            user_message="stop-after-text",
            locale="en",
            user_visible_text="Final answer " * 10,
            pending_tool_names=("agent_viz_build",),
        )
        decision = resolve_turn_completion(ctx)
        assert decision.scene_id == "custom_stop"
        llm = LLMResult(content=ctx.user_visible_text, tool_calls=[ToolCall(id="1", name="agent_viz_build", arguments={})])
        removed = absorb_tools_from_llm_result(llm, absorb_all=True)
        assert removed == ["agent_viz_build"]
    finally:
        turn_completion_module._extra_rules[:] = saved


def test_absorb_tools_from_strands_message() -> None:
    message = {
        "role": "assistant",
        "content": [
            {"text": "done"},
            {"toolUse": {"name": "agent_viz_build", "toolUseId": "1"}},
            {"toolUse": {"name": "portfolio_read_detail", "toolUseId": "2"}},
        ],
    }
    removed = absorb_tools_from_strands_message(message, tool_names={"agent_viz_build"})
    assert removed == ["agent_viz_build"]
    assert len(message["content"]) == 2
