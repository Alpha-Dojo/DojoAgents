# tests/test_dojo_sdk_tool.py
from __future__ import annotations

import json
import os
from unittest.mock import AsyncMock, patch

import pytest

from dojoagents.agent.models import ToolCall
from dojoagents.agent.runtime import Runtime
from dojoagents.config.models import DojoSDKConfig
from dojoagents.tools.dojo_sdk_tool import (
    DojoSDKToolManager,
    HF_REGISTRY,
    OFFLINE_TOOL_BINDINGS,
    get_dojo_sdk_specs,
)
from dojoagents.tools.executor import ToolExecutor
from dojoagents.tools.registry import ToolRegistry
from dojoagents.tools.sandbox import SandboxPolicy
from dojo.types.models import CurrentQuoteResponse, StockKlineResponse, StockNewsResponse

YSTOCK_INFO_REPRO_ARGS = {
    "symbols": ["SPY", "2800.HK", "510300.SH"],
    "market": "us",
    "only_simple_fields": True,
}
YSTOCK_INFO_REPRO_SYMBOLS = {"SPY", "2800.HK", "510300.SH"}


def test_hf_registry_coverage():
    assert set(OFFLINE_TOOL_BINDINGS).issubset(set(HF_REGISTRY))
    specs = get_dojo_sdk_specs()
    assert len(specs) == len(OFFLINE_TOOL_BINDINGS)
    assert len({spec.name for spec in specs}) == len(OFFLINE_TOOL_BINDINGS)


def test_dojo_sdk_tools_discovery():
    runtime = Runtime.from_default_config()
    all_tools = [spec.name for spec in runtime.agent.tool_executor.registry.all()]

    assert "dojo.sdk.stock.kline" in all_tools
    assert "dojo.sdk.stock.current_quote" in all_tools
    assert "dojo.sdk.sector.precomputed_sector_alpha_factors_daily" in all_tools
    assert "dojo.sdk.sector.precomputed_ticker_alpha_factors_daily" in all_tools
    assert "dojo.sdk.get_ticker" not in all_tools


@pytest.mark.asyncio
async def test_dojo_sdk_stock_kline_tool():
    registry = ToolRegistry()
    for spec in get_dojo_sdk_specs():
        registry.register(spec)

    executor = ToolExecutor(registry, SandboxPolicy())
    mock_response = StockKlineResponse(
        total_num=1,
        data=[
            {
                "symbol": "AAPL",
                "kline_t": "1D",
                "bar_time": "2026-06-04",
                "open": 180.0,
                "high": 182.0,
                "low": 179.0,
                "close": 181.5,
                "volume": 1000000,
                "amount": 181500000.0,
                "ts": "2026-05-01T00:00:00Z",
            }
        ],
    )
    mock_get_kline = AsyncMock(return_value=mock_response)

    with patch("dojoagents.tools.dojo_sdk_tool.AsyncDojo") as mock_async_dojo:
        instance = mock_async_dojo.return_value
        instance.stocks.get_kline = mock_get_kline

        result = await executor.execute_one(
            ToolCall(
                id="tc-stock-kline",
                name="dojo.sdk.stock.kline",
                arguments={"symbol": "AAPL", "kline_t": "1d", "limit": 10},
            )
        )

        assert result.ok
        data = json.loads(result.content)
        assert data["total_num"] == 1
        assert data["data"][0]["symbol"] == "AAPL"
        mock_get_kline.assert_called_once_with(
            symbol="AAPL",
            kline_t="1D",
            start_time=None,
            end_time=None,
            price_adj_type=None,
            price_adj_date=None,
            limit=10,
        )


@pytest.mark.asyncio
async def test_dojo_sdk_stock_current_quote_tool():
    registry = ToolRegistry()
    for spec in get_dojo_sdk_specs():
        registry.register(spec)

    executor = ToolExecutor(registry, SandboxPolicy())
    mock_response = CurrentQuoteResponse(
        symbol="AAPL",
        price=180.5,
        change=1.5,
        change_pct=0.84,
    )
    mock_get_quote = AsyncMock(return_value=mock_response)

    with patch("dojoagents.tools.dojo_sdk_tool.AsyncDojo") as mock_async_dojo:
        instance = mock_async_dojo.return_value
        instance.stocks.get_quote = mock_get_quote

        result = await executor.execute_one(
            ToolCall(
                id="tc-stock-quote",
                name="dojo.sdk.stock.current_quote",
                arguments={"symbols": ["AAPL"]},
            )
        )

        assert result.ok
        data = json.loads(result.content)
        assert data["symbol"] == "AAPL"
        assert data["price"] == 180.5
        mock_get_quote.assert_called_once_with(symbols=["AAPL"])


@pytest.mark.asyncio
async def test_dojo_sdk_stock_ystock_info_forwards_repro_args():
    """Mock: repro args from SSE run must reach get_ystock_info unchanged."""
    registry = ToolRegistry()
    for spec in get_dojo_sdk_specs():
        registry.register(spec)

    executor = ToolExecutor(registry, SandboxPolicy())
    result = await executor.execute_one(
        ToolCall(
            id="tc-stock-ystock-info",
            name="dojo.sdk.stock.ystock_info",
            arguments=dict(YSTOCK_INFO_REPRO_ARGS),
        )
    )

    assert result.ok
    data = json.loads(result.content)
    assert data["total_num"] >= 1


