from __future__ import annotations

import pytest

from dojoagents.agent.presenters import ToolResultPresenterRegistry
from dojoagents.agent.models import ToolCall
from dojoagents.tools.dojo_sdk_tool import DojoSDKToolManager
from dojoagents.tools.agent_viz import build_viz_blocks, get_agent_viz_specs
from dojoagents.tools.executor import ToolExecutor
from dojoagents.tools.registry import ToolRegistry
from dojoagents.tools.sandbox import SandboxPolicy


def _tool_registry() -> ToolRegistry:
    registry = ToolRegistry()
    for spec in get_agent_viz_specs():
        registry.register(spec)
    return registry


async def _call_build(args: dict):
    spec = _tool_registry().get("agent_viz_build")
    assert spec is not None
    return await spec.handler(args)


@pytest.mark.asyncio
async def test_agent_viz_build_ticker_quote_returns_quote_card() -> None:
    result = await _call_build(
        {
            "mapping_hint": "ticker_quote",
            "data": {
                "ticker": "AAPL",
                "market": "us",
                "name": {"en": "Apple"},
                "last_price": 200,
                "change_percent": 1.5,
                "pe": 30,
                "pb": 40,
                "market_cap": 3e12,
                "high": 201,
                "low": 198,
            },
        }
    )

    assert result["data"]["block_count"] == 1
    assert result["viz_blocks"][0]["kind"] == "quote_card"
    assert result["viz_blocks"][0]["payload"]["ticker"] == "AAPL"


@pytest.mark.asyncio
async def test_agent_viz_build_batch_ticker_quotes_returns_table() -> None:
    result = await _call_build(
        {
            "source_tool": "get_ticker_realtime_quote",
            "data": {
                "market": "us",
                "count": 2,
                "not_found": [],
                "items": [
                    {
                        "ticker": "AAPL",
                        "market": "us",
                        "name": {"en": "Apple"},
                        "last_price": 200,
                        "change_percent": 1.5,
                        "pe": 30,
                        "market_cap": 3e12,
                    },
                    {
                        "ticker": "MSFT",
                        "market": "us",
                        "name": {"en": "Microsoft"},
                        "last_price": 400,
                        "change_percent": -0.5,
                        "pe": 35,
                        "market_cap": 2e12,
                    },
                ],
            },
        }
    )

    assert result["data"]["block_count"] == 1
    assert result["viz_blocks"][0]["kind"] == "table"
    assert len(result["viz_blocks"][0]["payload"]["rows"]) == 2


@pytest.mark.asyncio
async def test_agent_viz_build_ticker_kline_returns_price_kline() -> None:
    result = await _call_build(
        {
            "source_tool": "dojo.sdk.stock.kline",
            "data": {
                "ticker": "002008.SZ",
                "market": "cn",
                "chart_change_pct": 12.5,
                "klines_chart": [
                    {"datetime": "2026-06-11", "open": 120.0, "high": 125.0, "low": 118.0, "close": 121.45, "volume": 1000},
                    {"datetime": "2026-06-12", "open": 121.0, "high": 123.0, "low": 117.0, "close": 119.12, "volume": 900},
                ],
            },
        }
    )

    assert result["data"]["kinds"] == ["price_kline"]
    assert result["viz_blocks"][0]["subtitle"] == "+12.50%"
    assert len(result["viz_blocks"][0]["payload"]["bars"]) == 2


@pytest.mark.asyncio
async def test_agent_viz_build_portfolio_analysis_returns_market_blocks() -> None:
    result = await _call_build(
        {
            "mapping_hint": "portfolio_analysis",
            "data": {
                "id": "p1",
                "name": "Test Folio",
                "stats_by_market": {
                    "us": {"cumulative_return_pct": 12.5, "sharpe_ratio": 1.2, "max_drawdown_pct": -8.0},
                    "cn": {"cumulative_return_pct": -2.0, "sharpe_ratio": 0.4, "max_drawdown_pct": -12.0},
                },
                "net_value_by_market": {"us": 1000000.0, "cn": 500000.0},
                "holdings": [
                    {"ticker": "AAPL", "market": "us", "name": "Apple", "weight": 60.0, "change_percent": 1.2},
                    {"ticker": "MSFT", "market": "us", "name": "Microsoft", "weight": 40.0, "change_percent": -0.5},
                    {"ticker": "600519", "market": "cn", "name": "Moutai", "weight": 100.0, "change_percent": 0.8},
                ],
                "nav_by_market": {
                    "us": [{"date": "2024-01-01", "value": 100}, {"date": "2024-01-02", "value": 101}],
                    "cn": [{"date": "2024-01-01", "value": 100}, {"date": "2024-01-02", "value": 99}],
                },
            },
        }
    )

    kinds = {block["kind"] for block in result["viz_blocks"]}
    assert {"kpi_row", "donut", "table", "line"}.issubset(kinds)


