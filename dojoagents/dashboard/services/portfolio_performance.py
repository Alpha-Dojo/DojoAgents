from __future__ import annotations

import math
import statistics

from dojoagents.dashboard.schemas.portfolio import (
    PortfolioMarketPerformance,
    PortfolioRiskStats,
)


def compute_risk_stats(nav: list[float]) -> PortfolioRiskStats:
    values = [float(value) for value in nav if math.isfinite(float(value)) and value > 0]
    if not values:
        return PortfolioRiskStats()
    returns = [values[index] / values[index - 1] - 1 for index in range(1, len(values))]
    cumulative = (values[-1] / values[0] - 1) * 100 if values[0] else None
    volatility: float | None = None
    sharpe: float | None = None
    if returns:
        daily_vol = statistics.pstdev(returns)
        volatility = daily_vol * math.sqrt(252) * 100
        if daily_vol > 0:
            sharpe = statistics.fmean(returns) / daily_vol * math.sqrt(252)

    peak = values[0]
    max_drawdown = 0.0
    for value in values:
        peak = max(peak, value)
        drawdown = (value / peak - 1) * 100
        max_drawdown = min(max_drawdown, drawdown)

    calmar: float | None = None
    if len(values) > 1 and max_drawdown < 0:
        annualized = ((values[-1] / values[0]) ** (252 / (len(values) - 1)) - 1) * 100
        calmar = annualized / abs(max_drawdown)
    return PortfolioRiskStats(
        cumulative_return_pct=cumulative,
        volatility_pct=volatility,
        sharpe_ratio=sharpe,
        max_drawdown_pct=max_drawdown,
        calmar_ratio=calmar,
        trading_days=len(values),
    )


def build_market_performance(
    *,
    market: str,
    holdings: list[dict],
    benchmark_symbol: str,
    benchmark_closes: dict[str, float],
) -> PortfolioMarketPerformance:
    date_sets = [set(benchmark_closes)]
    date_sets.extend(set(holding.get("closes", {})) for holding in holdings if isinstance(holding.get("closes"), dict))
    dates = sorted(set.intersection(*date_sets)) if date_sets and holdings else []
    values = [sum(float(holding.get("shares") or 0) * float(holding["closes"][day]) for holding in holdings) for day in dates]
    benchmark_values = [float(benchmark_closes[day]) for day in dates]

    def rebase(series: list[float]) -> list[float]:
        if not series or series[0] <= 0:
            return []
        return [value / series[0] * 100 for value in series]

    portfolio_nav = rebase(values)
    benchmark_nav = rebase(benchmark_values)
    return PortfolioMarketPerformance(
        market=market,
        dates=dates,
        portfolio=portfolio_nav,
        benchmark=benchmark_nav,
        benchmark_symbol=benchmark_symbol,
        stats=compute_risk_stats(portfolio_nav),
    )
