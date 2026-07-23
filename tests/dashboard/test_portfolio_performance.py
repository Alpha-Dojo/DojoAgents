from __future__ import annotations


import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from dojoagents.harnesses.built_in.financial.services.portfolio_performance import (
    build_market_performance,
    compute_risk_stats,
)
from dojoagents.harnesses.built_in.financial.services.portfolio_service import PortfolioService
from dojoagents.harnesses.built_in.financial.services.portfolio_store import PortfolioStore
from dojoagents.harnesses.built_in.financial.contracts.stock import Stock, StockQuote
from dojoagents.harnesses.built_in.financial.contracts.stock_kline import StockKlineBar, StockKlineResponse, ConstituentKlineBatchResponse
from dojoagents.harnesses.built_in.financial.surfaces import (
    dashboard_dependencies as deps,
)
from dojoagents.harnesses.built_in.financial.surfaces.dashboard_routers.dojo_folio import router as folio_router
from dojoagents.harnesses.built_in.financial.contracts.portfolio import PortfolioDetail


def test_risk_stats_are_deterministic_for_rebased_nav() -> None:
    stats = compute_risk_stats(
        {
            "2026-01-01": 100.0,
            "2026-01-02": 110.0,
            "2026-01-03": 99.0,
        },
        trading_days=["2026-01-01", "2026-01-02", "2026-01-03"],
    )

    assert stats.trading_days == 3
    assert stats.cumulative_return_pct == pytest.approx(-1.0)
    assert stats.max_drawdown_pct == pytest.approx(-10.0)
    assert stats.volatility_pct is not None and stats.volatility_pct > 0
    assert stats.sharpe_ratio is not None
    assert stats.calmar_ratio is not None


def test_risk_stats_forward_fill_invalid_nav_on_trading_day() -> None:
    stats = compute_risk_stats(
        {
            "2026-01-01": 100.0,
            "2026-01-02": 0.0,
            "2026-01-03": 105.0,
        },
        trading_days=["2026-01-01", "2026-01-02", "2026-01-03"],
    )

    assert stats.cumulative_return_pct == pytest.approx(5.0)
    assert stats.trading_days == 3
    assert stats.volatility_pct is not None and stats.volatility_pct > 0


def test_risk_stats_forward_fill_missing_trading_day() -> None:
    stats = compute_risk_stats(
        {"2026-01-01": 100.0, "2026-01-03": 105.0},
        trading_days=["2026-01-01", "2026-01-02", "2026-01-03"],
    )

    assert stats.cumulative_return_pct == pytest.approx(5.0)
    assert stats.trading_days == 3
    assert stats.volatility_pct is not None and stats.volatility_pct > 0


def test_risk_stats_forward_fill_preserves_drawdown_through_invalid_nav() -> None:
    stats = compute_risk_stats(
        {
            "2026-01-01": 100.0,
            "2026-01-02": 0.0,
            "2026-01-03": 80.0,
        },
        trading_days=["2026-01-01", "2026-01-02", "2026-01-03"],
    )

    assert stats.cumulative_return_pct == pytest.approx(-20.0)
    assert stats.max_drawdown_pct == pytest.approx(-20.0)


def test_risk_stats_use_market_trading_calendar_for_sparse_nav() -> None:
    from dojoagents.harnesses.built_in.financial.services.market_trading_calendar import trading_days_for_market

    trading_days = trading_days_for_market("us", "2026-01-02", "2026-01-06")
    stats = compute_risk_stats(
        {
            "2026-01-02": 100.0,
            "2026-01-06": 102.0,
        },
        trading_days=trading_days,
    )

    assert stats.cumulative_return_pct == pytest.approx(2.0)
    assert stats.trading_days == len(trading_days)
    assert stats.volatility_pct is not None and stats.volatility_pct > 0


def test_market_nav_is_flat_before_first_order() -> None:
    result = build_market_performance(
        market="us",
        orders=[],
        initial_capital=1_000_000,
        start_date="2026-01-01",
        ticker_closes={},
        benchmark_symbol="^SPX",
        benchmark_closes={
            "2026-01-02": 100,
            "2026-01-05": 101,
            "2026-01-06": 102,
        },
    )

    assert result.dates == ["2026-01-02", "2026-01-05", "2026-01-06"]
    assert result.portfolio == pytest.approx([100, 100, 100])
    assert result.benchmark == pytest.approx([100, 101, 102])
    assert result.stats.trading_days >= 3


