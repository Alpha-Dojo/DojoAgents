"""Leader concentration: share of sector return explained by the top contributor."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal, Sequence

LeaderConcentrationTier = Literal["extreme", "moderate", "healthy"]

EXTREME_THRESHOLD_PCT = 80.0
MODERATE_THRESHOLD_PCT = 50.0
_MIN_SECTOR_RETURN_ABS = 1e-9


@dataclass(frozen=True)
class LeaderConcentration:
    leader_ticker: str
    leader_weight_pct: float
    leader_return_pct: float
    leader_contribution_pct: float
    leader_concentration_pct: float
    leader_concentration_tier: LeaderConcentrationTier


def leader_concentration_tier(concentration_pct: float) -> LeaderConcentrationTier:
    magnitude = abs(float(concentration_pct))
    if magnitude > EXTREME_THRESHOLD_PCT:
        return "extreme"
    if magnitude >= MODERATE_THRESHOLD_PCT:
        return "moderate"
    return "healthy"


def compute_leader_concentration(
    members: Sequence[tuple[str, float | None, float | None]],
    sector_return_pct: float,
) -> LeaderConcentration | None:
    """Top-1 contributor share of sector index return.

    members: (ticker, market_cap, return_pct)
    leader = argmax |weight × return|
    concentration = (weight × return) / sector_return × 100

    Values >100% mean other names dragged against the leader's contribution.
    """
    try:
        sector_ret = float(sector_return_pct)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(sector_ret) or abs(sector_ret) < _MIN_SECTOR_RETURN_ABS:
        return None

    cleaned: list[tuple[str, float, float]] = []
    for ticker, market_cap, return_pct in members:
        name = str(ticker or "").strip()
        if not name:
            continue
        try:
            cap = float(market_cap) if market_cap is not None else float("nan")
            ret = float(return_pct) if return_pct is not None else float("nan")
        except (TypeError, ValueError):
            continue
        if not math.isfinite(cap) or cap <= 0 or not math.isfinite(ret):
            continue
        cleaned.append((name, cap, ret))

    if not cleaned:
        return None

    total_cap = sum(cap for _, cap, _ in cleaned)
    if total_cap <= 0:
        return None

    best: tuple[str, float, float, float] | None = None
    # ticker, weight_pct, return_pct, contribution_pct (return points)
    for ticker, cap, ret in cleaned:
        weight_pct = cap / total_cap * 100.0
        contribution_pct = (cap / total_cap) * ret
        if best is None or abs(contribution_pct) > abs(best[3]):
            best = (ticker, weight_pct, ret, contribution_pct)

    if best is None:
        return None

    ticker, weight_pct, ret, contribution_pct = best
    concentration = contribution_pct / sector_ret * 100.0
    if not math.isfinite(concentration):
        return None

    return LeaderConcentration(
        leader_ticker=ticker,
        leader_weight_pct=weight_pct,
        leader_return_pct=ret,
        leader_contribution_pct=contribution_pct,
        leader_concentration_pct=concentration,
        leader_concentration_tier=leader_concentration_tier(concentration),
    )
