from __future__ import annotations

import math
import statistics

from dojoagents.dashboard.schemas.portfolio import (
    PortfolioMarketPerformance,
    PortfolioRiskStats,
)
from dojoagents.dashboard.services.market_trading_calendar import trading_days_for_market

TRADING_DAYS_YEAR = 252


def _is_valid_nav(value: float) -> bool:
    return math.isfinite(value) and value > 0


def compute_risk_stats(
    nav_by_date: dict[str, float],
    *,
    trading_days: list[str],
) -> PortfolioRiskStats:
    """Risk metrics on a market trading calendar with forward-filled NAV gaps."""
    if not trading_days:
        return PortfolioRiskStats()

    filled_nav: list[float] = []
    last_good: float | None = None
    for day in trading_days:
        raw = nav_by_date.get(day)
        if raw is not None and _is_valid_nav(float(raw)):
            last_good = float(raw)
        if last_good is None:
            continue
        filled_nav.append(last_good)

    if not filled_nav:
        return PortfolioRiskStats()

    start_value = filled_nav[0]
    end_value = filled_nav[-1]
    cumulative = (end_value / start_value - 1) * 100 if start_value else None

    returns = [
        current / previous - 1
        for previous, current in zip(filled_nav, filled_nav[1:])
        if previous > 0
    ]

    volatility: float | None = None
    sharpe: float | None = None
    if len(returns) >= 2:
        daily_vol = statistics.pstdev(returns)
        if daily_vol > 0:
            volatility = daily_vol * math.sqrt(TRADING_DAYS_YEAR) * 100
            sharpe = statistics.fmean(returns) / daily_vol * math.sqrt(TRADING_DAYS_YEAR)
        else:
            volatility = 0.0
    elif len(returns) == 1:
        volatility = 0.0

    peak = filled_nav[0]
    max_drawdown = 0.0
    for value in filled_nav:
        peak = max(peak, value)
        drawdown = (value / peak - 1) * 100
        max_drawdown = min(max_drawdown, drawdown)

    trading_day_count = len(filled_nav)
    calmar: float | None = None
    if trading_day_count > 1 and max_drawdown < 0:
        annualized = ((end_value / start_value) ** (TRADING_DAYS_YEAR / (trading_day_count - 1)) - 1) * 100
        calmar = annualized / abs(max_drawdown)
    return PortfolioRiskStats(
        cumulative_return_pct=cumulative if cumulative is None or math.isfinite(cumulative) else None,
        volatility_pct=volatility if volatility is None or math.isfinite(volatility) else None,
        sharpe_ratio=sharpe if sharpe is None or math.isfinite(sharpe) else None,
        max_drawdown_pct=max_drawdown if math.isfinite(max_drawdown) else 0.0,
        calmar_ratio=calmar if calmar is None or math.isfinite(calmar) else None,
        trading_days=trading_day_count,
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


def _resolve_end_date(
    *,
    start_date: str,
    benchmark_closes: dict[str, float],
    ticker_closes: dict[str, dict[str, float]],
    calendar_dates: list[str] | None,
) -> str | None:
    end_candidates = [day for day in benchmark_closes if day >= start_date]
    for closes in ticker_closes.values():
        end_candidates.extend(day for day in closes if day >= start_date)
    if calendar_dates:
        end_candidates.extend(day for day in calendar_dates if day >= start_date)
    if not end_candidates:
        return None
    return max(end_candidates)


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
    nav_by_date = {day: value for day, value in zip(dates, values)}
    stats_trading_days = trading_days_for_market(market, dates[0], dates[-1])
    return PortfolioMarketPerformance(
        market=market,
        dates=dates,
        portfolio=portfolio_nav,
        benchmark=benchmark_nav,
        benchmark_symbol=benchmark_symbol,
        stats=compute_risk_stats(nav_by_date, trading_days=stats_trading_days),
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
    end_date = _resolve_end_date(
        start_date=start_date,
        benchmark_closes=benchmark_closes,
        ticker_closes=ticker_closes,
        calendar_dates=calendar_dates,
    )
    if end_date is None:
        return PortfolioMarketPerformance(
            market=market,
            benchmark_symbol=benchmark_symbol,
        )

    if calendar_dates:
        chart_dates = {day for day in calendar_dates if day >= start_date}
    else:
        chart_dates = {day for day in benchmark_closes if day >= start_date} | {
            day for closes in ticker_closes.values() for day in closes if day >= start_date
        }

    trading_days = trading_days_for_market(market, start_date, end_date)
    if len(trading_days) < 2:
        return PortfolioMarketPerformance(
            market=market,
            benchmark_symbol=benchmark_symbol,
        )

    dates: list[str] = []
    values: list[float] = []
    benchmark_values: list[float] = []
    nav_by_date: dict[str, float] = {}
    cash = float(initial_capital)
    positions: dict[str, float] = {}
    order_index = 0

    for day in trading_days:
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

        nav = cash + position_value
        nav_by_date[day] = nav
        if day not in chart_dates:
            continue

        dates.append(day)
        values.append(nav)
        benchmark_values.append(benchmark_price)

    if len(dates) < 2 or not nav_by_date:
        return PortfolioMarketPerformance(
            market=market,
            benchmark_symbol=benchmark_symbol,
        )

    portfolio_nav = rebase_nav(values)
    benchmark_nav = rebase_nav(benchmark_values)
    stats_start = min(nav_by_date)
    stats_trading_days = [day for day in trading_days if day >= stats_start]
    return PortfolioMarketPerformance(
        market=market,
        dates=dates,
        portfolio=portfolio_nav,
        benchmark=benchmark_nav,
        benchmark_symbol=benchmark_symbol,
        stats=compute_risk_stats(nav_by_date, trading_days=stats_trading_days),
    )