def test_market_nav_includes_cash_balance_and_positions() -> None:
    result = build_market_performance(
        market="us",
        orders=[
            {
                "ticker": "MU",
                "market": "us",
                "order_side": "buy",
                "order_status": "filled",
                "qty": 100,
                "price": 393.6,
                "fill_price": 393.6,
                "fill_time": "2026-03-02T00:00:00+00:00",
                "created_at": "2026-03-02T00:00:00+00:00",
            }
        ],
        initial_capital=1_000_000,
        start_date="2026-01-01",
        ticker_closes={
            "MU": {
                "2026-01-02": 300,
                "2026-03-02": 400,
                "2026-03-03": 440,
            }
        },
        benchmark_symbol="^SPX",
        benchmark_closes={
            "2026-01-02": 100,
            "2026-03-02": 110,
            "2026-03-03": 112,
        },
    )

    assert result.dates == ["2026-01-02", "2026-03-02", "2026-03-03"]
    assert result.portfolio[0] == pytest.approx(100)
    # 2026-03-01: cash 960640 + 100 * 400 = 1_000_640
    assert result.portfolio[1] == pytest.approx(100.064)
    # 2026-03-02: cash 960640 + 100 * 440 = 1_004_640
    assert result.portfolio[2] == pytest.approx(100.464)


def test_market_nav_extends_cash_only_market_to_unified_calendar() -> None:
    result = build_market_performance(
        market="sh",
        orders=[],
        initial_capital=1_000_000,
        start_date="2026-01-01",
        ticker_closes={},
        benchmark_symbol="000001.SS",
        benchmark_closes={
            "2026-01-01": 100,
            "2026-06-23": 110,
        },
        calendar_dates=["2026-01-01", "2026-06-23", "2026-06-29"],
    )

    assert result.dates == ["2026-06-23", "2026-06-29"]
    assert result.portfolio == pytest.approx([100, 100])


@pytest.mark.asyncio
async def test_lightweight_portfolio_detail_does_not_fetch_performance(tmp_path) -> None:
    store = PortfolioStore(tmp_path)
    portfolio = store.create("Primary")

    class NoFetchKline:
        async def get_or_fetch_kline(self, *_args, **_kwargs):
            raise AssertionError("lightweight detail must not fetch kline")

        async def get_klines(self, *_args, **_kwargs):
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
async def test_build_performance_batches_order_klines(tmp_path) -> None:
    store = PortfolioStore(tmp_path)
    portfolio = store.create("Batch")
    for ticker, market in (("AAPL", "us"), ("MSFT", "us"), ("0700", "hk")):
        store.add_order(
            portfolio["id"],
            order={
                "id": f"order-{ticker}",
                "ticker": ticker,
                "market": market,
                "order_side": "buy",
                "order_status": "filled",
                "price": 100.0,
                "qty": 10.0,
                "fill_price": 100.0,
                "fill_time": "2026-01-02T00:00:00+00:00",
                "created_at": "2026-01-02T00:00:00+00:00",
            },
        )

    calls: list[list[str]] = []

    class BatchKlines:
        async def get_klines(self, symbols, limit=None):
            del limit
            calls.append(list(symbols))
            items = {
                symbol: StockKlineResponse(
                    symbol=symbol,
                    bars=[
                        StockKlineBar(
                            symbol=symbol,
                            bar_time="2026-01-02",
                            open=100,
                            high=100,
                            low=100,
                            close=100,
                        ),
                        StockKlineBar(
                            symbol=symbol,
                            bar_time="2026-01-05",
                            open=110,
                            high=110,
                            low=110,
                            close=110,
                        ),
                    ],
                )
                for symbol in symbols
            }
            return ConstituentKlineBatchResponse(items=items)

        async def get_or_fetch_kline(self, *_args, **_kwargs):
            raise AssertionError("order performance must use get_klines batch")

    class Stocks:
        def get(self, *_args):
            return None

        def find_market(self, _ticker):
            return "us"

    class Sectors:
        def get(self, *_args):
            return None

    class Benchmarks:
        async def get_kline(self, symbol, limit=252):
            del symbol, limit
            return StockKlineResponse(
                symbol="^SPX",
                bars=[
                    StockKlineBar(
                        symbol="^SPX",
                        bar_time="2026-01-02",
                        open=100,
                        high=100,
                        low=100,
                        close=100,
                    ),
                    StockKlineBar(
                        symbol="^SPX",
                        bar_time="2026-01-05",
                        open=101,
                        high=101,
                        low=101,
                        close=101,
                    ),
                ],
            )

    service = PortfolioService(
        store,
        Stocks(),
        Sectors(),
        BatchKlines(),
        benchmark_store=Benchmarks(),
    )

    detail = await service.get_detail(portfolio["id"], include_performance=True)

    assert len(calls) == 1
    assert ["0700", "AAPL", "MSFT"] in calls
    assert detail.performance is not None
    assert "us" in detail.performance.series_by_market


