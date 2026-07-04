from __future__ import annotations

import pytest

from dojoagents.dashboard.services.portfolio_order_execution import (
    aggregate_positions,
    available_shares,
    explain_order_fill_failure,
    try_fill_order,
)
from dojoagents.dashboard.services.portfolio_store import PortfolioStore


class Bar:
    def __init__(self, bar_time: str, open: float, high: float, low: float, close: float | None = None):
        self.bar_time = bar_time
        self.open = open
        self.high = high
        self.low = low
        self.close = close if close is not None else open

    def get(self, key: str, default=None):
        return getattr(self, key, default)


class FakeKlineStore:
    def __init__(self, bars: list[Bar]) -> None:
        self.bars = bars

    async def get_or_fetch_kline(self, *_args, **_kwargs):
        from dojoagents.dashboard.schemas.stock_kline import StockKlineBar, StockKlineResponse

        return StockKlineResponse(
            symbol="NVDA",
            bars=[
                StockKlineBar(
                    symbol="NVDA",
                    bar_time=bar.bar_time,
                    open=bar.open,
                    high=bar.high,
                    low=bar.low,
                    close=bar.close,
                )
                for bar in self.bars
            ],
        )


class TruncatingFakeKlineStore:
    """Simulates default trailing-window fetch that drops older bars."""

    def __init__(self, bars: list[Bar], *, trailing_limit: int = 2) -> None:
        self.bars = bars
        self.trailing_limit = trailing_limit

    async def get_or_fetch_kline(self, *_args, **kwargs):
        from dojoagents.dashboard.schemas.stock_kline import StockKlineBar, StockKlineResponse

        start = str(kwargs.get("start_time") or "")[:10]
        end = str(kwargs.get("end_time") or "")[:10]
        limit = int(kwargs.get("limit") or 252)

        selected = self.bars
        if start and end:
            selected = [bar for bar in self.bars if start <= bar.bar_time[:10] <= end]
        elif start:
            selected = [bar for bar in self.bars if bar.bar_time[:10] >= start][:limit]
        else:
            selected = self.bars[-self.trailing_limit :]

        return StockKlineResponse(
            symbol="MU",
            bars=[
                StockKlineBar(
                    symbol="MU",
                    bar_time=bar.bar_time,
                    open=bar.open,
                    high=bar.high,
                    low=bar.low,
                    close=bar.close,
                )
                for bar in selected
            ],
        )


@pytest.mark.asyncio
async def test_evaluate_fill_failure_fetches_historical_bar_outside_trailing_window() -> None:
    from dojoagents.dashboard.services.portfolio_order_execution import evaluate_order_fill_failure

    order = {
        "id": "o-hist",
        "ticker": "MU",
        "market": "us",
        "order_side": "buy",
        "order_status": "pending",
        "price": 98.59,
        "qty": 200,
        "order_time": "2025-05-29",
        "created_at": "2026-06-30T00:00:00+00:00",
    }
    store = TruncatingFakeKlineStore(
        [
            Bar("2025-05-29", 98.59, 101.0, 97.0),
            Bar("2026-06-27", 190, 195, 188),
            Bar("2026-06-30", 194, 198, 192),
        ],
        trailing_limit=2,
    )
    failure = await evaluate_order_fill_failure(
        order,
        kline_store=store,
        prior_orders=[],
        initial_capital=1_000_000.0,
    )
    assert failure is None


@pytest.mark.asyncio
async def test_fill_order_without_time_uses_next_day_open() -> None:
    order = {
        "id": "o1",
        "ticker": "NVDA",
        "market": "us",
        "order_side": "buy",
        "order_status": "pending",
        "price": 200.0,
        "qty": 10,
        "order_time": None,
        "created_at": "2026-06-27T00:00:00+00:00",
    }
    store = FakeKlineStore(
        [
            Bar("2026-06-27", 190, 195, 188),
            Bar("2026-06-30", 194, 198, 192),
        ]
    )
    filled = await try_fill_order(
        order,
        kline_store=store,
        prior_orders=[],
        initial_capital=1_000_000.0,
    )
    assert filled["order_status"] == "filled"
    assert filled["fill_price"] == pytest.approx(194.0)
    assert filled["fill_time"].startswith("2026-06-30")


