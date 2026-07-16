from __future__ import annotations

from dojoagents.dashboard.services.domain_utils import finite_float

# Leader/laggard rankings need a real basket. `member_count` comes from sector
# precompute and already counts only index-eligible constituents (positive
# market cap + tradable), not the raw taxonomy membership list.
MIN_SECTOR_MEMBER_COUNT_FOR_MOVERS_RANKING = 5


def sector_eligible_for_movers_ranking(
    *,
    member_count: int,
    total_market_cap: float = 0.0,
    min_total_market_cap: float = 0.0,
) -> bool:
    """True when an L3 sector may appear in gainers/losers / discovery rankings."""
    if int(member_count or 0) < MIN_SECTOR_MEMBER_COUNT_FOR_MOVERS_RANKING:
        return False
    if min_total_market_cap > 0 and finite_float(total_market_cap) < min_total_market_cap:
        return False
    return True
