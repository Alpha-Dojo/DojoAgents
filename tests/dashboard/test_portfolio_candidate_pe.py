from __future__ import annotations

import pytest

from dojoagents.dashboard.schemas.stock import Stock, StockQuote
from dojoagents.dashboard.services.portfolio_service import PortfolioService
from dojoagents.dashboard.services.portfolio_store import PortfolioStore


def _quote(*, pe: float, pb: float = 2.0) -> StockQuote:
    return StockQuote(
        ticker="002230",
        name="iFLYTEK",
        last_price=40.84,
        pre_close=39.46,
        open=40.0,
        high=41.0,
        low=39.5,
        change=1.38,
        change_percent=3.5,
        volume=1,
        amount=40.84,
        avg_price=40.84,
        market_cap=98_100_000_000,
        turn_rate=1.2,
        pe=pe,
        pb=pb,
        dividend_yield=0.0,
    )


@pytest.mark.asyncio
async def test_candidate_preserves_positive_pe(tmp_path) -> None:
    store = PortfolioStore(tmp_path)
    portfolio = store.create("CN Tech")
    store.add_candidate(portfolio["id"], ticker="002230", market="sh")

    stock = Stock(ticker="002230", market="sh", short_name="科大讯飞", stock_quote=_quote(pe=113.7))

    class Stocks:
        def get(self, market, ticker):
            if market == "sh" and ticker == "002230":
                return stock
            return None

        def find_market(self, ticker):
            return "sh" if ticker == "002230" else None

    service = PortfolioService(store, Stocks(), _EmptySectorStore(), _NoKlineStore())
    detail = await service.get_detail(portfolio["id"], include_performance=False)

    assert detail is not None
    assert len(detail.candidates) == 1
    assert detail.candidates[0].pe == pytest.approx(113.7)


@pytest.mark.asyncio
async def test_candidate_preserves_negative_pe_for_loss_display(tmp_path) -> None:
    store = PortfolioStore(tmp_path)
    portfolio = store.create("Loss Makers")
    store.add_candidate(portfolio["id"], ticker="BIDU", market="us")

    stock = Stock(ticker="BIDU", market="us", short_name="Baidu", stock_quote=_quote(pe=-12.5))

    class Stocks:
        def get(self, market, ticker):
            if market == "us" and ticker == "BIDU":
                return stock
            return None

        def find_market(self, ticker):
            return "us" if ticker == "BIDU" else None

    service = PortfolioService(store, Stocks(), _EmptySectorStore(), _NoKlineStore())
    detail = await service.get_detail(portfolio["id"], include_performance=False)

    assert detail is not None
    assert len(detail.candidates) == 1
    assert detail.candidates[0].pe == pytest.approx(-12.5)


class _EmptySectorStore:
    def get(self, *_args):
        return None


class _NoKlineStore:
    async def get_or_fetch_kline(self, *_args, **_kwargs):
        return None
