from __future__ import annotations

from typing import Optional

from dojoagents.dashboard.services.stock_store import StockStore
from dojoagents.dashboard.schemas.dojo_core import CoreTickerQuoteResponse

MARKETS = ("sh", "hk", "us")


def resolve_core_ticker_quote(
    ticker: str,
    *,
    market: Optional[str] = None,
    stock_store: StockStore,
) -> Optional[CoreTickerQuoteResponse]:
    """Return live quote snapshot for a DojoCore ticker from the in-memory stock store."""
    symbol = ticker.strip()
    if not symbol:
        return None

    market_code = (market or stock_store.find_market(symbol) or "").lower()
    if market_code not in MARKETS:
        return None

    stock = stock_store.get(market_code, symbol)
    if stock is None or stock.stock_quote is None:
        return None

    quote = stock.stock_quote
    amount = quote.amount if quote.amount and quote.amount > 0 else None
    total_shares = quote.total_shares if quote.total_shares and quote.total_shares > 0 else None
    return CoreTickerQuoteResponse(
        ticker=symbol,
        market=market_code,
        currency=stock.currency,
        last_price=quote.last_price,
        change=quote.change,
        change_percent=quote.change_percent,
        pre_close=quote.pre_close,
        open=quote.open,
        high=quote.high,
        low=quote.low,
        volume=quote.volume,
        amount=amount,
        total_shares=total_shares,
        market_cap=quote.market_cap,
        pe=quote.pe,
        forward_pe=stock.forward_pe,
        pb=quote.pb,
        turn_rate=quote.turn_rate,
        exchange_name=stock.full_exchange_name,
        industry=stock.industry,
        sector=stock.sector,
        country=stock.country,
    )
