from __future__ import annotations

import math
import statistics
from typing import List, Optional, Tuple

from dojoagents.harnesses.built_in.financial.contracts.dojo_sphere import SectorPerformanceMarketStats

TRADING_DAYS_YEAR = 252


def compute_market_performance_stats(
    series: List[Tuple[str, float]],
    window_start: str,
    window_end: str,
) -> Optional[SectorPerformanceMarketStats]:
    """Risk/return stats from market-cap-weighted index on a market's own calendar."""
    if not window_start or not window_end:
        return None

    values = [(day, value) for day, value in series if window_start <= day <= window_end]
    if len(values) < 2:
        return None

    first_value = values[0][1]
    last_value = values[-1][1]
    if first_value <= 0:
        return None

    cumulative_return_pct = round((last_value / first_value - 1) * 100, 2)

    daily_returns: List[float] = []
    for index in range(1, len(values)):
        prev = values[index - 1][1]
        curr = values[index][1]
        if prev > 0:
            daily_returns.append(curr / prev - 1)

    sharpe_ratio: Optional[float] = None
    volatility_pct: Optional[float] = None
    if len(daily_returns) >= 2:
        mean_return = statistics.mean(daily_returns)
        std_return = statistics.stdev(daily_returns)
        if std_return > 0:
            sharpe_ratio = round(mean_return / std_return * math.sqrt(TRADING_DAYS_YEAR), 2)
            volatility_pct = round(std_return * math.sqrt(TRADING_DAYS_YEAR) * 100, 2)
        else:
            volatility_pct = 0.0

    peak = first_value
    max_drawdown_pct = 0.0
    for _, value in values:
        if value > peak:
            peak = value
        if peak > 0:
            drawdown = (value - peak) / peak * 100
            if drawdown < max_drawdown_pct:
                max_drawdown_pct = drawdown

    max_drawdown_pct = round(max_drawdown_pct, 2)

    calmar_ratio: Optional[float] = None
    trading_days = len(values)
    if trading_days > 0 and max_drawdown_pct < 0:
        total_return = last_value / first_value
        annualized_return = total_return ** (TRADING_DAYS_YEAR / trading_days) - 1
        calmar_ratio = round(annualized_return / abs(max_drawdown_pct / 100), 2)

    return SectorPerformanceMarketStats(
        cumulative_return_pct=cumulative_return_pct,
        sharpe_ratio=sharpe_ratio,
        max_drawdown_pct=max_drawdown_pct,
        calmar_ratio=calmar_ratio,
        volatility_pct=volatility_pct,
        trading_days=trading_days,
    )