@pytest.mark.asyncio
async def test_fill_order_rejects_buy_when_cash_insufficient() -> None:
    order = {
        "id": "o-cash",
        "ticker": "MU",
        "market": "us",
        "order_side": "buy",
        "order_status": "pending",
        "price": 1128.33,
        "qty": 199999,
        "order_time": "2026-03-01",
        "created_at": "2026-02-28T00:00:00+00:00",
    }
    store = FakeKlineStore([Bar("2026-03-01", 1120, 1140, 1110)])
    filled = await try_fill_order(
        order,
        kline_store=store,
        prior_orders=[],
        initial_capital=1_000_000.0,
    )
    assert filled["order_status"] == "rejected"


@pytest.mark.asyncio
async def test_evaluate_fill_failure_returns_code_for_insufficient_cash() -> None:
    from dojoagents.dashboard.services.portfolio_order_execution import evaluate_order_fill_failure

    order = {
        "id": "o-cash2",
        "ticker": "MU",
        "market": "us",
        "order_side": "buy",
        "order_status": "rejected",
        "price": 1128.33,
        "qty": 199999,
        "order_time": "2026-03-01",
        "created_at": "2026-02-28T00:00:00+00:00",
    }
    store = FakeKlineStore([Bar("2026-03-01", 1120, 1140, 1110)])
    failure = await evaluate_order_fill_failure(
        order,
        kline_store=store,
        prior_orders=[],
        initial_capital=1_000_000.0,
    )
    assert failure is not None
    assert failure.code == "insufficient_cash"
    assert failure.context["available"] == pytest.approx(1_000_000.0)


@pytest.mark.asyncio
async def test_fill_order_with_time_requires_price_in_range() -> None:
    order = {
        "id": "o2",
        "ticker": "NVDA",
        "market": "us",
        "order_side": "buy",
        "order_status": "pending",
        "price": 195.0,
        "qty": 5,
        "order_time": "2026-06-30",
        "created_at": "2026-06-29T00:00:00+00:00",
    }
    store = FakeKlineStore([Bar("2026-06-30", 194, 198, 192)])
    filled = await try_fill_order(
        order,
        kline_store=store,
        prior_orders=[],
        initial_capital=1_000_000.0,
    )
    assert filled["order_status"] == "filled"
    assert filled["fill_price"] == pytest.approx(195.0)


@pytest.mark.asyncio
async def test_explain_fill_failure_when_price_outside_range() -> None:
    order = {
        "id": "o3",
        "ticker": "NVDA",
        "market": "us",
        "order_side": "buy",
        "order_status": "pending",
        "price": 150.28,
        "qty": 100,
        "order_time": "2026-06-30",
        "created_at": "2026-06-29T00:00:00+00:00",
    }
    store = FakeKlineStore([Bar("2026-06-30", 194, 198, 192)])
    reason = await explain_order_fill_failure(
        order,
        kline_store=store,
        prior_orders=[],
        initial_capital=1_000_000.0,
    )
    assert reason is not None
    assert "outside" in reason
    assert "150.28" in reason


@pytest.mark.asyncio
async def test_explain_fill_failure_when_bar_missing() -> None:
    order = {
        "id": "o4",
        "ticker": "NVDA",
        "market": "us",
        "order_side": "buy",
        "order_status": "pending",
        "price": 195.0,
        "qty": 5,
        "order_time": "2026-06-30",
        "created_at": "2026-06-29T00:00:00+00:00",
    }
    store = FakeKlineStore([Bar("2026-06-27", 194, 198, 192)])
    reason = await explain_order_fill_failure(
        order,
        kline_store=store,
        prior_orders=[],
        initial_capital=1_000_000.0,
    )
    assert reason is not None
    assert "no trading bar" in reason


