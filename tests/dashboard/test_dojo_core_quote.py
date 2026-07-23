from __future__ import annotations

from types import SimpleNamespace

from dojoagents.harnesses.built_in.financial.contracts.stock import StockQuote
from dojoagents.harnesses.built_in.financial.services.dojo_core_quote import resolve_core_ticker_quote


class FakeStockStore:
    def resolve(self, ticker, market=None):
        return self.get(market or "hk", ticker)

    def find_market(self, ticker):
        if ticker in {"0700", "0700.HK"}:
            return "hk"
        return None

    def get(self, market, ticker):
        if market == "hk" and ticker == "0700.HK":
            return SimpleNamespace(
                ticker="0700.HK",
                market="hk",
                currency="HKD",
                forward_pe=None,
                full_exchange_name="HKEX",
                industry="Internet",
                sector="Technology",
                country="Hong Kong",
                stock_quote=StockQuote(
                    ticker="0700.HK",
                    name="Tencent",
                    last_price=431.2,
                    pre_close=440.0,
                    open=433.0,
                    high=445.8,
                    low=431.2,
                    change=-8.8,
                    change_percent=-2.0,
                    volume=24957296,
                    amount=1.0,
                    avg_price=0.0,
                    market_cap=1.0,
                    total_shares=1.0,
                    turn_rate=0.0,
                    pe=20.0,
                    pb=4.0,
                    dividend_yield=0.0,
                ),
            )
        return None


def test_resolve_core_ticker_quote_maps_bare_hk_code_to_suffix() -> None:
    quote = resolve_core_ticker_quote("0700", market="hk", stock_store=FakeStockStore())
    assert quote is not None
    assert quote.ticker == "0700.HK"
    assert quote.last_price == 431.2


def test_resolve_core_ticker_quote_returns_none_for_unknown_bare_code_without_market() -> None:
    quote = resolve_core_ticker_quote("0700", stock_store=FakeStockStore())
    assert quote is None