@pytest.mark.asyncio
async def test_agent_viz_build_generic_table_and_line() -> None:
    table = await _call_build(
        {
            "kind": "table",
            "data": {"rows": [{"ticker": "AAPL", "score": 98}, {"ticker": "MSFT", "score": 95}]},
        }
    )
    line = await _call_build(
        {
            "kind": "line",
            "data": {"series": [{"id": "nav", "label": "NAV", "points": [{"date": "2026-01-01", "value": 1}, {"date": "2026-01-02", "value": 2}]}]},
        }
    )

    assert table["viz_blocks"][0]["kind"] == "table"
    assert table["viz_blocks"][0]["payload"]["columns"][0]["key"] == "ticker"
    assert line["viz_blocks"][0]["kind"] == "line"


@pytest.mark.asyncio
async def test_agent_viz_build_generic_table_accepts_column_labels_and_array_rows() -> None:
    result = await _call_build(
        {
            "kind": "table",
            "title": "低估值高息美股组合",
            "subtitle": "等权配置",
            "data": {
                "columns": ["代码", "名称", "股价", "仓位"],
                "rows": [
                    ["PFE", "辉瑞", "$24.07", "20.0%"],
                    ["UPS", "联合包裹", "$102.45", "20.0%"],
                ],
            },
        }
    )

    assert result["data"] == {"block_count": 1, "kinds": ["table"]}
    block = result["viz_blocks"][0]
    assert block["kind"] == "table"
    assert block["title"] == "低估值高息美股组合"
    assert block["subtitle"] == "等权配置"
    assert block["payload"]["columns"] == [
        {"key": "col_0", "label": "代码"},
        {"key": "col_1", "label": "名称"},
        {"key": "col_2", "label": "股价"},
        {"key": "col_3", "label": "仓位"},
    ]
    assert block["payload"]["rows"][0] == {"col_0": "PFE", "col_1": "辉瑞", "col_2": "$24.07", "col_3": "20.0%"}


@pytest.mark.asyncio
async def test_agent_viz_build_generic_sparkline() -> None:
    result = await _call_build({"kind": "sparkline", "data": {"values": [1, 2, 3], "change_percent": 2.5}})

    assert result["viz_blocks"][0]["kind"] == "sparkline"
    assert result["viz_blocks"][0]["payload"]["points"] == [{"value": 1}, {"value": 2}, {"value": 3}]


@pytest.mark.asyncio
async def test_agent_viz_build_generic_kpi_row_accepts_metrics() -> None:
    result = await _call_build(
        {
            "kind": "kpi_row",
            "title": "核心指标",
            "data": {
                "metrics": [
                    {"label": "加权平均 PE", "value": "13.50x", "trend": "down"},
                    {"label": "加权股息率", "value": "5.73%", "trend": "up"},
                ]
            },
        }
    )

    assert result["data"] == {"block_count": 1, "kinds": ["kpi_row"]}
    assert result["viz_blocks"][0]["kind"] == "kpi_row"
    assert result["viz_blocks"][0]["payload"]["items"][0]["tone"] == "negative"
    assert result["viz_blocks"][0]["payload"]["items"][1]["tone"] == "positive"


@pytest.mark.asyncio
async def test_agent_viz_build_generic_hbar_rank_accepts_items() -> None:
    result = await _call_build(
        {
            "kind": "hbar_rank",
            "title": "股息率排名",
            "data": {
                "items": [
                    {"label": "PFE 辉瑞", "value": 7.15, "sub": "PE: 18.37"},
                    {"label": "BMY 施贵宝", "value": 4.56, "sub": "PE: 15.41"},
                ]
            },
        }
    )

    assert result["data"] == {"block_count": 1, "kinds": ["hbar_rank"]}
    assert result["viz_blocks"][0]["kind"] == "hbar_rank"
    assert len(result["viz_blocks"][0]["payload"]["gainers"]) == 2


@pytest.mark.asyncio
async def test_agent_viz_build_generic_hbar_rank_falls_back_to_bar_for_series_comparison() -> None:
    result = await _call_build(
        {
            "kind": "hbar_rank",
            "title": "估值对比",
            "data": {
                "categories": ["恒生指数", "标普500"],
                "series": [
                    {"name": "当前PE", "label": "当前PE", "values": [9.8, 31.68]},
                    {"name": "历史中位数PE", "label": "历史中位数PE", "values": [12.5, 15.08]},
                ],
            },
        }
    )

    assert result["data"] == {"block_count": 1, "kinds": ["bar"]}
    assert result["viz_blocks"][0]["kind"] == "bar"


@pytest.mark.asyncio
async def test_agent_viz_build_generic_bar_accepts_label_value_arrays() -> None:
    result = await _call_build(
        {
            "kind": "bar",
            "title": "当前PE vs 历史中位数",
            "data": {
                "labels": ["恒生指数", "沪深300", "标普500"],
                "pe_current": [9.8, 13.2, 31.68],
                "pe_median": [12.5, 13.5, 15.08],
            },
        }
    )

    assert result["data"] == {"block_count": 1, "kinds": ["bar"]}
    block = result["viz_blocks"][0]
    assert block["kind"] == "bar"
    assert block["payload"]["categories"] == ["恒生指数", "沪深300", "标普500"]
    assert block["payload"]["series"][0]["label"] == "当前PE"
    assert block["payload"]["series"][1]["label"] == "历史中位数PE"


