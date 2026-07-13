from __future__ import annotations

import pytest

from dojoagents.dashboard.schemas.stock import Stock, StockQuote
from dojoagents.dashboard.services.portfolio_service import PortfolioService
from dojoagents.dashboard.services.portfolio_store import PortfolioStore


def _quote(ticker: str, *, last_price: float) -> StockQuote:
    return StockQuote(
        ticker=ticker,
        name=ticker,
        last_price=last_price,
        pre_close=last_price,
        open=last_price,
        high=last_price,
        low=last_price,
        change=0.0,
        change_percent=0.0,
        volume=0,
        amount=0.0,
        avg_price=last_price,
        market_cap=0.0,
        turn_rate=0.0,
        pe=0.0,
        pb=0.0,
        dividend_yield=0.0,
    )


class _QuoteStockStore:
    def __init__(self, prices: dict[tuple[str, str], float]) -> None:
        self.prices = prices

    def get(self, market: str, ticker: str) -> Stock | None:
        price = self.prices.get((market, ticker))
        if price is None:
            return None
        return Stock(
            ticker=ticker,
            market=market,
            short_name=ticker,
            stock_quote=_quote(ticker, last_price=price),
        )

    def find_market(self, _ticker: str) -> str | None:
        return None


class _EmptySectorStore:
    def get(self, *_args, **_kwargs):
        return None


class _NoFetchKline:
    async def get_or_fetch_kline(self, *_args, **_kwargs):
        raise AssertionError("weight test must not fetch kline")


@pytest.mark.asyncio
async def test_holdings_weight_is_absolute_vs_total_portfolio_nav(tmp_path) -> None:
    store = PortfolioStore(tmp_path)
    portfolio = store.create("Weight Test")
    portfolio_id = portfolio["id"]

    store.add_order(
        portfolio_id,
        order={
            "id": "order-aapl",
            "ticker": "AAPL",
            "market": "us",
            "order_side": "buy",
            "order_status": "filled",
            "price": 100.0,
            "qty": 1000.0,
            "fill_price": 100.0,
            "fill_time": "2026-01-02T00:00:00+00:00",
            "created_at": "2026-01-02T00:00:00+00:00",
        },
    )
    store.add_order(
        portfolio_id,
        order={
            "id": "order-0700",
            "ticker": "0700",
            "market": "hk",
            "order_side": "buy",
            "order_status": "filled",
            "price": 200.0,
            "qty": 500.0,
            "fill_price": 200.0,
            "fill_time": "2026-01-02T00:00:00+00:00",
            "created_at": "2026-01-02T00:00:00+00:00",
        },
    )

    service = PortfolioService(
        store,
        _QuoteStockStore({("us", "AAPL"): 100.0, ("hk", "0700"): 200.0}),
        _EmptySectorStore(),
        _NoFetchKline(),
    )

    detail = await service.get_detail(portfolio_id, include_performance=False)
    assert detail is not None

    weights = {(row.market, row.ticker): row.weight for row in detail.positions}
    assert weights[("us", "AAPL")] == pytest.approx(100_000 / 3_000_000 * 100, rel=1e-3)
    assert weights[("hk", "0700")] == pytest.approx(100_000 / 3_000_000 * 100, rel=1e-3)
    assert sum(weights.values()) == pytest.approx(200_000 / 3_000_000 * 100, rel=1e-3)

    us_weights = [row.weight for row in detail.positions if row.market == "us"]
    assert sum(us_weights) < 100.0
