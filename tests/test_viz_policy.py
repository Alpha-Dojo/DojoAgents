from __future__ import annotations

from dojoagents.agent.models import ToolResult
from dojoagents.harnesses.built_in.financial.policies.visualization_rules import (
    VizPolicyContext,
    VizPolicyMatch,
    build_viz_policy_catalog,
    build_viz_policy_context,
    build_viz_policy_turn_anchor,
    check_agent_viz_build,
    register_viz_policy_rule,
    resolve_viz_policy,
)
from dojoagents.agent.models import ChatRequest


def _request(message: str = "分析") -> ChatRequest:
    return ChatRequest(
        message=message,
        user_id="u1",
        session_id="s1",
        channel="dashboard",
        metadata={"locale": "zh"},
    )


def test_catalog_lists_builtin_scenes() -> None:
    catalog = build_viz_policy_catalog("zh")
    assert "portfolio_mutating_task" in catalog
    assert "portfolio_eval_accepted" in catalog
    assert "register_viz_policy_rule" in catalog


def test_blocks_agent_viz_after_portfolio_eval_accepted() -> None:
    ctx = VizPolicyContext(
        channel="dashboard",
        user_message="清仓",
        locale="zh",
        tool_results=(
            ToolResult(
                call_id="e1",
                name="portfolio_eval_submit",
                ok=True,
                data={"accepted": True, "portfolio_id": "p-1"},
            ),
        ),
    )
    decision = check_agent_viz_build(ctx)
    assert decision.block_agent_viz_build
    assert decision.match.scene_id == "portfolio_eval_accepted"


def test_blocks_agent_viz_during_portfolio_write_flow() -> None:
    ctx = VizPolicyContext(
        channel="dashboard",
        user_message="卖出腾讯",
        locale="en",
        tool_results=(
            ToolResult(
                call_id="o1",
                name="portfolio_write_create_order",
                ok=True,
                data={"order_result": {"order_side": "sell", "ticker": "0700.HK"}},
            ),
        ),
    )
    decision = check_agent_viz_build(ctx)
    assert decision.block_agent_viz_build
    assert decision.match.scene_id == "portfolio_mutating_task"


def test_allows_optional_for_read_only_analysis() -> None:
    ctx = VizPolicyContext(
        channel="dashboard",
        user_message="分析组合",
        locale="zh",
        tool_results=(ToolResult(call_id="d1", name="portfolio_read_detail", ok=True, data={"id": "p-1"}),),
    )
    decision = check_agent_viz_build(ctx)
    assert not decision.block_agent_viz_build
    assert decision.match.scene_id == "exploratory_read_analysis"
    assert decision.match.stance == "optional"


def test_encouraged_when_execute_code_has_viz_hint() -> None:
    ctx = VizPolicyContext(
        channel="dashboard",
        user_message="回撤分析",
        locale="en",
        tool_results=(
            ToolResult(
                call_id="c1",
                name="execute_code",
                ok=True,
                content='stdout\n--- viz_hint ---\n{"mapping_hint":"drawdown_analysis"}',
                data={"dates": ["2026-01-01"], "prices": [100.0, 95.0]},
            ),
        ),
    )
    match = resolve_viz_policy(ctx)
    assert match.scene_id == "quant_viz_data_ready"
    assert match.stance == "encouraged"


def test_turn_anchor_for_transactional_message() -> None:
    anchor = build_viz_policy_turn_anchor(_request("请对我的组合全部清仓"), "zh")
    assert anchor
    assert "禁止" in anchor
    assert "agent_viz_build" in anchor


def test_custom_rule_can_forbid_new_scene() -> None:
    from dojoagents.harnesses.built_in.financial.policies import (
        visualization_rules as viz_policy_module,
    )

    saved = list(viz_policy_module._extra_rules)

    def _custom_rule(ctx: VizPolicyContext) -> VizPolicyMatch | None:
        if "no-viz-demo" in ctx.user_message:
            return VizPolicyMatch(
                scene_id="custom_demo",
                stance="forbidden",
                reason_en="Custom demo forbids viz.",
                reason_zh="自定义演示禁止可视化。",
                priority=200,
            )
        return None

    try:
        register_viz_policy_rule(_custom_rule, priority=200)
        ctx = build_viz_policy_context(_request("no-viz-demo please"))
        decision = check_agent_viz_build(ctx)
        assert decision.block_agent_viz_build
        assert decision.match.scene_id == "custom_demo"
    finally:
        viz_policy_module._extra_rules[:] = saved
