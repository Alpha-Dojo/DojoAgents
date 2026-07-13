from __future__ import annotations

from types import SimpleNamespace

import pytest

from dojoagents.agent.escalation import AgentEscalationError
from dojoagents.dashboard.services.portfolio_allocation import normalize_shares
from dojoagents.dashboard.schemas.portfolio import PortfolioCapitalConfig, PortfolioDetail, PortfolioPositionView
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
        upper = ticker.upper()
        if upper in {"GOOG", "GOOGL", "AAPL"}:
            return SimpleNamespace(ticker=upper, market=market or "us")
        return None

    def find_market(self, ticker):
        if ticker.upper() in {"GOOG", "GOOGL", "AAPL"}:
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
    assert meta.time_source == "inferred_from_latest_bar"


@pytest.mark.asyncio
async def test_resolve_current_price_uses_latest_trading_day() -> None:
    store = FakeKlineStore([Bar("2026-07-03", 355.0, 362.0, 354.0, 359.91)])
    body, meta = await resolve_portfolio_order_request(
        _registry(store),
        FakePortfolioService(),
        "p1",
        {
            "ticker": "GOOGL",
            "market": "us",
            "order_side": "buy",
            "price": 359.91,
            "qty": 100,
        },
    )

    assert body.order_time == "2026-07-03"
    assert body.price == pytest.approx(359.91)
    assert meta.time_source == "inferred_from_latest_bar"


@pytest.mark.asyncio
async def test_resolve_historical_price_falls_back_to_matching_bar() -> None:
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
            "price": 305.0,
            "qty": 100,
        },
    )

    assert body.order_time == "2026-06-10"
    assert meta.time_source == "inferred_from_price"


@pytest.mark.asyncio
async def test_resolve_accepts_price_at_daily_high_boundary() -> None:
    store = FakeKlineStore([Bar("2026-07-03", 350.0, 359.91, 348.0, 359.0)])
    body, meta = await resolve_portfolio_order_request(
        _registry(store),
        FakePortfolioService(),
        "p1",
        {
            "ticker": "GOOG",
            "market": "us",
            "order_side": "buy",
            "price": 359.91,
            "order_time": "2026-07-03",
            "qty": 10,
        },
    )

    assert body.price == pytest.approx(359.91)
    assert meta.bar_high == pytest.approx(359.91)
    assert body.resolved_bar is not None
    assert body.resolved_bar.date == "2026-07-03"
    assert body.resolved_bar.low == pytest.approx(348.0)
    assert body.resolved_bar.high == pytest.approx(359.91)


@pytest.mark.asyncio
async def test_fetch_resolution_uses_date_window_not_tail_limit() -> None:
    store = FakeKlineStore([Bar("2026-07-03", 350.0, 362.0, 348.0, 359.91)])
    await resolve_portfolio_order_request(
        _registry(store),
        FakePortfolioService(),
        "p1",
        {"ticker": "GOOG", "market": "us", "order_side": "buy", "price": 359.91},
    )

    assert store.calls
    assert "start_time" in store.calls[0]
    assert "end_time" in store.calls[0]
    assert "limit" not in store.calls[0] or store.calls[0].get("limit") is None


@pytest.mark.asyncio
async def test_resolve_gooql_falls_back_to_goog_kline_symbol() -> None:
    class SplitKlineStore(FakeKlineStore):
        async def get_or_fetch_kline(self, symbol, **kwargs):
            self.calls.append({"symbol": symbol, **kwargs})
            if symbol == "GOOGL":
                from dojoagents.dashboard.schemas.stock_kline import StockKlineResponse

                return StockKlineResponse(symbol=symbol, bars=[])
            return await super().get_or_fetch_kline(symbol, **kwargs)

    store = SplitKlineStore([Bar("2026-07-03", 355.0, 362.0, 354.0, 359.91)])
    body, meta = await resolve_portfolio_order_request(
        _registry(store),
        FakePortfolioService(),
        "p1",
        {
            "ticker": "GOOGL",
            "market": "us",
            "order_side": "buy",
            "price": 359.91,
            "qty": 10,
        },
    )

    assert body.ticker == "GOOG"
    assert body.order_time == "2026-07-03"
    assert meta.kline_symbol == "GOOG"
    assert body.resolved_bar is not None
    assert body.resolved_bar.date == "2026-07-03"
    assert any(call["symbol"] == "GOOGL" for call in store.calls)
    assert any(call["symbol"] == "GOOG" for call in store.calls)


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


