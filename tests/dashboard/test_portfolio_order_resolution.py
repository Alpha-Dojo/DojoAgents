from __future__ import annotations

from types import SimpleNamespace

import pytest

from dojoagents.agent.escalation import AgentEscalationError
from dojoagents.dashboard.services.portfolio_allocation import normalize_shares
from dojoagents.dashboard.schemas.portfolio import PortfolioCapitalConfig, PortfolioDetail
from dojoagents.dashboard.services.portfolio_order_resolution import (
    validate_share_quantity,
    resolve_portfolio_order_request,
)


class Bar:
    def __init__(self, bar_time: str, open: float, high: float, low: float, close: float | None = None):
        self.bar_time = bar_time
        self.open = open
        self.high = high
        self.low = low
        self.close = close if close is not None else open


class FakeKlineStore:
    def __init__(self, bars: list[Bar]) -> None:
        self.bars = bars
        self.calls: list[dict[str, object]] = []

    async def get_or_fetch_kline(self, symbol, **kwargs):
        self.calls.append({"symbol": symbol, **kwargs})
        from dojoagents.dashboard.schemas.stock_kline import StockKlineBar, StockKlineResponse

        selected = self.bars
        start = str(kwargs.get("start_time") or "")[:10]
        end = str(kwargs.get("end_time") or "")[:10]
        if start and end:
            selected = [bar for bar in self.bars if start <= bar.bar_time[:10] <= end]
        return StockKlineResponse(
            symbol=symbol,
            bars=[
                StockKlineBar(
                    symbol=symbol,
                    bar_time=bar.bar_time,
                    open=bar.open,
                    high=bar.high,
                    low=bar.low,
                    close=bar.close,
                )
                for bar in selected
            ],
        )


class FakeStockStore:
    def resolve(self, ticker, market=None):
        if ticker.upper() in {"GOOG", "AAPL"}:
            return SimpleNamespace(ticker=ticker.upper(), market=market or "us")
        return None

    def find_market(self, ticker):
        if ticker.upper() in {"GOOG", "AAPL"}:
            return "us"
        if ticker.endswith(".SS"):
            return "sh"
        return None

    def get(self, market, ticker):
        return self.resolve(ticker, market=market)


class FakePortfolioService:
    def __init__(self) -> None:
        self.detail = PortfolioDetail(
            id="p1",
            name="Test",
            config=PortfolioCapitalConfig(
                start_date="2025-01-01",
                capital_by_market={"us": 1_000_000.0, "sh": 1_000_000.0, "hk": 1_000_000.0},
            ),
            orders=[],
        )

    async def get_detail(self, portfolio_id: str, *, include_performance: bool = True):
        return self.detail


def _registry(kline_store: FakeKlineStore):
    return SimpleNamespace(
        stock_store=FakeStockStore(),
        kline_store=kline_store,
    )


@pytest.mark.parametrize(
    ("market", "qty", "error"),
    [
        ("us", 2000, None),
        ("us", 2000.5, "whole number"),
        ("sh", 100, None),
        ("sh", 150, "multiple of 100"),
        ("hk", 200, None),
    ],
)
def test_validate_share_quantity(market: str, qty: float, error: str | None) -> None:
    message = validate_share_quantity(market, qty)
    if error is None:
        assert message is None
    else:
        assert message is not None
        assert error in message


@pytest.mark.asyncio
async def test_resolve_uses_latest_close_when_only_ticker_provided() -> None:
    store = FakeKlineStore(
        [
            Bar("2026-06-17", 350.0, 355.0, 348.0, 352.0),
            Bar("2026-06-18", 357.89, 369.0, 356.61, 367.46),
        ]
    )
    body, meta = await resolve_portfolio_order_request(
        _registry(store),
        FakePortfolioService(),
        "p1",
        {"ticker": "GOOG", "market": "us", "order_side": "buy"},
    )

    assert body.price == pytest.approx(367.46)
    assert body.order_time == "2026-06-18"
    assert body.qty == float(normalize_shares("us", 100_000 / body.price))
    assert meta.price_source == "close"
    assert meta.qty_source == "default_10pct"


@pytest.mark.asyncio
async def test_resolve_uses_open_on_specified_trade_date() -> None:
    store = FakeKlineStore([Bar("2026-06-18", 363.89, 369.0, 356.61, 367.46)])
    body, meta = await resolve_portfolio_order_request(
        _registry(store),
        FakePortfolioService(),
        "p1",
        {
            "ticker": "GOOG",
            "market": "us",
            "order_side": "buy",
            "order_time": "2026-06-18",
            "qty": 2000,
        },
    )

    assert body.price == pytest.approx(363.89)
    assert body.qty == 2000
    assert meta.price_source == "open"
    assert meta.time_source == "user"


@pytest.mark.asyncio
async def test_resolve_finds_trade_date_from_limit_price() -> None:
    store = FakeKlineStore(
        [
            Bar("2026-06-10", 300.0, 310.0, 295.0, 305.0),
            Bar("2026-06-18", 363.89, 369.0, 356.61, 367.46),
        ]
    )
    body, meta = await resolve_portfolio_order_request(
        _registry(store),
        FakePortfolioService(),
        "p1",
        {
            "ticker": "GOOG",
            "market": "us",
            "order_side": "buy",
            "price": 357.89,
            "qty": 100,
        },
    )

    assert body.order_time == "2026-06-18"
    assert body.price == pytest.approx(357.89)
    assert meta.time_source == "inferred_from_price"


@pytest.mark.asyncio
async def test_resolve_rejects_price_outside_daily_range() -> None:
    store = FakeKlineStore([Bar("2026-06-18", 363.89, 369.0, 356.61, 367.46)])
    with pytest.raises(AgentEscalationError) as exc_info:
        await resolve_portfolio_order_request(
            _registry(store),
            FakePortfolioService(),
            "p1",
            {
                "ticker": "GOOG",
                "market": "us",
                "order_side": "buy",
                "price": 400.0,
                "order_time": "2026-06-18",
                "qty": 100,
            },
        )
    assert exc_info.value.code == "price_not_fillable"


@pytest.mark.asyncio
async def test_resolve_rejects_invalid_a_share_lot() -> None:
    store = FakeKlineStore([Bar("2026-06-18", 100.0, 110.0, 95.0, 105.0)])
    with pytest.raises(AgentEscalationError) as exc_info:
        await resolve_portfolio_order_request(
            _registry(store),
            FakePortfolioService(),
            "p1",
            {
                "ticker": "688008.SS",
                "market": "cn",
                "order_side": "buy",
                "order_time": "2026-06-18",
                "qty": 150,
            },
        )
    assert exc_info.value.code == "invalid_order_quantity"
