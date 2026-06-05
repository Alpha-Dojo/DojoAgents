# tests/test_dojo_sdk_tool.py
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from dojoagents.agent.runtime import Runtime
from dojoagents.agent.models import ToolCall
from dojoagents.tools.registry import ToolRegistry
from dojoagents.tools.executor import ToolExecutor
from dojoagents.tools.sandbox import SandboxPolicy
from dojoagents.tools.dojo_sdk_tool import get_dojo_sdk_specs

# Import response models from dojo SDK to mock return values properly
from dojo.types.models import (
    KLineResponse,
    TickerResponse,
    NewsResponse,
    CurrentQuoteResponse,
    StockKlineResponse,
    FinancialsResponse,
    StockNewsResponse,
)


def test_dojo_sdk_tools_discovery():
    """Verify that DojoSDK tools are registered and discovered under default runtime bootstrapping."""
    runtime = Runtime.from_default_config()
    all_tools = [spec.name for spec in runtime.agent.tool_executor.registry.all()]
    
    assert "dojo.sdk.get_kline" in all_tools
    assert "dojo.sdk.get_ticker" in all_tools
    assert "dojo.sdk.get_news" in all_tools


@pytest.mark.asyncio
async def test_dojo_sdk_get_kline_tool():
    """Test get_kline tool handler and parameter passing."""
    registry = ToolRegistry()
    for spec in get_dojo_sdk_specs():
        registry.register(spec)

    executor = ToolExecutor(registry, SandboxPolicy())
    
    # Mock AsyncDojo client and get_kline response
    mock_response = KLineResponse(
        exchange="BINANCE",
        bz_type="SPOT",
        symbol="BTCUSDT",
        klines=[[1717462800000, 68000.0, 69000.0, 67500.0, 68500.0, 150.5]]
    )
    
    mock_get_kline = AsyncMock(return_value=mock_response)
    
    with patch("dojoagents.tools.dojo_sdk_tool.AsyncDojo") as mock_async_dojo:
        # Wire the mock to client properties
        instance = mock_async_dojo.return_value
        instance.market_data.get_kline = mock_get_kline
        
        tool_call = ToolCall(
            id="tc-kline",
            name="dojo.sdk.get_kline",
            arguments={
                "exchange": "BINANCE",
                "bz_type": "SPOT",
                "symbol": "BTCUSDT",
                "kline_t": "1h",
                "limit": 10
            }
        )
        
        result = await executor.execute_one(tool_call)
        
        assert result.ok
        assert "tc-kline" == result.call_id
        
        # Verify JSON content matches mock response
        data = json.loads(result.content)
        assert data["exchange"] == "BINANCE"
        assert data["bz_type"] == "SPOT"
        assert data["symbol"] == "BTCUSDT"
        assert len(data["klines"]) == 1
        assert data["klines"][0][1] == 68000.0
        
        # Verify mock was called with correct parameters
        mock_get_kline.assert_called_once_with(
            exchange="BINANCE",
            bz_type="SPOT",
            symbol="BTCUSDT",
            kline_t="1h",
            limit=10
        )


@pytest.mark.asyncio
async def test_dojo_sdk_get_ticker_tool():
    """Test get_ticker tool handler."""
    registry = ToolRegistry()
    for spec in get_dojo_sdk_specs():
        registry.register(spec)

    executor = ToolExecutor(registry, SandboxPolicy())
    
    mock_response = TickerResponse(
        exchange="BINANCE",
        bz_type="SPOT",
        symbol="ETHUSDT",
        price=3500.0,
        volume=12000.5
    )
    
    mock_get_ticker = AsyncMock(return_value=mock_response)
    
    with patch("dojoagents.tools.dojo_sdk_tool.AsyncDojo") as mock_async_dojo:
        instance = mock_async_dojo.return_value
        instance.market_data.get_ticker = mock_get_ticker
        
        tool_call = ToolCall(
            id="tc-ticker",
            name="dojo.sdk.get_ticker",
            arguments={
                "exchange": "BINANCE",
                "bz_type": "SPOT",
                "symbol": "ETHUSDT"
            }
        )
        
        result = await executor.execute_one(tool_call)
        
        assert result.ok
        data = json.loads(result.content)
        assert data["exchange"] == "BINANCE"
        assert data["symbol"] == "ETHUSDT"
        assert data["price"] == 3500.0
        
        mock_get_ticker.assert_called_once_with(
            exchange="BINANCE",
            bz_type="SPOT",
            symbol="ETHUSDT"
        )


