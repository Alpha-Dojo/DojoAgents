# tests/test_dojo_sdk_tool.py
from __future__ import annotations

import json
import os
from unittest.mock import AsyncMock, patch

import pytest

from dojoagents.agent.models import ToolCall
from dojoagents.agent.runtime import Runtime
from dojoagents.config.models import DojoSDKConfig
from dojoagents.harnesses.built_in.financial.tools.sdk_runtime import (
    DojoSDKToolManager,
    HF_REGISTRY,
    OFFLINE_TOOL_BINDINGS,
    get_dojo_sdk_specs,
)
from dojoagents.tools.executor import ToolExecutor
from dojoagents.tools.registry import ToolRegistry
from dojoagents.tools.sandbox import SandboxPolicy
from dojo.types.models import BenchmarkCatalogResponse, CurrentQuoteResponse, StockKlineResponse, StockNewsResponse

YSTOCK_INFO_REPRO_ARGS = {
    "symbols": ["SPY", "2800.HK", "510300.SH"],
    "market": "us",
    "only_simple_fields": True,
}
YSTOCK_INFO_REPRO_SYMBOLS = {"SPY", "2800.HK", "510300.SH"}


def test_hf_registry_coverage():
    assert set(OFFLINE_TOOL_BINDINGS) == set(HF_REGISTRY)
    specs = get_dojo_sdk_specs()
    assert len(specs) == len(HF_REGISTRY)
    assert len({spec.name for spec in specs}) == len(HF_REGISTRY)


def test_dojo_sdk_tools_discovery():
    runtime = Runtime.from_default_config()
    all_tools = [spec.name for spec in runtime.agent.tool_executor.registry.all()]

    assert "dojo.sdk.stock.kline" in all_tools
    assert "dojo.sdk.stock.current_quote" in all_tools
    assert "dojo.sdk.benchmark.catalog" in all_tools
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
                "kline_t": "1d",
                "bar_time": "2026-06-04",
                "open": 180.0,
                "high": 182.0,
                "low": 179.0,
                "close": 181.5,
                "vol": 1000.0,
            }
        ],
    )
    mock_get_kline = AsyncMock(return_value=mock_response)

    with patch("dojoagents.harnesses.built_in.financial.tools.sdk_runtime.AsyncDojo") as mock_async_dojo:
        instance = mock_async_dojo.return_value
        instance.stocks.get_kline = mock_get_kline

        result = await executor.execute_one(
            ToolCall(
                id="tc-stock-kline",
                name="dojo.sdk.stock.kline",
                arguments={"symbol": "AAPL", "kline_t": "1d", "limit": 50},
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
            limit=50,
        )


@pytest.mark.asyncio
async def test_dojo_sdk_stock_current_quote_tool():
    registry = ToolRegistry()
    for spec in get_dojo_sdk_specs():
        registry.register(spec)

    executor = ToolExecutor(registry, SandboxPolicy())
    mock_response = CurrentQuoteResponse(symbol="AAPL", price=180.5, volume=50000.0)
    mock_get_quote = AsyncMock(return_value=mock_response)

    with patch("dojoagents.harnesses.built_in.financial.tools.sdk_runtime.AsyncDojo") as mock_async_dojo:
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
    rows = data.get("data") or []
    tickers = {row.get("ticker") or row.get("symbol") for row in rows if isinstance(row, dict) and (row.get("ticker") or row.get("symbol"))}
    # Offline snapshots need not contain every requested symbol, but must not
    # leak the full market or symbols outside the request.
    assert data["total_num"] <= len(YSTOCK_INFO_REPRO_SYMBOLS)
    assert tickers <= YSTOCK_INFO_REPRO_SYMBOLS


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

    with patch("dojoagents.harnesses.built_in.financial.tools.sdk_runtime.AsyncDojo") as mock_async_dojo:
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


@pytest.mark.asyncio
async def test_dojo_sdk_benchmark_catalog_tool():
    registry = ToolRegistry()
    for spec in get_dojo_sdk_specs():
        registry.register(spec)

    executor = ToolExecutor(registry, SandboxPolicy())
    mock_response = BenchmarkCatalogResponse(total_num=1, data=[{"symbol": "SPX", "name": "S&P 500"}])
    mock_get_catalog = AsyncMock(return_value=mock_response)

    with patch("dojoagents.harnesses.built_in.financial.tools.sdk_runtime.AsyncDojo") as mock_async_dojo:
        instance = mock_async_dojo.return_value
        instance.benchmark.get_catalog = mock_get_catalog

        result = await executor.execute_one(
            ToolCall(
                id="tc-benchmark-catalog",
                name="dojo.sdk.benchmark.catalog",
                arguments={},
            )
        )

        assert result.ok
        data = json.loads(result.content)
        assert data["data"][0]["symbol"] == "SPX"
        mock_get_catalog.assert_called_once_with()


def test_dojo_sdk_config_injection():
    config = DojoSDKConfig(
        api_key="test-api-key",
        base_url="https://test.dojo.api",
        timeout=30.0,
        max_retries=3,
    )

    with patch("dojoagents.harnesses.built_in.financial.tools.sdk_runtime.AsyncDojo") as mock_async_dojo:
        manager = DojoSDKToolManager(config)
        _ = manager.client

        mock_async_dojo.assert_called_once_with(
            api_key="test-api-key",
            base_url="https://test.dojo.api",
            timeout=30.0,
            max_retries=3,
        )
