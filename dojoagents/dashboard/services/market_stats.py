from __future__ import annotations

from typing import List, Optional

from dojoagents.dashboard.schemas.market import MarketStats
from dojoagents.dashboard.schemas.stock import Stock


def _valid_pe(pe: float) -> bool:
    return pe > 0


def compute_market_stats(market: str, stocks: List[Stock]) -> MarketStats:
    """Aggregate cap / PE stats from preloaded stocks (name + quote filters applied)."""
    total_cap = 0.0
    pe_eligible_cap = 0.0
    total_earning = 0.0
    pe_sum = 0.0
    pe_count = 0

    for stock in stocks:
        quote = stock.stock_quote
        if quote is None:
            continue

        cap = quote.market_cap
        if cap > 0:
            total_cap += cap

        pe = quote.pe
        if not _valid_pe(pe) or cap <= 0:
            continue

        pe_count += 1
        pe_sum += pe
        pe_eligible_cap += cap
        total_earning += cap / pe

    weighted_pe: Optional[float] = None
    if pe_eligible_cap > 0 and total_earning > 0:
        # cap/PE weighted: only constituents with positive PE enter numerator and denominator.
        weighted_pe = round(pe_eligible_cap / total_earning, 2)

    simple_pe: Optional[float] = None
    if pe_count > 0:
        simple_pe = round(pe_sum / pe_count, 2)

    return MarketStats(
        market=market,
        listed_count=len(stocks),
        total_market_cap=total_cap,
        weighted_pe=weighted_pe,
        simple_pe=simple_pe,
        pe_sample_count=pe_count,
    )