@pytest.mark.asyncio
async def test_build_performance_backfills_missing_order_klines_and_uses_deep_benchmark(tmp_path) -> None:
    store = PortfolioStore(tmp_path)
    portfolio = store.create("Live")
    store.add_order(
        portfolio["id"],
        order={
            "id": "order-nvda",
            "ticker": "NVDA",
            "market": "us",
            "order_side": "buy",
            "order_status": "filled",
            "price": 172.18,
            "qty": 100.0,
            "fill_price": 172.18,
            "fill_time": "2026-04-02T00:00:00+00:00",
            "created_at": "2026-04-02T00:00:00+00:00",
        },
    )
    for ticker in ("MU", "QCOM", "GOOG"):
        store.add_candidate(portfolio["id"], ticker=ticker, market="us")

    class BatchKlines:
        async def get_klines(self, symbols, limit=None):
            del limit
            # Simulate large candidate batch omitting filled order tickers.
            items = {
                symbol: StockKlineResponse(
                    symbol=symbol,
                    bars=[
                        StockKlineBar(
                            symbol=symbol,
                            bar_time="2026-07-09",
                            open=100,
                            high=100,
                            low=100,
                            close=100,
                        )
                    ],
                )
                for symbol in symbols
                if symbol != "NVDA"
            }
            return ConstituentKlineBatchResponse(items=items)

        async def get_or_fetch_kline(self, symbol, limit=None):
            del limit
            assert symbol == "NVDA"
            return StockKlineResponse(
                symbol=symbol,
                bars=[
                    StockKlineBar(
                        symbol=symbol,
                        bar_time=day,
                        open=price,
                        high=price,
                        low=price,
                        close=price,
                    )
                    for day, price in (
                        ("2026-04-02", 172.18),
                        ("2026-07-09", 202.78),
                    )
                ],
            )

    class Stocks:
        def get(self, *_args):
            return None

        def find_market(self, _ticker):
            return "us"

    class Sectors:
        def get(self, *_args):
            return None

    benchmark_limits: list[int] = []

    class Benchmarks:
        async def get_kline(self, symbol, limit=252):
            del symbol
            benchmark_limits.append(int(limit))
            return StockKlineResponse(
                symbol="^SPX",
                bars=[
                    StockKlineBar(
                        symbol="^SPX",
                        bar_time=day,
                        open=100,
                        high=100,
                        low=100,
                        close=100 + index,
                    )
                    for index, day in enumerate(
                        ["2026-01-02", "2026-04-02", "2026-07-09"],
                    )
                ],
            )

    service = PortfolioService(
        store,
        Stocks(),
        Sectors(),
        BatchKlines(),
        benchmark_store=Benchmarks(),
    )

    detail = await service.get_detail(portfolio["id"], include_performance=True)

    assert benchmark_limits
    assert max(benchmark_limits) >= 500
    assert detail.performance is not None
    us_series = detail.performance.series_by_market["us"]
    assert us_series.dates[-1] == "2026-07-09"
    assert us_series.portfolio[-1] != pytest.approx(100.0)