@pytest.mark.asyncio
async def test_dojo_sdk_stock_ystock_info_symbols_filter():
    """Live: explicit symbols must filter results (not return full US market).

    Reproduces dashboard run run-7ee0f436 where total_num was 13166.

    Run manually:
      DOJO_ONLINE=1 DOJO_API_KEY=... uv run --extra dev python -m pytest \\
        tests/test_dojo_sdk_tool.py::test_dojo_sdk_stock_ystock_info_symbols_filter -v -s
    """
    if os.environ.get("DOJO_ONLINE", "0").lower() not in ("1", "true", "yes", "on"):
        pytest.skip("Set DOJO_ONLINE=1 to hit the live API (offline HF path uses separate auth/cache).")
    if not os.environ.get("DOJO_API_KEY"):
        pytest.skip("Set DOJO_API_KEY to run live ystock_info symbol-filter check.")

    registry = ToolRegistry()
    for spec in get_dojo_sdk_specs():
        registry.register(spec)

    executor = ToolExecutor(registry, SandboxPolicy())
    result = await executor.execute_one(
        ToolCall(
            id="tc-stock-ystock-info-live",
            name="dojo.sdk.stock.ystock_info",
            arguments=dict(YSTOCK_INFO_REPRO_ARGS),
        )
    )

    assert result.ok, result.error
    data = json.loads(result.content)
    rows = data.get("data") or []
    total = data.get("total_num", len(rows))
    tickers = {row.get("ticker") or row.get("symbol") for row in rows if row.get("ticker") or row.get("symbol")}

    print(f"ystock_info repro: total_num={total}, row_count={len(rows)}, " f"tickers={sorted(tickers)[:20]}{'...' if len(tickers) > 20 else ''}")

    assert total <= len(YSTOCK_INFO_REPRO_SYMBOLS), f"symbols filter failed: total_num={total} for {YSTOCK_INFO_REPRO_ARGS!r}; " f"sample tickers={sorted(tickers)[:10]}"
    assert tickers <= YSTOCK_INFO_REPRO_SYMBOLS, f"unexpected tickers outside request: {sorted(tickers - YSTOCK_INFO_REPRO_SYMBOLS)[:10]}"


@pytest.mark.asyncio
async def test_dojo_sdk_stock_news_tool():
    registry = ToolRegistry()
    for spec in get_dojo_sdk_specs():
        registry.register(spec)

    executor = ToolExecutor(registry, SandboxPolicy())
    mock_response = StockNewsResponse(symbol="TSLA", news=[{"title": "Tesla Announces Q2 Earnings"}])
    mock_get_news = AsyncMock(return_value=mock_response)

    with patch("dojoagents.tools.dojo_sdk_tool.AsyncDojo") as mock_async_dojo:
        instance = mock_async_dojo.return_value
        instance.stocks.get_news = mock_get_news

        result = await executor.execute_one(
            ToolCall(
                id="tc-stock-news",
                name="dojo.sdk.stock.news",
                arguments={"symbol": "TSLA", "page": 1, "page_size": 10},
            )
        )

        assert result.ok
        data = json.loads(result.content)
        assert data["symbol"] == "TSLA"
        assert len(data["news"]) == 1
        mock_get_news.assert_called_once_with(symbol="TSLA", page=1, page_size=10)


def test_dojo_sdk_config_injection():
    config = DojoSDKConfig(
        api_key="test-api-key",
        base_url="https://test.dojo.api",
        timeout=30.0,
        max_retries=3,
    )

    with patch("dojoagents.tools.dojo_sdk_tool.AsyncDojo") as mock_async_dojo:
        manager = DojoSDKToolManager(config)
        _ = manager.client

        mock_async_dojo.assert_called_once_with(
            api_key="test-api-key",
            base_url="https://test.dojo.api",
            timeout=30.0,
            max_retries=3,
        )


@pytest.mark.asyncio
async def test_dojo_sdk_precomputed_alpha_factors_tools():
    registry = ToolRegistry()
    for spec in get_dojo_sdk_specs():
        registry.register(spec)

    executor = ToolExecutor(registry, SandboxPolicy())

    mock_sector_factors = AsyncMock(return_value={"total_num": 1, "data": [{"sector": "tech", "alpha": 1.25}]})
    mock_ticker_factors = AsyncMock(return_value={"total_num": 1, "data": [{"symbol": "AAPL", "alpha": 0.85}]})

    with patch("dojoagents.tools.dojo_sdk_tool.AsyncDojo") as mock_async_dojo:
        instance = mock_async_dojo.return_value
        instance.sectors.get_precomputed_sector_alpha_factors_daily = mock_sector_factors
        instance.sectors.get_precomputed_ticker_alpha_factors_daily = mock_ticker_factors

        res_sector = await executor.execute_one(
            ToolCall(
                id="tc-sector-alpha",
                name="dojo.sdk.sector.precomputed_sector_alpha_factors_daily",
                arguments={"trade_date": "2026-05-28"},
            )
        )
        assert res_sector.ok
        data_sector = json.loads(res_sector.content)
        assert data_sector["data"][0]["sector"] == "tech"
        mock_sector_factors.assert_called_once_with(
            trade_date="2026-05-28",
            market=None,
            scope=None,
            level1_id=None,
            level2_id=None,
            level3_id=None,
            link_key=None,
            theme_row_status=None,
            horizon_row_status=None,
            factor_rule=None,
        )

        res_ticker = await executor.execute_one(
            ToolCall(
                id="tc-ticker-alpha",
                name="dojo.sdk.sector.precomputed_ticker_alpha_factors_daily",
                arguments={"ticker": "AAPL"},
            )
        )
        assert res_ticker.ok
        data_ticker = json.loads(res_ticker.content)
        assert data_ticker["data"][0]["symbol"] == "AAPL"
        mock_ticker_factors.assert_called_once_with(
            trade_date=None,
            market=None,
            ticker="AAPL",
            level1_id=None,
            level2_id=None,
            level3_id=None,
            role=None,
            factor_rule=None,
            row_status=None,
        )