@pytest.mark.asyncio
async def test_explain_fill_failure_when_insufficient_shares() -> None:
    order = {
        "id": "o5",
        "ticker": "AAPL",
        "market": "us",
        "order_side": "sell",
        "order_status": "rejected",
        "price": 286.73,
        "qty": 100,
        "order_time": "2026-06-29",
        "created_at": "2026-06-29T00:00:00+00:00",
    }
    store = FakeKlineStore([Bar("2026-06-29", 280, 290, 275)])
    reason = await explain_order_fill_failure(
        order,
        kline_store=store,
        prior_orders=[],
        initial_capital=1_000_000.0,
    )
    assert reason is not None
    assert "insufficient shares" in reason


@pytest.mark.asyncio
async def test_evaluate_fill_failure_returns_code_for_insufficient_shares() -> None:
    from dojoagents.dashboard.services.portfolio_order_execution import evaluate_order_fill_failure

    order = {
        "id": "o6",
        "ticker": "AAPL",
        "market": "us",
        "order_side": "sell",
        "order_status": "rejected",
        "price": 286.73,
        "qty": 100,
        "order_time": "2026-06-29",
        "created_at": "2026-06-29T00:00:00+00:00",
    }
    store = FakeKlineStore([Bar("2026-06-29", 280, 290, 275)])
    failure = await evaluate_order_fill_failure(
        order,
        kline_store=store,
        prior_orders=[],
        initial_capital=1_000_000.0,
    )
    assert failure is not None
    assert failure.code == "insufficient_shares"
    assert failure.context["held"] == 0


@pytest.mark.asyncio
async def test_evaluate_fill_failure_returns_code_for_price_out_of_range() -> None:
    from dojoagents.dashboard.services.portfolio_order_execution import evaluate_order_fill_failure

    order = {
        "id": "o7",
        "ticker": "NVDA",
        "market": "us",
        "order_side": "buy",
        "order_status": "pending",
        "price": 150.28,
        "qty": 100,
        "order_time": "2026-06-30",
        "created_at": "2026-06-29T00:00:00+00:00",
    }
    store = FakeKlineStore([Bar("2026-06-30", 194, 198, 192)])
    failure = await evaluate_order_fill_failure(
        order,
        kline_store=store,
        prior_orders=[],
        initial_capital=1_000_000.0,
    )
    assert failure is not None
    assert failure.code == "price_out_of_range"


def test_store_migrates_legacy_holdings_to_candidates(tmp_path) -> None:
    portfolio_id = "legacy"
    path = tmp_path / "portfolio" / f"{portfolio_id}.json"
    path.parent.mkdir(parents=True)
    path.write_text(
        """
        {
          "version": 2,
          "id": "legacy",
          "name": "Legacy",
          "config": {"start_date": "2025-01-01", "cost_date": "2025-01-01", "capital_by_market": {"us": 1000000}},
          "holdings": [{"ticker": "AAPL", "market": "us", "shares": 10, "added_at": "2026-01-01T00:00:00+00:00"}]
        }
        """,
        encoding="utf-8",
    )
    (tmp_path / "portfolio" / "index.json").write_text('{"version": 3, "portfolios": []}', encoding="utf-8")
    store = PortfolioStore(tmp_path)
    raw = store.get_raw(portfolio_id)
    assert raw is not None
    assert raw["version"] == 3
    assert raw["candidates"] == [{"ticker": "AAPL", "market": "us", "added_at": "2026-01-01T00:00:00+00:00"}]
    assert raw["orders"] == []


def test_replay_market_balance_does_not_go_negative_on_oversized_buy() -> None:
    from dojoagents.dashboard.services.portfolio_order_execution import replay_market_balance

    orders = [
        {
            "order_status": "filled",
            "market": "us",
            "ticker": "MU",
            "order_side": "buy",
            "qty": 199999,
            "fill_price": 1128.33,
            "fill_time": "2026-03-01T00:00:00+00:00",
            "created_at": "2026-02-28T00:00:00+00:00",
        }
    ]
    cash, held = replay_market_balance(
        orders,
        market="us",
        initial_capital=1_000_000.0,
        as_of_date="2026-03-01",
    )
    assert cash == pytest.approx(1_000_000.0)
    assert held == {}


