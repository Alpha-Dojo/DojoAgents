from __future__ import annotations

import pytest

from dojoagents.harnesses.built_in.financial.contracts.portfolio import (
    AddPortfolioHoldingRequest,
    CreatePortfolioOrderRequest,
)
from dojoagents.harnesses.built_in.financial.contracts.stock import Stock, StockQuote
from dojoagents.harnesses.built_in.financial.services.portfolio_service import PortfolioService, PortfolioOrderFillError
from dojoagents.harnesses.built_in.financial.services.portfolio_store import PortfolioStore


def _quote(*, ticker: str, last_price: float) -> StockQuote:
    return StockQuote(
        ticker=ticker,
        name="Kuaishou-W",
        last_price=last_price,
        pre_close=last_price,
        open=last_price,
        high=last_price,
        low=last_price,
        change=0.0,
        change_percent=0.0,
        volume=1,
        amount=last_price,
        avg_price=last_price,
        market_cap=100_000_000_000,
        turn_rate=1.2,
        pe=20.0,
        pb=3.0,
        dividend_yield=0.0,
    )


class _HkStockStore:
    def __init__(self) -> None:
        self.stock = Stock(
            ticker="1024.HK",
            market="hk",
            short_name="快手-W",
            stock_quote=_quote(ticker="1024.HK", last_price=48.46),
        )

    def get(self, market: str, ticker: str) -> Stock | None:
        if market == "hk" and ticker.upper() == "1024.HK":
            return self.stock
        return None

    def resolve(self, ticker: str, market: str | None = None) -> Stock | None:
        if market == "hk" and ticker.upper() == "1024.HK":
            return self.stock
        return None

    def find_market(self, ticker: str) -> str | None:
        return "hk" if ticker.upper() == "1024.HK" else None


class _EmptySectorStore:
    def get(self, *_args, **_kwargs):
        return None


class _NoKlineStore:
    async def get_or_fetch_kline(self, *_args, **_kwargs):
        return None


@pytest.mark.asyncio
async def test_add_holding_resolves_bare_hk_ticker(tmp_path) -> None:
    store = PortfolioStore(tmp_path)
    portfolio = store.create("HK Test")
    service = PortfolioService(store, _HkStockStore(), _EmptySectorStore(), _NoKlineStore())

    detail = await service.add_holding(
        portfolio["id"],
        AddPortfolioHoldingRequest(ticker="1024", market="hk"),
    )

    assert detail is not None
    assert len(detail.candidates) == 1
    candidate = detail.candidates[0]
    assert candidate.ticker == "1024.HK"
    assert candidate.name == "快手-W"
    assert candidate.price == pytest.approx(48.46)


@pytest.mark.asyncio
async def test_create_order_resolves_bare_hk_ticker(tmp_path) -> None:
    store = PortfolioStore(tmp_path)
    portfolio = store.create("HK Order Test")
    service = PortfolioService(store, _HkStockStore(), _EmptySectorStore(), _NoKlineStore())

    with pytest.raises(PortfolioOrderFillError, match=r"1024\.HK"):
        await service.create_order(
            portfolio["id"],
            CreatePortfolioOrderRequest(
                ticker="1024",
                market="hk",
                order_side="buy",
                price=48.46,
                qty=100,
                order_time="2026-01-02",
            ),
        )