@pytest.mark.asyncio
async def test_agent_viz_build_market_overview_returns_kpis_and_weighted_pe_bar() -> None:
    result = await _call_build(
        {
            "source_tool": "get_market_overview",
            "data": {
                "days": 5,
                "markets": {
                    "hk": {"market": "hk", "listed_count": 2899, "total_market_cap": 103.0e12, "weighted_pe": 10.38},
                    "cn": {"market": "cn", "listed_count": 5245, "total_market_cap": 129.0e12, "weighted_pe": 17.24},
                    "us": {"market": "us", "listed_count": 13166, "total_market_cap": 109.0e12, "weighted_pe": 23.74},
                },
                "benchmarks": {},
            },
        }
    )

    assert result["data"] == {"block_count": 2, "kinds": ["kpi_row", "bar"]}
    kpi_block, bar_block = result["viz_blocks"]
    assert kpi_block["kind"] == "kpi_row"
    assert bar_block["kind"] == "bar"
    assert bar_block["title"] == "Valuation comparison"
    assert bar_block["payload"]["categories"] == ["US", "CN", "HK"]
    assert bar_block["payload"]["series"] == [{"label": "Weighted PE", "values": [23.74, 17.24, 10.38]}]


@pytest.mark.asyncio
async def test_agent_viz_build_unknown_data_returns_empty_blocks() -> None:
    result = await _call_build({"kind": "auto", "data": {"message": "plain text only"}})

    assert result["data"] == {"block_count": 0, "kinds": []}
    assert result["viz_blocks"] == []
    assert "No supported visualization shape" in result["content"]


def test_build_viz_blocks_rejects_invalid_kind() -> None:
    with pytest.raises(RuntimeError, match="Unsupported visualization kind"):
        build_viz_blocks({"rows": []}, kind="bubble")


def test_presenter_auto_generates_quote_card_for_sdk_quote() -> None:
    normalized = ToolResultPresenterRegistry().normalize(
        "dojo.sdk.stock.current_quote",
        {
            "data": {
                "quotes": [
                    {
                        "symbol": "AAPL",
                        "market": "us",
                        "name": {"en": "Apple"},
                        "last_price": 200,
                        "change_percent": 1.5,
                    }
                ]
            }
        },
    )

    assert normalized["viz_blocks"][0]["kind"] == "quote_card"
    assert normalized["viz_blocks"][0]["payload"]["ticker"] == "AAPL"


def test_presenter_auto_generates_price_kline_for_sdk_kline() -> None:
    normalized = ToolResultPresenterRegistry().normalize(
        "dojo.sdk.benchmark.kline",
        {
            "data": {
                "symbol": "HSI",
                "market": "hk",
                "chart_change_pct": -1.59,
                "klines_chart": [
                    {"datetime": "2026-06-11", "open": 120.0, "high": 125.0, "low": 118.0, "close": 121.45, "volume": 1000},
                    {"datetime": "2026-06-12", "open": 121.0, "high": 123.0, "low": 117.0, "close": 119.12, "volume": 900},
                ],
            }
        },
    )

    assert normalized["viz_blocks"][0]["kind"] == "price_kline"
    assert normalized["viz_blocks"][0]["subtitle"] == "-1.59%"


def test_presenter_preserves_explicit_viz_blocks() -> None:
    explicit = [{"id": "viz-1", "kind": "table", "title": "Rows", "payload": {"rows": []}}]
    normalized = ToolResultPresenterRegistry().normalize(
        "agent_viz_build",
        {"data": {"block_count": 1}, "viz_blocks": explicit},
    )

    assert normalized["viz_blocks"] == explicit


def test_presenter_ignores_auto_viz_failures(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*args, **kwargs):
        raise RuntimeError("mapper broke")

    monkeypatch.setattr("dojoagents.agent.presenters.build_viz_blocks", boom)
    normalized = ToolResultPresenterRegistry().normalize(
        "dojo.sdk.stock.current_quote",
        {"data": {"symbol": "AAPL", "last_price": 200}},
    )

    assert normalized["viz_blocks"] == []


@pytest.mark.asyncio
async def test_dojo_sdk_ok_includes_structured_data() -> None:
    manager = DojoSDKToolManager()
    payload = {"symbol": "AAPL", "last_price": 200}

    result = await manager._ok(payload)

    assert result["data"] == payload
    assert result["metadata"] == {"ok": True}
    assert '"symbol": "AAPL"' in result["content"]


@pytest.mark.asyncio
async def test_tool_executor_preserves_agent_viz_blocks() -> None:
    executor = ToolExecutor(_tool_registry(), SandboxPolicy(timeout_seconds=5))
    result = await executor.execute_one(
        ToolCall(
            id="call-viz",
            name="agent_viz_build",
            arguments={
                "mapping_hint": "ticker_quote",
                "data": {"ticker": "AAPL", "market": "us", "last_price": 200, "change_percent": 1.5},
            },
        ),
        session_id="s1",
    )

    assert result.ok is True
    assert result.call_id == "call-viz"
    assert result.viz_blocks
    assert result.viz_blocks[0]["kind"] == "quote_card"
