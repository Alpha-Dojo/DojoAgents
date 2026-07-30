from __future__ import annotations

import pytest

from dojoagents.dashboard.schemas.stock import Stock, StockQuote
from dojoagents.dashboard.schemas.stock_kline import StockKlineBar, StockKlineResponse
from dojoagents.dashboard.services.constituent_filter import (
    is_sector_constituent_eligible,
    stock_is_equity_quote_type,
)
from dojoagents.dashboard.services.sector_earnings_index import stock_passes_sector_performance_weight


def _quote(*, ticker: str = "AAPL", market_cap: float = 2e9, volume: int = 100) -> StockQuote:
    return StockQuote(
        ticker=ticker,
        name=ticker,
        last_price=10.0,
        pre_close=9.0,
        open=10.0,
        high=11.0,
        low=9.0,
        change=1.0,
        change_percent=10.0,
        volume=volume,
        amount=1e6,
        avg_price=10.0,
        market_cap=market_cap,
        total_shares=1e9,
        turn_rate=1.0,
        pe=10.0,
        pb=2.0,
        dividend_yield=0.0,
    )


@pytest.mark.parametrize(
    ("quote_type", "expected"),
    [
        ("EQUITY", True),
        ("equity", True),
        ("ETF", False),
        ("MUTUALFUND", False),
        ("INDEX", False),
        (None, False),
        ("", False),
    ],
)
def test_stock_is_equity_quote_type(quote_type: str | None, expected: bool) -> None:
    stock = Stock(ticker="X", market="us", quote_type=quote_type, stock_quote=_quote())
    assert stock_is_equity_quote_type(stock) is expected


def test_etf_fails_sector_performance_weight() -> None:
    stock = Stock(
        ticker="IAU",
        market="us",
        short_name="iShares Gold Trust Shares",
        quote_type="ETF",
        stock_quote=_quote(ticker="IAU"),
    )
    assert stock_passes_sector_performance_weight(stock) is False


@pytest.mark.asyncio
async def test_etf_not_constituent_eligible() -> None:
    class _KlineStore:
        async def get_or_fetch_kline(self, symbol: str, **kwargs):
            return StockKlineResponse(
                symbol=symbol,
                as_of="2026-07-28",
                bars=[
                    StockKlineBar(
                        symbol=symbol,
                        bar_time="2026-07-28",
                        close=10.0,
                        open=10.0,
                        high=10.0,
                        low=10.0,
                        vol=100,
                    )
                ],
            )

    stock = Stock(
        ticker="IAU",
        market="us",
        quote_type="ETF",
        stock_quote=_quote(ticker="IAU"),
    )
    assert await is_sector_constituent_eligible(stock, _KlineStore()) is False


@pytest.mark.asyncio
async def test_equity_constituent_eligible() -> None:
    class _KlineStore:
        async def get_or_fetch_kline(self, symbol: str, **kwargs):
            return StockKlineResponse(
                symbol=symbol,
                as_of="2026-07-28",
                bars=[
                    StockKlineBar(
                        symbol=symbol,
                        bar_time="2026-07-28",
                        close=10.0,
                        open=10.0,
                        high=10.0,
                        low=10.0,
                        vol=100,
                    )
                ],
            )

    stock = Stock(
        ticker="AAPL",
        market="us",
        quote_type="EQUITY",
        stock_quote=_quote(),
    )
    assert await is_sector_constituent_eligible(stock, _KlineStore()) is True