@pytest.mark.asyncio
async def test_dojo_sdk_get_news_tool():
    """Test get_news tool handler."""
    registry = ToolRegistry()
    for spec in get_dojo_sdk_specs():
        registry.register(spec)

    executor = ToolExecutor(registry, SandboxPolicy())
    
    mock_response = NewsResponse(
        news=[
            {"title": "Bitcoin Surges Above 68k", "sentiment": "bullish"},
            {"title": "Fed Holds Rates Steady", "sentiment": "neutral"}
        ]
    )
    
    mock_get_news = AsyncMock(return_value=mock_response)
    
    with patch("dojoagents.tools.dojo_sdk_tool.AsyncDojo") as mock_async_dojo:
        instance = mock_async_dojo.return_value
        instance.news.get_news = mock_get_news
        
        tool_call = ToolCall(
            id="tc-news",
            name="dojo.sdk.get_news",
            arguments={"limit": 5}
        )
        
        result = await executor.execute_one(tool_call)
        
        assert result.ok
        data = json.loads(result.content)
        assert len(data["news"]) == 2
        assert data["news"][0]["title"] == "Bitcoin Surges Above 68k"
        
        mock_get_news.assert_called_once_with(limit=5)


def test_dojo_sdk_config_injection():
    """Verify that configuration settings are passed to AsyncDojo during tool spec generation."""
    from dojoagents.config.models import DojoSDKConfig
    
    config = DojoSDKConfig(
        api_key="test-api-key",
        base_url="https://test.dojo.api",
        timeout=30.0,
        max_retries=3
    )
    
    with patch("dojoagents.tools.dojo_sdk_tool.AsyncDojo") as mock_async_dojo:
        specs = get_dojo_sdk_specs(config)
        # Specs are returned successfully (3 generic + 4 stock tools)
        assert len(specs) == 7
        
        # Trigger client lazy initialization by accessing the client of the manager
        from dojoagents.tools.dojo_sdk_tool import DojoSDKToolManager
        manager = DojoSDKToolManager(config)
        client = manager.client
        
        # Verify AsyncDojo was instantiated with the correct kwargs
        mock_async_dojo.assert_called_once_with(
            api_key="test-api-key",
            base_url="https://test.dojo.api",
            timeout=30.0,
            max_retries=3
        )


@pytest.mark.asyncio
async def test_dojo_sdk_get_stock_quote_tool():
    """Test get_stock_quote tool handler."""
    registry = ToolRegistry()
    for spec in get_dojo_sdk_specs():
        registry.register(spec)

    executor = ToolExecutor(registry, SandboxPolicy())
    
    mock_response = CurrentQuoteResponse(
        symbol="AAPL",
        price=180.5,
        volume=50000.0
    )
    
    mock_get_quote = AsyncMock(return_value=mock_response)
    
    with patch("dojoagents.tools.dojo_sdk_tool.AsyncDojo") as mock_async_dojo:
        instance = mock_async_dojo.return_value
        instance.stocks.get_quote = mock_get_quote
        
        tool_call = ToolCall(
            id="tc-stock-quote",
            name="dojo.sdk.get_stock_quote",
            arguments={"symbols": ["AAPL"]}
        )
        
        result = await executor.execute_one(tool_call)
        
        assert result.ok
        data = json.loads(result.content)
        assert data["symbol"] == "AAPL"
        assert data["price"] == 180.5
        
        mock_get_quote.assert_called_once_with(symbols=["AAPL"])


