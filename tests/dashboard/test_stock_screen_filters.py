from __future__ import annotations

import math
from types import SimpleNamespace

import pytest

from dojoagents.dashboard.schemas.stock import Stock, StockQuote
from dojoagents.dashboard.services.domain_api import build_stock_screen
from dojoagents.dashboard.services.stock_quote_filter import (
    change_significance_score,
    configure_ticker_market_cap_mins,
    effective_min_market_cap,
    passes_market_cap_floor,
    stock_passes_market_screen_hard_filters,
)


def _quote(
    *,
    ticker: str = "AAA",
    market_cap: float = 5e9,
    change_percent: float = 1.0,
    volume: int = 1000,
    amount: float = 1e6,
    turn_rate: float = 0.5,
) -> StockQuote:
    return StockQuote(
        ticker=ticker,
        name=ticker,
        last_price=10.0,
        pre_close=9.9,
        open=10.0,
        high=10.5,
        low=9.8,
        change=0.1,
        change_percent=change_percent,
        volume=volume,
        amount=amount,
        avg_price=10.0,
        market_cap=market_cap,
        turn_rate=turn_rate,
        pe=15.0,
        pb=2.0,
        dividend_yield=0.0,
    )


def _stock(
    *,
    ticker: str = "AAA",
    market: str = "us",
    market_cap: float = 5e9,
    change_percent: float = 1.0,
    volume: int = 1000,
    amount: float | None = None,
    turn_rate: float | None = None,
    is_delisted: bool | None = None,
) -> Stock:
    quote_kwargs: dict = {
        "ticker": ticker,
        "market_cap": market_cap,
        "change_percent": change_percent,
        "volume": volume,
    }
    if amount is not None:
        quote_kwargs["amount"] = amount
    if turn_rate is not None:
        quote_kwargs["turn_rate"] = turn_rate
    return Stock(
        ticker=ticker,
        market=market,
        stock_quote=_quote(**quote_kwargs),
        is_delisted=is_delisted,
    )


@pytest.fixture(autouse=True)
def _reset_cap_config() -> None:
    configure_ticker_market_cap_mins(sh=1e9, us=1e9, hk=1e9)
    yield
    configure_ticker_market_cap_mins(sh=1e9, us=1e9, hk=1e9)


def test_hard_filters_exclude_delisted_zero_volume_and_zero_cap() -> None:
    assert stock_passes_market_screen_hard_filters(_stock()) is True
    assert stock_passes_market_screen_hard_filters(_stock(is_delisted=True)) is False
    assert stock_passes_market_screen_hard_filters(_stock(volume=0, amount=0.0, turn_rate=0.0)) is False
    assert stock_passes_market_screen_hard_filters(_stock(market_cap=0.0)) is False
    assert stock_passes_market_screen_hard_filters(Stock(ticker="X", market="us", stock_quote=None)) is False


def test_trading_activity_accepts_amount_or_turn_rate_without_volume() -> None:
    quote = _quote(volume=0, amount=0.0, turn_rate=0.0)
    stock = Stock(ticker="BBB", market="us", stock_quote=quote)
    assert stock_passes_market_screen_hard_filters(stock) is False

    quote_amount = _quote(volume=0, amount=250_000.0, turn_rate=0.0)
    stock_amount = Stock(ticker="CCC", market="us", stock_quote=quote_amount)
    assert stock_passes_market_screen_hard_filters(stock_amount) is True

    quote_turn = _quote(volume=0, amount=0.0, turn_rate=0.01)
    stock_turn = Stock(ticker="DDD", market="us", stock_quote=quote_turn)
    assert stock_passes_market_screen_hard_filters(stock_turn) is True


def test_effective_min_market_cap_defaults_to_config() -> None:
    configure_ticker_market_cap_mins(sh=2e9, us=3e9, hk=4e9)
    assert effective_min_market_cap("us", None) == 3e9
    assert effective_min_market_cap("us", 0) == 0
    assert effective_min_market_cap("us", 5e8) == 5e8


def test_passes_market_cap_floor_uses_strict_greater_than() -> None:
    assert passes_market_cap_floor("us", 2e9, min_market_cap=None) is True
    assert passes_market_cap_floor("us", 1e9, min_market_cap=None) is False
    assert passes_market_cap_floor("us", 5e8, min_market_cap=0) is True


