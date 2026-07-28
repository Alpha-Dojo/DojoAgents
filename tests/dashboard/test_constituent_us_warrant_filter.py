from __future__ import annotations

import pytest

from dojoagents.dashboard.schemas.stock import Stock, StockQuote
from dojoagents.dashboard.schemas.stock_kline import StockKlineBar, StockKlineResponse
from dojoagents.dashboard.services.constituent_filter import (
    is_sector_constituent_eligible,
    stock_is_us_warrant_by_name,
)
from dojoagents.dashboard.services.sector_earnings_index import stock_passes_sector_performance_weight


def _quote(*, name: str = "FGIWW", market_cap: float = 2e9, volume: int = 100) -> StockQuote:
    return StockQuote(
        ticker="FGIWW",
        name=name,
        last_price=1.75,
        pre_close=0.34,
        open=1.0,
        high=2.0,
        low=0.5,
        change=1.41,
        change_percent=419.6,
        volume=volume,
        amount=1e6,
        avg_price=1.5,
        market_cap=market_cap,
        total_shares=1e9,
        turn_rate=1.0,
        pe=0.0,
        pb=0.0,
        dividend_yield=0.0,
    )


def test_us_warrant_detected_from_short_name() -> None:
    stock = Stock(
        ticker="FGIWW",
        market="us",
        short_name="FGI Industries Ltd. Warrant",
        long_name="FGI Industries Ltd.",
        stock_quote=_quote(),
    )
    assert stock_is_us_warrant_by_name(stock) is True


def test_us_warrant_detected_case_insensitive_from_quote_name() -> None:
    stock = Stock(
        ticker="CLSKW",
        market="us",
        short_name="CleanSpark",
        stock_quote=_quote(name="CleanSpark, Inc. WARRANTS"),
    )
    assert stock_is_us_warrant_by_name(stock) is True


def test_cn_company_name_with_warrant_not_excluded() -> None:
    stock = Stock(
        ticker="688799.SS",
        market="sh",
        short_name="HUNAN WARRANT PHARMACEUTICAL CO",
        stock_quote=_quote(name="HUNAN WARRANT PHARMACEUTICAL CO"),
    )
    assert stock_is_us_warrant_by_name(stock) is False


def test_us_common_stock_without_warrant_passes() -> None:
    stock = Stock(
        ticker="SONY",
        market="us",
        short_name="Sony Group Corporation",
        long_name="Sony Group Corporation",
        stock_quote=_quote(name="Sony Group Corporation"),
    )
    assert stock_is_us_warrant_by_name(stock) is False
    assert stock_passes_sector_performance_weight(stock) is True


def test_us_warrant_fails_sector_performance_weight() -> None:
    stock = Stock(
        ticker="FGIWW",
        market="us",
        short_name="FGI Industries Ltd. Warrant",
        stock_quote=_quote(),
    )
    assert stock_passes_sector_performance_weight(stock) is False


@pytest.mark.asyncio
async def test_us_warrant_not_constituent_eligible() -> None:
    class _KlineStore:
        async def get_or_fetch_kline(self, symbol: str, **kwargs):
            return StockKlineResponse(
                symbol=symbol,
                as_of="2026-07-28",
                bars=[
                    StockKlineBar(
                        symbol=symbol,
                        bar_time="2026-07-28",
                        close=1.75,
                        open=1.0,
                        high=2.0,
                        low=0.5,
                        vol=100,
                    )
                ],
            )

    stock = Stock(
        ticker="FGIWW",
        market="us",
        short_name="FGI Industries Ltd. Warrant",
        stock_quote=_quote(),
    )
    assert await is_sector_constituent_eligible(stock, _KlineStore()) is False
