from __future__ import annotations

import pytest

from dojoagents.harnesses.built_in.financial.policies.legacy_harness import HarnessLoopState
from dojoagents.harnesses.built_in.financial.policies.legacy.portfolio import PortfolioTaskHarness
from dojoagents.agent.models import ChatRequest, LLMResult, ToolCall, ToolResult
from dojoagents.agent.providers import StaticLLMProvider
from dojoagents.harnesses.built_in.financial.policies.turn_intent import (
    TurnIntentResult,
    build_turn_intent_anchor,
    build_turn_intent_anchor_async,
    classify_turn_intent,
)


def _request(message: str = "分析候选池", *, history: list | None = None) -> ChatRequest:
    metadata: dict = {"dashboard_tab": "folio", "locale": "zh"}
    if history is not None:
        metadata["history"] = history
    return ChatRequest(
        user_id="local",
        session_id="sess-1",
        channel="dashboard",
        message=message,
        metadata=metadata,
    )


def test_turn_intent_anchor_only_when_history_exists() -> None:
    assert build_turn_intent_anchor(_request(), TurnIntentResult()) == ""
    anchor = build_turn_intent_anchor(
        _request(
            "帮我分析全球AI大模型概念组合",
            history=[{"role": "user", "content": "创建一个半导体组合"}],
        ),
        TurnIntentResult(mode="new_task"),
    )
    assert "当前任务" in anchor
    assert "全球AI大模型概念组合" in anchor
    assert "不要继续执行旧任务" in anchor


def test_turn_intent_anchor_continuation_resumes_prior_task() -> None:
    anchor = build_turn_intent_anchor(
        _request(
            "继续执行前述任务",
            history=[
                {"role": "user", "content": "构建半导体行业上下游关系图谱"},
                {"role": "assistant", "content": "工具执行已完成，请查看上方步骤与组合更新。"},
            ],
        ),
        TurnIntentResult(
            mode="continue_unfinished",
            prior_task_summary="构建半导体行业上下游关系图谱",
            last_turn_status="tools_only_no_deliverable",
        ),
    )
    assert "续做未完成工作" in anchor
    assert "半导体行业上下游关系图谱" in anchor
    assert "不要继续执行旧任务" not in anchor


@pytest.mark.asyncio
async def test_classify_turn_intent_uses_llm() -> None:
    provider = StaticLLMProvider(
        [LLMResult(content=('{"continue_unfinished": true, ' '"prior_task_summary": "构建半导体行业上下游关系图谱", ' '"last_turn_status": "tools_only_no_deliverable"}'))]
    )
    request = _request(
        "继续执行前述任务",
        history=[
            {"role": "user", "content": "构建半导体行业上下游关系图谱"},
            {"role": "assistant", "content": "工具执行已完成，请查看上方步骤与组合更新。"},
        ],
    )
    intent = await classify_turn_intent(request, provider, model="test-model")
    assert intent.mode == "continue_unfinished"
    assert "半导体" in intent.prior_task_summary
    assert provider.calls


@pytest.mark.asyncio
async def test_build_turn_intent_anchor_async() -> None:
    provider = StaticLLMProvider([LLMResult(content=('{"continue_unfinished": false, ' '"prior_task_summary": "", ' '"last_turn_status": "complete"}'))])
    anchor, intent = await build_turn_intent_anchor_async(
        _request(
            "帮我分析全球AI大模型概念组合",
            history=[{"role": "user", "content": "创建一个半导体组合"}],
        ),
        provider,
        model="test-model",
    )
    assert intent.mode == "new_task"
    assert "当前任务" in anchor
    assert "不要继续执行旧任务" in anchor
    assert "execute_code 本轮不可用" not in anchor
    assert "execute_code unavailable" not in anchor


def test_portfolio_harness_does_not_match_folio_tab_alone() -> None:
    harness = PortfolioTaskHarness()
    state = HarnessLoopState(request=_request())
    assert harness.matches(_request(), state) is False


def test_portfolio_harness_matches_after_write_tool() -> None:
    harness = PortfolioTaskHarness()
    state = HarnessLoopState(request=_request("创建组合"))
    state.tool_results.append(
        ToolResult(
            call_id="c1",
            name="portfolio_write_create",
            ok=True,
            data={"id": "p-1"},
            resource_changes=[{"resource": "portfolio", "action": "create", "portfolio_id": "p-1"}],
        )
    )
    assert harness.matches(_request("创建组合"), state) is True


def test_portfolio_harness_blocks_create_during_analysis_run() -> None:
    harness = PortfolioTaskHarness()
    state = HarnessLoopState(request=_request("分析候选池"))
    state.tool_results.append(ToolResult(call_id="c1", name="portfolio_read_search", ok=True, data={"items": []}))
    state.tool_results.append(ToolResult(call_id="c2", name="portfolio_read_detail", ok=True, data={"id": "p-1"}))
    blocked = harness.block_tool_call(
        ToolCall(id="c3", name="portfolio_write_create", arguments={"name": "New"}),
        state,
    )
    assert blocked is not None
    assert "portfolio_write_create" in blocked


def test_portfolio_harness_allows_create_after_research_for_explicit_create_task() -> None:
    harness = PortfolioTaskHarness()
    state = HarnessLoopState(request=_request("Pick 5 undervalued US high-dividend stocks and create a portfolio."))
    state.tool_results.append(
        ToolResult(
            call_id="c1",
            name="screen_market_stocks",
            ok=True,
            data={"items": []},
        )
    )

    blocked = harness.block_tool_call(
        ToolCall(
            id="c2",
            name="portfolio_write_create",
            arguments={"name": "US High Dividend"},
        ),
        state,
    )

    assert blocked is None


def test_portfolio_harness_blocks_rename_during_analysis_run() -> None:
    harness = PortfolioTaskHarness()
    state = HarnessLoopState(request=_request("Analyze the existing portfolio."))
    state.tool_results.append(
        ToolResult(
            call_id="c1",
            name="portfolio_read_detail",
            ok=True,
            data={"id": "p-1"},
        )
    )

    blocked = harness.block_tool_call(
        ToolCall(
            id="c2",
            name="portfolio_write_rename",
            arguments={"portfolio_id": "p-1", "name": "Renamed"},
        ),
        state,
    )

    assert blocked is not None
    assert "read/analysis only" in blocked
