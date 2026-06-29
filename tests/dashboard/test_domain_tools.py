from __future__ import annotations

from types import SimpleNamespace

import pytest

from dojoagents.dashboard.tools import domain_tools
from dojoagents.tools.executor import ToolExecutor
from dojoagents.tools.registry import ToolRegistry
from dojoagents.tools.sandbox import SandboxPolicy


def _ready_registry() -> SimpleNamespace:
    return SimpleNamespace(
        sector_store=object(),
        stock_store=object(),
        benchmark_store=object(),
    )


def test_register_dashboard_domain_tools_adds_alpha_dashboard_tool_names() -> None:
    registry = ToolRegistry()

    domain_tools.register_dashboard_domain_tools(registry, _ready_registry())

    names = {spec.name for spec in registry.all()}
    assert {
        "search_company_ticker",
        "get_taxonomy_tree",
        "get_market_overview",
        "get_sector_movers",
        "screen_market_stocks",
        "get_sector_analysis",
        "filter_sector_constituents",
        "get_ticker_realtime_quote",
        "get_ticker_financials",
        "get_ticker_news_and_events",
        "get_ticker_price_trends",
    }.issubset(names)


def test_market_overview_tool_description_guides_cross_market_comparison() -> None:
    registry = ToolRegistry()

    domain_tools.register_dashboard_domain_tools(registry, _ready_registry())

    spec = registry.get("get_market_overview")
    assert spec is not None
    assert "Omit market" in spec.description
    assert "US, CN, and HK" in spec.description


def test_realtime_quote_tool_description_guides_batch_usage() -> None:
    registry = ToolRegistry()

    domain_tools.register_dashboard_domain_tools(registry, _ready_registry())

    spec = registry.get("get_ticker_realtime_quote")
    assert spec is not None
    assert "tickers" in spec.description
    assert "single call" in spec.description.lower()


@pytest.mark.asyncio
async def test_dashboard_domain_tool_returns_structured_data(monkeypatch) -> None:
    async def fake_market_overview(registry, *, days, market):
        return {
            "days": days,
            "markets": {
                market
                or "us": {
                    "market": market or "us",
                    "listed_count": 10,
                    "total_market_cap": 123.0,
                    "weighted_pe": 14.1,
                    "pe_sample_count": 10,
                }
            },
            "benchmarks": {},
        }

    monkeypatch.setattr(domain_tools, "build_market_overview", fake_market_overview)
    registry = ToolRegistry()
    domain_tools.register_dashboard_domain_tools(registry, _ready_registry())

    spec = registry.get("get_market_overview")
    assert spec is not None
    result = await spec.handler({"days": 3, "market": "hk"})

    assert result["metadata"] == {"ok": True}
    assert result["data"]["days"] == 3
    assert result["data"]["markets"]["hk"]["weighted_pe"] == 14.1
    assert '"weighted_pe": 14.1' in result["content"]


@pytest.mark.asyncio
async def test_realtime_quote_tool_returns_batch_payload(monkeypatch) -> None:
    async def fake_batch(registry, *, tickers, market):
        return {
            "market": market,
            "count": len(tickers),
            "not_found": [],
            "items": [{"ticker": ticker, "market": market or "us", "last_price": 1.0} for ticker in tickers],
        }

    monkeypatch.setattr(domain_tools, "build_tickers_quotes_v1", fake_batch)
    registry = ToolRegistry()
    domain_tools.register_dashboard_domain_tools(registry, _ready_registry())

    spec = registry.get("get_ticker_realtime_quote")
    assert spec is not None
    result = await spec.handler({"tickers": ["AAPL", "MSFT"], "market": "us"})

    assert result["data"]["count"] == 2
    assert [item["ticker"] for item in result["data"]["items"]] == ["AAPL", "MSFT"]


def test_create_app_registers_dashboard_domain_tools() -> None:
    from dojoagents.dashboard.server import create_app

    class FakeRuntime:
        def __init__(self) -> None:
            self.agent = SimpleNamespace(
                tool_executor=ToolExecutor(ToolRegistry(), SandboxPolicy()),
            )
            self.config_store = None
            self.extensions = SimpleNamespace(status=lambda: [])
            self.scheduler = SimpleNamespace(list_jobs=lambda: [])

    runtime = FakeRuntime()
    create_app(runtime, store_registry=_ready_registry())

    assert runtime.agent.tool_executor.registry.get("get_market_overview") is not None
    assert runtime.agent.tool_executor.registry.get("get_sector_movers") is not None
