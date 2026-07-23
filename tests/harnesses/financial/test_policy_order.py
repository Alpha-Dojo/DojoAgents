from __future__ import annotations

import pytest

from dojoagents.agent.models import ChatRequest, ToolCall, ToolResult
from dojoagents.config.models import AgentsConfig, HarnessConfig
from dojoagents.harnesses.builder import HarnessBuilder
from dojoagents.harnesses.built_in.financial.config import FinancialHarnessConfig
from dojoagents.harnesses.built_in.financial.harness import FinancialHarness
from dojoagents.harnesses.context import HarnessBuildContext, HarnessSessionContext, HarnessTurnContext
from dojoagents.harnesses.decisions import ToolControlDecision
from dojoagents.harnesses.runtime import HarnessRuntime
from dojoagents.harnesses.state import HarnessSessionState
from dojoagents.sessions.models import SessionPrincipal


def _capabilities(tmp_path):
    root = AgentsConfig(
        harness=HarnessConfig(
            config={
                "data_root": str(tmp_path / "data"),
                "portfolio_data_root": str(tmp_path / "portfolio"),
                "refresh_enabled": False,
            }
        )
    )
    build = HarnessBuildContext(root, root.harness.config, tmp_path, tmp_path, "dashboard", None)
    harness = FinancialHarness(FinancialHarnessConfig.from_context(build))
    builder = HarnessBuilder(harness.descriptor)
    harness.configure(builder, build)
    return builder.build()


def _turn(message="创建组合"):
    request = ChatRequest(
        message,
        session_id="s-1",
        principal=SessionPrincipal("alice"),
        channel="dashboard",
    )
    return HarnessTurnContext(
        request,
        HarnessSessionContext(request.principal, request.session_id, HarnessSessionState()),
    )


def test_financial_policy_order_is_fixed(tmp_path):
    capabilities = _capabilities(tmp_path)
    assert [spec.component_id for spec in capabilities.flow_policies] == [
        "financial.turn-scope",
        "financial.portfolio-flow",
        "financial.portfolio-escalation",
        "financial.sector-session",
        "financial.visualization",
        "financial.task.tool-orchestrated",
        "financial.task.artifact-synthesis",
        "financial.completion",
    ]
    assert [spec.component_id for spec in capabilities.tool_transformers] == [
        "financial.portfolio-repair",
        "financial.sector-repair",
    ]


@pytest.mark.asyncio
async def test_portfolio_transformer_merges_batch_calls_then_core_revalidates(tmp_path):
    capabilities = _capabilities(tmp_path)
    validated = []

    async def core_authorizer(call, context):
        return ToolControlDecision("allow", "core")

    runtime = HarnessRuntime(
        capabilities,
        core_safety_prompt="safe",
        core_tool_authorizer=core_authorizer,
        revalidate_tool_call=lambda call: validated.append(call.name),
    )
    turn = _turn()
    await runtime.before_turn(turn)
    calls = (
        ToolCall("c1", "portfolio_write_remove_holding", {"portfolio_id": "p-1", "ticker": "AAPL"}),
        ToolCall("c2", "portfolio_write_remove_holding", {"portfolio_id": "p-1", "ticker": "MSFT"}),
    )
    repaired = await runtime.transform_calls(calls, turn)

    assert len(repaired) == 1
    assert repaired[0].name == "portfolio_write_remove_candidates"
    assert validated == ["portfolio_write_remove_candidates"]


@pytest.mark.asyncio
async def test_portfolio_policy_restricts_analysis_write_and_escalates_user_input(tmp_path):
    capabilities = _capabilities(tmp_path)

    async def core_authorizer(call, context):
        return ToolControlDecision("allow", "core")

    runtime = HarnessRuntime(
        capabilities,
        core_safety_prompt="safe",
        core_tool_authorizer=core_authorizer,
        revalidate_tool_call=lambda call: None,
    )
    turn = _turn("分析候选池")
    turn.tool_results.append(ToolResult("r1", "portfolio_read_detail", True, data={"id": "p-1"}))
    blocked = await runtime.authorize(ToolCall("w1", "portfolio_write_create", {"name": "unexpected"}), turn)
    assert blocked.action == "block"

    turn.tool_results.append(
        ToolResult(
            "w2",
            "portfolio_write_create_orders",
            False,
            error="capital",
            metadata={
                "escalation": {
                    "code": "capital_budget_exceeded",
                    "message": "raise capital",
                    "source_tool": "portfolio_write_create_orders",
                    "requires_user_input": True,
                }
            },
        )
    )
    decision = await runtime.evaluate_completion(turn)
    assert decision.action == "needs_user_input"
    assert decision.code == "capital_budget_exceeded"
