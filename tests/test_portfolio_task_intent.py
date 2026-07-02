from __future__ import annotations

import pytest

from dojoagents.agent.harness import HarnessLoopState
from dojoagents.agent.harnesses.portfolio import PortfolioTaskHarness
from dojoagents.agent.harnesses.portfolio_eval import PortfolioEvalSubmission, verify_eval_submission
from dojoagents.agent.harnesses.portfolio_task_intent import (
    classify_portfolio_task,
    is_liquidation_intent,
    order_side_trace,
)
from dojoagents.agent.models import ChatRequest, ToolResult


def _make_request(*, message: str = "test") -> ChatRequest:
    return ChatRequest(
        user_id="u",
        session_id="s",
        channel="dashboard",
        message=message,
        metadata={"dashboard_tab": "folio"},
    )


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("请全部清仓", True),
        ("清仓我的持仓", True),
        ("liquidate all positions", True),
        ("卖出 NVDA 一半", False),
        ("帮我分析一下", False),
    ],
)
def test_is_liquidation_intent(message: str, expected: bool) -> None:
    assert is_liquidation_intent(message) is expected


def test_order_side_trace_detects_buy_and_sell() -> None:
    state = HarnessLoopState(request=_make_request())
    state.tool_results.append(
        ToolResult(
            call_id="call-orders",
            name="portfolio_write_create_orders",
            ok=True,
            data={
                "order_result": {
                    "filled_orders": [
                        {"ticker": "NVDA", "order_side": "sell"},
                        {"ticker": "AAPL", "order_side": "buy"},
                    ]
                }
            },
        )
    )
    has_buy, has_sell = order_side_trace(state)
    assert has_buy is True
    assert has_sell is True


def test_classify_liquidate_task_from_user_message_and_sells() -> None:
    state = HarnessLoopState(request=_make_request(message="全部清仓"))
    state.tool_results.append(
        ToolResult(
            call_id="call-orders",
            name="portfolio_write_create_orders",
            ok=True,
            data={"order_result": {"filled_orders": [{"ticker": "NVDA", "order_side": "sell"}]}},
        )
    )
    assert classify_portfolio_task(state) == "liquidate"


def test_portfolio_harness_allows_liquidation_with_zero_positions() -> None:
    harness = PortfolioTaskHarness()
    state = HarnessLoopState(request=_make_request(message="全部清仓"))
    state.tool_results.extend(
        [
            ToolResult(
                call_id="call-orders",
                name="portfolio_write_create_orders",
                ok=True,
                data={
                    "id": "p-1",
                    "kind": "manual",
                    "order_result": {
                        "filled_orders": [
                            {"ticker": "NVDA", "order_side": "sell", "status": "filled"},
                            {"ticker": "GOOG", "order_side": "sell", "status": "filled"},
                        ]
                    },
                },
            ),
            ToolResult(
                call_id="call-detail",
                name="portfolio_read_detail",
                ok=True,
                data={"id": "p-1", "kind": "manual", "positions": []},
            ),
            ToolResult(
                call_id="call-eval",
                name="portfolio_eval_submit",
                ok=True,
                data={
                    "portfolio_id": "p-1",
                    "task_summary": "Liquidate all holdings",
                    "max_position_count": 0,
                    "require_kind_agent": False,
                },
            ),
        ]
    )

    decision = harness.validate_progress(state)

    assert decision.complete is True


def test_portfolio_harness_rejects_require_kind_agent_on_manual_trade() -> None:
    harness = PortfolioTaskHarness()
    state = HarnessLoopState(request=_make_request(message="全部清仓"))
    state.tool_results.extend(
        [
            ToolResult(
                call_id="call-orders",
                name="portfolio_write_create_orders",
                ok=True,
                data={
                    "order_result": {
                        "filled_orders": [{"ticker": "NVDA", "order_side": "sell"}],
                    }
                },
            ),
            ToolResult(
                call_id="call-detail",
                name="portfolio_read_detail",
                ok=True,
                data={"id": "p-1", "kind": "manual", "positions": []},
            ),
            ToolResult(
                call_id="call-eval",
                name="portfolio_eval_submit",
                ok=True,
                data={
                    "portfolio_id": "p-1",
                    "task_summary": "Liquidate",
                    "require_kind_agent": True,
                    "max_position_count": 0,
                },
            ),
        ]
    )

    decision = harness.validate_progress(state)

    assert decision.complete is False
    assert any("agent-owned" in issue or "require_kind_agent" in issue for issue in decision.issues)
    assert any("require_kind_agent=false" in step for step in decision.next_steps)


def test_verify_eval_submission_max_position_count() -> None:
    submission = PortfolioEvalSubmission(
        portfolio_id="p-1",
        task_summary="Liquidate",
        max_position_count=0,
    )
    issues = verify_eval_submission(
        submission,
        {"id": "p-1", "positions": [{"ticker": "NVDA", "market": "us", "shares": 100}]},
    )
    assert issues
    assert any("at most 0" in issue for issue in issues)

    ok = verify_eval_submission(submission, {"id": "p-1", "positions": []})
    assert ok == []
