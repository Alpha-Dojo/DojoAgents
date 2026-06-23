from __future__ import annotations


import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from dojoagents.dashboard.services.portfolio_performance import (
    build_market_performance,
    compute_risk_stats,
)
from dojoagents.dashboard.services.portfolio_service import PortfolioService
from dojoagents.dashboard.services.portfolio_store import PortfolioStore
from dojoagents.dashboard.schemas.stock import Stock, StockQuote
from dojoagents.dashboard.schemas.stock_kline import StockKlineBar, StockKlineResponse
from dojoagents.dashboard import deps
from dojoagents.dashboard.routers.dojo_folio import router as folio_router
from dojoagents.dashboard.schemas.portfolio import PortfolioDetail


def test_risk_stats_are_deterministic_for_rebased_nav() -> None:
    stats = compute_risk_stats([100.0, 110.0, 99.0])

    assert stats.trading_days == 3
    assert stats.cumulative_return_pct == pytest.approx(-1.0)
    assert stats.max_drawdown_pct == pytest.approx(-10.0)
    assert stats.volatility_pct is not None and stats.volatility_pct > 0
    assert stats.sharpe_ratio is not None
    assert stats.calmar_ratio is not None


def test_market_performance_aligns_dates_and_rebases_portfolio_and_benchmark() -> None:
    result = build_market_performance(
        market="us",
        holdings=[
            {
                "shares": 1,
                "closes": {
                    "2026-06-18": 100,
                    "2026-06-19": 110,
                    "2026-06-20": 121,
                },
            },
            {
                "shares": 2,
                "closes": {
                    "2026-06-18": 50,
                    "2026-06-19": 55,
                    "2026-06-20": 60.5,
                },
            },
        ],
        benchmark_symbol="^SPX",
        benchmark_closes={
            "2026-06-17": 90,
            "2026-06-18": 100,
            "2026-06-19": 105,
            "2026-06-20": 110,
        },
    )

    assert result.dates == ["2026-06-18", "2026-06-19", "2026-06-20"]
    assert result.portfolio == pytest.approx([100, 110, 121])
    assert result.benchmark == pytest.approx([100, 105, 110])
    assert result.benchmark_symbol == "^SPX"
    assert result.stats.cumulative_return_pct == pytest.approx(21)


@pytest.mark.asyncio
async def test_lightweight_portfolio_detail_does_not_fetch_performance(tmp_path) -> None:
    store = PortfolioStore(tmp_path)
    portfolio = store.create("Primary")

    class NoFetchKline:
        async def get_or_fetch_kline(self, *_args, **_kwargs):
            raise AssertionError("lightweight detail must not fetch kline")

        def load_all(self, _ticker):
            return []

    class EmptyStockStore:
        def get(self, *_args):
            return None

        def find_market(self, _ticker):
            return None

    class EmptySectorStore:
        def get(self, *_args):
            return None

    service = PortfolioService(
        store,
        EmptyStockStore(),
        EmptySectorStore(),
        NoFetchKline(),
    )

    detail = await service.get_detail(portfolio["id"], include_performance=False)

    assert detail is not None
    assert detail.performance is None


@pytest.mark.asyncio
async def test_service_builds_independent_market_series_with_default_benchmarks(tmp_path) -> None:
    store = PortfolioStore(tmp_path)
    portfolio = store.create("Global")
    holdings = (("AAPL", "us", 10), ("600000", "sh", 20), ("0700.HK", "hk", 30))
    for ticker, market, shares in holdings:
        store.add_holding(portfolio["id"], ticker=ticker, market=market, shares=shares)

    def stock(ticker, market, price):
        return Stock(
            ticker=ticker,
            market=market,
            short_name=ticker,
            stock_quote=StockQuote(
                ticker=ticker,
                name=ticker,
                last_price=price,
                pre_close=price,
                open=price,
                high=price,
                low=price,
                change=0,
                change_percent=0,
                volume=1,
                amount=price,
                avg_price=price,
                market_cap=2_000_000_000,
                turn_rate=1,
                pe=20,
                pb=2,
            ),
        )

    stocks = {
        ("us", "AAPL"): stock("AAPL", "us", 100),
        ("sh", "600000"): stock("600000", "sh", 10),
        ("hk", "0700.HK"): stock("0700.HK", "hk", 300),
    }

    class Stocks:
        def get(self, market, ticker):
            return stocks.get((market, ticker))

        def find_market(self, ticker):
            return next((market for market, symbol in stocks if symbol == ticker), None)

    class Sectors:
        def get(self, *_args):
            return None

    market_dates = {
        "us": ["2026-06-18", "2026-06-19"],
        "sh": ["2026-06-17", "2026-06-19"],
        "hk": ["2026-06-16", "2026-06-18"],
    }

    class Klines:
        async def get_or_fetch_kline(self, symbol, *, market=None, **_kwargs):
            base = float(stocks[(market, symbol)].stock_quote.last_price)
            return StockKlineResponse(
                symbol=symbol,
                bars=[
                    StockKlineBar(
                        symbol=symbol,
                        bar_time=day,
                        open=base * (1 + index * 0.1),
                        high=base * (1 + index * 0.1),
                        low=base * (1 + index * 0.1),
                        close=base * (1 + index * 0.1),
                    )
                    for index, day in enumerate(market_dates[market])
                ],
            )

        def load_all(self, _ticker):
            return []

    class Benchmarks:
        async def get_kline(self, symbol, limit=252):
            del limit
            market = {"^SPX": "us", "000001.SS": "sh", "^HSI": "hk"}[symbol]
            return StockKlineResponse(
                symbol=symbol,
                bars=[
                    StockKlineBar(
                        symbol=symbol,
                        bar_time=day,
                        open=100 + index * 5,
                        high=100 + index * 5,
                        low=100 + index * 5,
                        close=100 + index * 5,
                    )
                    for index, day in enumerate(market_dates[market])
                ],
            )

    service = PortfolioService(
        store,
        Stocks(),
        Sectors(),
        Klines(),
        benchmark_store=Benchmarks(),
    )

    detail = await service.get_detail(portfolio["id"], include_performance=True)

    assert set(detail.performance.series_by_market) == {"us", "sh", "hk"}
    assert detail.performance.benchmark_symbol_by_market == {
        "us": "^SPX",
        "sh": "000001.SS",
        "hk": "^HSI",
    }
    assert detail.performance.series_by_market["us"].portfolio == pytest.approx([100, 110])
    assert detail.performance.series_by_market["sh"].dates == market_dates["sh"]
    assert detail.cost_basis_by_market == {"us": 1_000, "sh": 200, "hk": 9_000}


def test_detail_route_passes_benchmark_overrides_to_service() -> None:
    calls = []

    class Service:
        async def get_detail(self, portfolio_id, **kwargs):
            calls.append((portfolio_id, kwargs))
            return PortfolioDetail(id=portfolio_id, name="Primary")

    app = FastAPI()
    app.include_router(folio_router, prefix="/api/v1")
    app.dependency_overrides[deps.get_portfolio_service] = lambda: Service()

    response = TestClient(app).get("/api/v1/dojo-folio/portfolios/p1" "?benchmark_us=QQQ&benchmark_sh=000300.SS&benchmark_hk=HSTECH")

    assert response.status_code == 200
    assert calls == [
        (
            "p1",
            {
                "include_performance": True,
                "benchmark_by_market": {
                    "us": "QQQ",
                    "sh": "000300.SS",
                    "hk": "HSTECH",
                },
            },
        )
    ]