def test_change_significance_score_prefers_larger_caps_at_same_move() -> None:
    micro = change_significance_score(-50.0, 1e5)
    large = change_significance_score(-8.0, 2e11)
    assert large > micro


def test_change_significance_score_formula() -> None:
    assert change_significance_score(10.0, 1e9) == pytest.approx(10.0 * math.log(1e9))
    assert change_significance_score(None, 1e9) == float("-inf")


@pytest.mark.asyncio
async def test_build_stock_screen_applies_hard_filters_and_default_cap() -> None:
    stocks = [
        _stock(ticker="BIG", market_cap=5e9, change_percent=-5.0),
        _stock(ticker="MICRO", market_cap=5e7, change_percent=-70.0),
        _stock(ticker="DEAD", market_cap=5e9, change_percent=-3.0, volume=0, amount=0.0, turn_rate=0.0),
        _stock(ticker="DELIST", market_cap=5e9, change_percent=-2.0, is_delisted=True),
    ]
    registry = SimpleNamespace(stock_store=SimpleNamespace(list_market=lambda _market: stocks))

    result = await build_stock_screen(
        registry,
        market="us",
        days=0,
        min_market_cap=None,
        max_market_cap=None,
        min_return_pct=None,
        max_return_pct=None,
        min_pe=None,
        max_pe=None,
        min_change_percent=None,
        max_change_percent=None,
        sort_by="change_percent",
        sort_order="asc",
        limit=10,
    )

    assert result.universe_count == 2
    assert result.match_count == 1
    assert [item.ticker for item in result.items] == ["BIG"]


@pytest.mark.asyncio
async def test_build_stock_screen_allows_micro_caps_when_min_cap_zero() -> None:
    stocks = [
        _stock(ticker="BIG", market_cap=5e9, change_percent=-5.0),
        _stock(ticker="MICRO", market_cap=5e7, change_percent=-70.0),
    ]
    registry = SimpleNamespace(stock_store=SimpleNamespace(list_market=lambda _market: stocks))

    result = await build_stock_screen(
        registry,
        market="us",
        days=0,
        min_market_cap=0,
        max_market_cap=None,
        min_return_pct=None,
        max_return_pct=None,
        min_pe=None,
        max_pe=None,
        min_change_percent=None,
        max_change_percent=None,
        sort_by="change_percent",
        sort_order="asc",
        limit=10,
    )

    assert result.match_count == 2
    assert result.items[0].ticker == "BIG"
    assert result.items[1].ticker == "MICRO"


@pytest.mark.asyncio
async def test_build_stock_screen_significance_sort_ranks_large_mover_first() -> None:
    stocks = [
        _stock(ticker="MICRO", market_cap=5e7, change_percent=-70.0),
        _stock(ticker="MEGA", market_cap=2e11, change_percent=-8.0),
    ]
    registry = SimpleNamespace(stock_store=SimpleNamespace(list_market=lambda _market: stocks))

    result = await build_stock_screen(
        registry,
        market="us",
        days=0,
        min_market_cap=0,
        max_market_cap=None,
        min_return_pct=None,
        max_return_pct=None,
        min_pe=None,
        max_pe=None,
        min_change_percent=None,
        max_change_percent=None,
        sort_by="change_percent",
        sort_order="asc",
        limit=10,
    )

    assert [item.ticker for item in result.items] == ["MEGA", "MICRO"]


@pytest.mark.asyncio
async def test_build_stock_screen_respects_max_market_cap() -> None:
    stocks = [
        _stock(ticker="MID", market_cap=5e9, change_percent=10.0),
        _stock(ticker="MEGA", market_cap=2e11, change_percent=5.0),
    ]
    registry = SimpleNamespace(stock_store=SimpleNamespace(list_market=lambda _market: stocks))

    result = await build_stock_screen(
        registry,
        market="us",
        days=0,
        min_market_cap=0,
        max_market_cap=1e10,
        min_return_pct=None,
        max_return_pct=None,
        min_pe=None,
        max_pe=None,
        min_change_percent=None,
        max_change_percent=None,
        sort_by="change_percent",
        sort_order="desc",
        limit=10,
    )

    assert result.match_count == 1
    assert result.items[0].ticker == "MID"