@pytest.mark.asyncio
async def test_dojo_sdk_get_stock_kline_tool():
    """Test get_stock_kline tool handler."""
    registry = ToolRegistry()
    for spec in get_dojo_sdk_specs():
        registry.register(spec)

    executor = ToolExecutor(registry, SandboxPolicy())
    
    mock_response = StockKlineResponse(
        total_num=1,
        klines=[
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
        ]
    )
    
    mock_get_kline = AsyncMock(return_value=mock_response)
    
    with patch("dojoagents.tools.dojo_sdk_tool.AsyncDojo") as mock_async_dojo:
        instance = mock_async_dojo.return_value
        instance.stocks.get_kline = mock_get_kline
        
        tool_call = ToolCall(
            id="tc-stock-kline",
            name="dojo.sdk.get_stock_kline",
            arguments={
                "symbol": "AAPL",
                "kline_t": "1d",
                "limit": 50
            }
        )
        
        result = await executor.execute_one(tool_call)
        
        assert result.ok
        data = json.loads(result.content)
        assert data["total_num"] == 1
        assert len(data["klines"]) == 1
        assert data["klines"][0]["symbol"] == "AAPL"
        
        mock_get_kline.assert_called_once_with(
            symbol="AAPL",
            kline_t="1D",
            limit=50,
            start_time=None,
            end_time=None
        )


@pytest.mark.asyncio
async def test_dojo_sdk_get_stock_financials_tool():
    """Test get_stock_financials tool handler."""
    registry = ToolRegistry()
    for spec in get_dojo_sdk_specs():
        registry.register(spec)

    executor = ToolExecutor(registry, SandboxPolicy())
    
    mock_response = FinancialsResponse(
        symbol="MSFT",
        financials=[{"year": 2023, "revenue": 211000}]
    )
    
    mock_get_financials = AsyncMock(return_value=mock_response)
    
    with patch("dojoagents.tools.dojo_sdk_tool.AsyncDojo") as mock_async_dojo:
        instance = mock_async_dojo.return_value
        instance.stocks.get_financials = mock_get_financials
        
        tool_call = ToolCall(
            id="tc-stock-financials",
            name="dojo.sdk.get_stock_financials",
            arguments={"symbol": "MSFT", "lookback": 3}
        )
        
        result = await executor.execute_one(tool_call)
        
        assert result.ok
        data = json.loads(result.content)
        assert data["symbol"] == "MSFT"
        assert len(data["financials"]) == 1
        
        mock_get_financials.assert_called_once_with(symbol="MSFT", lookback=3)


@pytest.mark.asyncio
async def test_dojo_sdk_get_stock_news_tool():
    """Test get_stock_news tool handler."""
    registry = ToolRegistry()
    for spec in get_dojo_sdk_specs():
        registry.register(spec)

    executor = ToolExecutor(registry, SandboxPolicy())
    
    mock_response = StockNewsResponse(
        symbol="TSLA",
        news=[{"title": "Tesla Announces Q2 Earnings"}]
    )
    
    mock_get_news = AsyncMock(return_value=mock_response)
    
    with patch("dojoagents.tools.dojo_sdk_tool.AsyncDojo") as mock_async_dojo:
        instance = mock_async_dojo.return_value
        instance.stocks.get_news = mock_get_news
        
        tool_call = ToolCall(
            id="tc-stock-news",
            name="dojo.sdk.get_stock_news",
            arguments={"symbol": "TSLA", "limit": 10}
        )
        
        result = await executor.execute_one(tool_call)
        
        assert result.ok
        data = json.loads(result.content)
        assert data["symbol"] == "TSLA"
        assert len(data["news"]) == 1
        
        mock_get_news.assert_called_once_with(symbol="TSLA", limit=10)