@pytest.mark.asyncio
async def test_service_builds_independent_market_series_with_default_benchmarks(tmp_path) -> None:
    store = PortfolioStore(tmp_path)
    portfolio = store.create("Global")
    holdings = (("AAPL", "us", 10), ("600000", "sh", 20), ("0700.HK", "hk", 30))

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
                dividend_yield=0,
            ),
        )

    stocks = {
        ("us", "AAPL"): stock("AAPL", "us", 100),
        ("sh", "600000"): stock("600000", "sh", 10),
        ("hk", "0700.HK"): stock("0700.HK", "hk", 300),
    }

    for ticker, market, shares in holdings:
        store.add_candidate(portfolio["id"], ticker=ticker, market=market)
        store.add_order(
            portfolio["id"],
            order={
                "id": f"order-{ticker}",
                "ticker": ticker,
                "market": market,
                "order_side": "buy",
                "order_status": "filled",
                "price": float(stocks[(market, ticker)].stock_quote.last_price),
                "qty": float(shares),
                "fill_price": float(stocks[(market, ticker)].stock_quote.last_price),
                "fill_time": "2026-06-16T00:00:00+00:00",
                "created_at": "2026-06-16T00:00:00+00:00",
            },
        )

    class Stocks:
        def get(self, market, ticker):
            return stocks.get((market, ticker))

        def find_market(self, ticker):
            return next((market for market, symbol in stocks if symbol == ticker), None)

    class Sectors:
        def get(self, *_args):
            return None

    market_dates = {
        "us": ["2026-06-15", "2026-06-16", "2026-06-17", "2026-06-18", "2026-06-19"],
        "sh": ["2026-06-15", "2026-06-16", "2026-06-17", "2026-06-19"],
        "hk": ["2026-06-15", "2026-06-16", "2026-06-18"],
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

        async def get_klines(self, symbols, limit=None):
            del limit
            items = {}
            for symbol in symbols:
                market = next(m for (m, s) in stocks if s == symbol)
                items[symbol] = await self.get_or_fetch_kline(symbol, market=market)
            return ConstituentKlineBatchResponse(items=items)

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
    us_series = detail.performance.series_by_market["us"]
    assert us_series.portfolio[0] == pytest.approx(100)
    assert us_series.portfolio[1] == pytest.approx(100.01)
    assert us_series.portfolio[-1] > us_series.portfolio[1]
    assert detail.net_value_by_market["us"] == pytest.approx(1_000_000)
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


@pytest.mark.asyncio
async def test_portfolio_holdings_use_bilingual_stock_names(tmp_path) -> None:
    store = PortfolioStore(tmp_path)
    portfolio = store.create("Primary")
    store.add_holding(portfolio["id"], ticker="NVDA", market="us", shares=10)

    stock = Stock(
        ticker="NVDA",
        market="us",
        short_name="NVIDIA Corp",
        long_name="NVIDIA Corporation",
        stock_quote=StockQuote(
            ticker="NVDA",
            name="英伟达",
            last_price=194.97,
            pre_close=192.0,
            open=193.0,
            high=195.0,
            low=192.5,
            change=2.97,
            change_percent=1.27,
            volume=1,
            amount=194.97,
            avg_price=194.97,
            market_cap=2_000_000_000,
            turn_rate=1,
            pe=20,
            pb=2,
            dividend_yield=0,
        ),
    )

    class Stocks:
        def get(self, market, ticker):
            if market == "us" and ticker == "NVDA":
                return stock
            return None

        def find_market(self, _ticker):
            return "us"

    class Sectors:
        def get(self, *_args):
            return None

    class Klines:
        async def get_or_fetch_kline(self, *_args, **_kwargs):
            return StockKlineResponse(symbol="NVDA", bars=[])

        async def get_klines(self, symbols, limit=None):
            del limit
            return ConstituentKlineBatchResponse(items={})

        def load_all(self, _ticker):
            return []

    service = PortfolioService(store, Stocks(), Sectors(), Klines())
    detail = await service.get_detail(portfolio["id"], include_performance=False)

    assert detail is not None
    assert len(detail.candidates) == 1
    candidate = detail.candidates[0]
    assert candidate.name_zh == "英伟达"
    assert candidate.name_en == "NVIDIA Corp"
