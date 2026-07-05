from __future__ import annotations

from dojoagents.agent.models import ToolCall
from dojoagents.agent.portfolio_tool_repair import merge_remove_holding_tool_calls


def test_merge_remove_holding_tool_calls_noop_for_single_remove() -> None:
    calls = [
        ToolCall(
            id="c1",
            name="portfolio_write_remove_holding",
            arguments={"portfolio_id": "p-1", "ticker": "AAPL", "market": "us"},
        )
    ]
    assert merge_remove_holding_tool_calls(calls) == calls


def test_merge_remove_holding_tool_calls_combines_same_portfolio() -> None:
    calls = [
        ToolCall(
            id="c1",
            name="portfolio_write_remove_holding",
            arguments={"portfolio_id": "p-1", "ticker": "AAPL", "market": "us"},
        ),
        ToolCall(
            id="c2",
            name="portfolio_read_detail",
            arguments={"portfolio_id": "p-1"},
        ),
        ToolCall(
            id="c3",
            name="portfolio_write_remove_holding",
            arguments={"portfolio_id": "p-1", "ticker": "MSFT", "market": "us"},
        ),
    ]

    merged = merge_remove_holding_tool_calls(calls)

    assert len(merged) == 2
    assert merged[0].name == "portfolio_write_remove_candidates"
    assert merged[0].arguments["portfolio_id"] == "p-1"
    assert merged[0].arguments["holdings"] == [
        {"ticker": "AAPL", "market": "us"},
        {"ticker": "MSFT", "market": "us"},
    ]
    assert merged[1].name == "portfolio_read_detail"


def test_merge_remove_holding_tool_calls_keeps_different_portfolios_separate() -> None:
    calls = [
        ToolCall(
            id="c1",
            name="portfolio_write_remove_holding",
            arguments={"portfolio_id": "p-1", "ticker": "AAPL"},
        ),
        ToolCall(
            id="c2",
            name="portfolio_write_remove_holding",
            arguments={"portfolio_id": "p-2", "ticker": "MSFT"},
        ),
    ]

    assert merge_remove_holding_tool_calls(calls) == calls
