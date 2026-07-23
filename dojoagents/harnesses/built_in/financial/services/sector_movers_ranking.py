from __future__ import annotations

from dojoagents.harnesses.built_in.financial.services.domain_utils import finite_float

# Leader/laggard rankings need a real basket. `member_count` comes from sector
# precompute and counts only index-eligible constituents: above the per-ticker
# market-cap floor (~10亿), positive cap, and tradable — not the raw taxonomy list.
MIN_SECTOR_MEMBER_COUNT_FOR_MOVERS_RANKING = 5

# Matches dashboard UI `DEFAULT_MIN_CAP_YI=200` (亿) × 1e8 local-currency units.
# Agent `get_sector_movers` applies this when min_cap_* args are omitted.
DEFAULT_SECTOR_MOVERS_MIN_TOTAL_MARKET_CAP = 200 * 1e8


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
