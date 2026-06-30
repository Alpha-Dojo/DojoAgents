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
        if daily_vol > 0:
            volatility = daily_vol * math.sqrt(252) * 100
            sharpe = statistics.fmean(returns) / daily_vol * math.sqrt(252)
        else:
            volatility = 0.0

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
        cumulative_return_pct=cumulative if cumulative is None or math.isfinite(cumulative) else None,
        volatility_pct=volatility if volatility is None or math.isfinite(volatility) else None,
        sharpe_ratio=sharpe if sharpe is None or math.isfinite(sharpe) else None,
        max_drawdown_pct=max_drawdown if math.isfinite(max_drawdown) else 0.0,
        calmar_ratio=calmar if calmar is None or math.isfinite(calmar) else None,
        trading_days=len(values),
    )


def rebase_nav(values: list[float]) -> list[float]:
    if not values or values[0] <= 0:
        return []
    return [value / values[0] * 100 for value in values]


def _forward_fill_on_or_before(series: dict[str, float], day: str) -> float | None:
    eligible = [date for date in series if date <= day]
    if not eligible:
        return None
    return float(series[max(eligible)])


def _first_series_date(series: dict[str, float]) -> str | None:
    if not series:
        return None
    return min(series)


def _align_series_to_dates(
    master_dates: list[str],
    primary: dict[str, float],
    secondary: dict[str, float],
) -> tuple[list[str], list[float], list[float]] | None:
    first_primary = _first_series_date(primary)
    if not first_primary:
        return None

    dates: list[str] = []
    primary_values: list[float] = []
    secondary_values: list[float] = []
    secondary_carry: float | None = None

    for day in master_dates:
        if day < first_primary:
            continue
        primary_value = _forward_fill_on_or_before(primary, day)
        if primary_value is None:
            continue
        secondary_eligible = [date for date in secondary if date <= day]
        if secondary_eligible:
            secondary_carry = float(secondary[max(secondary_eligible)])
        if secondary_carry is None:
            continue
        dates.append(day)
        primary_values.append(primary_value)
        secondary_values.append(secondary_carry)

    if len(dates) < 2:
        return None
    return dates, primary_values, secondary_values


def build_candidate_index_performance(
    *,
    market: str,
    index_by_date: dict[str, float],
    benchmark_symbol: str,
    benchmark_closes: dict[str, float],
) -> PortfolioMarketPerformance:
    master_dates = sorted(set(index_by_date) | set(benchmark_closes))
    aligned = _align_series_to_dates(master_dates, index_by_date, benchmark_closes)
    if aligned is None:
        return PortfolioMarketPerformance(
            market=market,
            benchmark_symbol=benchmark_symbol,
        )
    dates, values, benchmark_values = aligned
    portfolio_nav = rebase_nav(values)
    benchmark_nav = rebase_nav(benchmark_values)
    return PortfolioMarketPerformance(
        market=market,
        dates=dates,
        portfolio=portfolio_nav,
        benchmark=benchmark_nav,
        benchmark_symbol=benchmark_symbol,
        stats=compute_risk_stats(portfolio_nav),
    )


def build_market_performance(
    *,
    market: str,
    orders: list[dict],
    initial_capital: float,
    start_date: str,
    ticker_closes: dict[str, dict[str, float]],
    benchmark_symbol: str,
    benchmark_closes: dict[str, float],
    calendar_dates: list[str] | None = None,
) -> PortfolioMarketPerformance:
    from dojoagents.dashboard.services.portfolio_order_execution import (
        _apply_filled_order,
        market_filled_orders,
    )

    if initial_capital <= 0 and not market_filled_orders(orders, market=market):
        return PortfolioMarketPerformance(
            market=market,
            benchmark_symbol=benchmark_symbol,
        )

    market_orders = market_filled_orders(orders, market=market)
    if calendar_dates:
        master_dates = [day for day in calendar_dates if day >= start_date]
    else:
        master_dates = sorted(
            {day for day in benchmark_closes if day >= start_date}
            | {day for closes in ticker_closes.values() for day in closes if day >= start_date}
        )
    if len(master_dates) < 2:
        return PortfolioMarketPerformance(
            market=market,
            benchmark_symbol=benchmark_symbol,
        )

    dates: list[str] = []
    values: list[float] = []
    benchmark_values: list[float] = []
    cash = float(initial_capital)
    positions: dict[str, float] = {}
    order_index = 0

    for day in master_dates:
        while order_index < len(market_orders):
            order = market_orders[order_index]
            fill_date = str(
                order.get("fill_time") or order.get("order_time") or order.get("created_at") or ""
            )[:10]
            if fill_date > day:
                break
            cash, positions = _apply_filled_order(cash, positions, order)
            order_index += 1

        position_value = 0.0
        missing_price = False
        for ticker, shares in positions.items():
            closes = ticker_closes.get(ticker) or {}
            price = _forward_fill_on_or_before(closes, day)
            if price is None:
                missing_price = True
                break
            position_value += shares * price
        if missing_price:
            continue

        benchmark_price = _forward_fill_on_or_before(benchmark_closes, day)
        if benchmark_price is None:
            continue

        dates.append(day)
        values.append(cash + position_value)
        benchmark_values.append(benchmark_price)

    if len(dates) < 2:
        return PortfolioMarketPerformance(
            market=market,
            benchmark_symbol=benchmark_symbol,
        )

    portfolio_nav = rebase_nav(values)
    benchmark_nav = rebase_nav(benchmark_values)
    return PortfolioMarketPerformance(
        market=market,
        dates=dates,
        portfolio=portfolio_nav,
        benchmark=benchmark_nav,
        benchmark_symbol=benchmark_symbol,
        stats=compute_risk_stats(portfolio_nav),
    )