def test_sanitize_invalid_filled_orders_rejects_oversized_buy() -> None:
    from dojoagents.dashboard.services.portfolio_order_execution import sanitize_invalid_filled_orders

    orders = [
        {
            "id": "bad-buy",
            "order_status": "filled",
            "market": "us",
            "ticker": "MU",
            "order_side": "buy",
            "qty": 199999,
            "fill_price": 1128.33,
            "price": 1128.33,
            "fill_time": "2026-03-01T00:00:00+00:00",
            "created_at": "2026-02-28T00:00:00+00:00",
        }
    ]
    sanitized, changed = sanitize_invalid_filled_orders(orders, capital_by_market={"us": 1_000_000.0})
    assert changed is True
    assert sanitized == []


def test_aggregate_positions_bounded_skips_oversized_buy() -> None:
    from dojoagents.dashboard.services.portfolio_order_execution import aggregate_positions_bounded

    orders = [
        {
            "order_status": "filled",
            "market": "us",
            "ticker": "MU",
            "order_side": "buy",
            "qty": 199999,
            "fill_price": 1128.33,
            "fill_time": "2026-03-01T00:00:00+00:00",
            "created_at": "2026-02-28T00:00:00+00:00",
        }
    ]
    positions = aggregate_positions_bounded(
        orders,
        capital_by_market={"us": 1_000_000.0},
    )
    assert positions == []


def test_aggregate_positions_from_filled_orders() -> None:
    orders = [
        {
            "order_status": "filled",
            "market": "us",
            "ticker": "AAPL",
            "order_side": "buy",
            "qty": 100,
            "fill_price": 10.0,
            "fill_time": "2026-06-01T00:00:00+00:00",
        },
        {
            "order_status": "filled",
            "market": "us",
            "ticker": "AAPL",
            "order_side": "sell",
            "qty": 40,
            "fill_price": 12.0,
            "fill_time": "2026-06-10T00:00:00+00:00",
        },
    ]
    positions = aggregate_positions(orders)
    assert len(positions) == 1
    assert positions[0]["shares"] == pytest.approx(60)
    assert positions[0]["cost_basis"] == pytest.approx(600)
    assert available_shares(orders, market="us", ticker="AAPL") == pytest.approx(60)


class BlockingKlineStore:
    async def get_or_fetch_kline(self, *_args, **_kwargs):
        raise AssertionError("fill path should reuse resolved_bar without refetching kline")


@pytest.mark.asyncio
async def test_try_fill_order_reuses_resolved_bar_without_kline_fetch() -> None:
    order = {
        "id": "o-resolved",
        "ticker": "GOOGL",
        "market": "us",
        "order_side": "buy",
        "order_status": "pending",
        "price": 359.91,
        "qty": 10,
        "order_time": "2026-07-03",
        "created_at": "2026-07-04T00:00:00+00:00",
        "resolved_bar": {
            "date": "2026-07-03",
            "open": 350.0,
            "low": 348.0,
            "high": 362.0,
        },
    }
    filled = await try_fill_order(
        order,
        kline_store=BlockingKlineStore(),
        prior_orders=[],
        initial_capital=1_000_000.0,
    )
    assert filled["order_status"] == "filled"
    assert filled["fill_price"] == pytest.approx(359.91)
    assert filled["fill_time"].startswith("2026-07-03")


@pytest.mark.asyncio
async def test_evaluate_fill_failure_reuses_resolved_bar_without_kline_fetch() -> None:
    from dojoagents.dashboard.services.portfolio_order_execution import evaluate_order_fill_failure

    order = {
        "id": "o-resolved",
        "ticker": "GOOGL",
        "market": "us",
        "order_side": "buy",
        "order_status": "pending",
        "price": 359.91,
        "qty": 10,
        "order_time": "2026-07-03",
        "created_at": "2026-07-04T00:00:00+00:00",
        "resolved_bar": {
            "date": "2026-07-03",
            "open": 350.0,
            "low": 348.0,
            "high": 362.0,
        },
    }
    failure = await evaluate_order_fill_failure(
        order,
        kline_store=BlockingKlineStore(),
        prior_orders=[],
        initial_capital=1_000_000.0,
    )
    assert failure is None