@pytest.mark.asyncio
async def test_resolve_sell_defaults_to_held_shares_on_liquidation_intent() -> None:
    store = FakeKlineStore([Bar("2026-06-18", 357.89, 369.0, 356.61, 367.46)])
    service = FakePortfolioService()
    service.detail = PortfolioDetail(
        id="p1",
        name="Test",
        config=PortfolioCapitalConfig(
            start_date="2025-01-01",
            capital_by_market={"us": 1_000_000.0, "sh": 1_000_000.0, "hk": 1_000_000.0},
        ),
        orders=[],
        positions=[PortfolioPositionView(ticker="GOOG", market="us", name="Alphabet", shares=1000.0)],
    )
    from dojoagents.tools.process_registry import active_user_message

    token = active_user_message.set("请全部清仓")
    try:
        body, meta = await resolve_portfolio_order_request(
            _registry(store),
            service,
            "p1",
            {"ticker": "GOOG", "market": "us", "order_side": "sell"},
        )
    finally:
        active_user_message.reset(token)

    assert body.qty == 1000.0
    assert meta.qty_source == "held_shares"


@pytest.mark.asyncio
async def test_resolve_sell_without_qty_escalates_for_partial_sell_intent() -> None:
    store = FakeKlineStore([Bar("2026-06-18", 357.89, 369.0, 356.61, 367.46)])
    service = FakePortfolioService()
    service.detail = PortfolioDetail(
        id="p1",
        name="Test",
        config=PortfolioCapitalConfig(
            start_date="2025-01-01",
            capital_by_market={"us": 1_000_000.0, "sh": 1_000_000.0, "hk": 1_000_000.0},
        ),
        orders=[],
        positions=[PortfolioPositionView(ticker="GOOG", market="us", name="Alphabet", shares=1000.0)],
    )
    from dojoagents.tools.process_registry import active_user_message

    token = active_user_message.set("卖出 GOOG")
    try:
        with pytest.raises(AgentEscalationError) as exc_info:
            await resolve_portfolio_order_request(
                _registry(store),
                service,
                "p1",
                {"ticker": "GOOG", "market": "us", "order_side": "sell"},
            )
    finally:
        active_user_message.reset(token)

    assert exc_info.value.code == "sell_qty_unspecified"
    assert exc_info.value.context.get("held_shares") == 1000.0
    assert exc_info.value.context.get("user_options")


@pytest.mark.asyncio
async def test_resolve_sell_uses_qty_pct_when_provided() -> None:
    store = FakeKlineStore([Bar("2026-06-18", 357.89, 369.0, 356.61, 367.46)])
    service = FakePortfolioService()
    service.detail = PortfolioDetail(
        id="p1",
        name="Test",
        config=PortfolioCapitalConfig(
            start_date="2025-01-01",
            capital_by_market={"us": 1_000_000.0, "sh": 1_000_000.0, "hk": 1_000_000.0},
        ),
        orders=[],
        positions=[PortfolioPositionView(ticker="GOOG", market="us", name="Alphabet", shares=1000.0)],
    )
    body, meta = await resolve_portfolio_order_request(
        _registry(store),
        service,
        "p1",
        {"ticker": "GOOG", "market": "us", "order_side": "sell", "qty_pct": 0.5},
    )

    assert body.qty == 500.0
    assert meta.qty_source == "qty_pct"

