"""Pure helpers for industry theme-state metrics (breadth / momentum / fundamentals lite)."""

from __future__ import annotations

import math
from typing import Any, Iterable, Mapping, Sequence

import numpy as np
import pandas as pd

from dojoagents.dashboard.services.fin_indicators_utils import (
    comparable_quarter_key,
    natural_comparable_quarter_key,
    prepare_single_quarter_rows,
    quarter_key,
)

MIN_ELIGIBLE_COUNT = 5
VOLUME_LOOKBACK_DAYS = 20
VOLUME_MULTIPLIER = 1.5
HIGH_LOOKBACK_DAYS = 252
MOMENTUM_WINDOWS = (5, 10, 20)
CONFIRMATION_WINDOW_DAYS = 5
STAGE_HINT_RULE = "revenue_lite_v1"
ROLE_FILTER = "primary+secondary"
ACCEL_STABLE_ABS_PP = 5.0
FIN_COVERAGE_MIN = 0.3
# Default rotation board: z(RS) blend (20D-dominant) × breadth confirmation.
ROTATION_RS_WEIGHTS = (0.2, 0.3, 0.5)  # 5d, 10d, 20d
ROTATION_BREADTH_CENTER = 50.0
ROTATION_BREADTH_MULT_MIN = 0.5
ROTATION_BREADTH_MULT_MAX = 1.5
ROTATION_RANK_RULE = "rs_z_blend_20d_dominant_x_breadth_v1"


def _finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return number


def nan_or(value: float | None) -> float:
    return float("nan") if value is None else float(value)


def window_return_pct(levels: Sequence[float], days: int) -> float | None:
    """Match sector precompute window: P[t] / P[t - (days-1) steps in series indexing via len-days]."""
    if days <= 0 or len(levels) < days:
        return None
    start = _finite(levels[-days])
    end = _finite(levels[-1])
    if start is None or end is None or start <= 0:
        return None
    return ((end / start) - 1.0) * 100.0


def window_volatility_pct(daily_returns: Sequence[float], days: int) -> float | None:
    if days <= 1 or len(daily_returns) < days:
        return None
    window = [_finite(value) for value in daily_returns[-days:]]
    clean = [value for value in window if value is not None]
    if len(clean) < max(2, days // 2):
        return None
    std = float(np.std(clean, ddof=1)) if len(clean) > 1 else 0.0
    return std * math.sqrt(days)


def risk_adjusted(return_pct: float | None, volatility_pct: float | None) -> float | None:
    if return_pct is None or volatility_pct is None or volatility_pct <= 0:
        return None
    return return_pct / volatility_pct


def breadth_confirmation_multiplier(breadth_score: float | None) -> float:
    """Map breadth_score (%) into [0.5, 1.5]; missing breadth → neutral 1.0."""
    number = _finite(breadth_score)
    if number is None:
        return 1.0
    center = ROTATION_BREADTH_CENTER if ROTATION_BREADTH_CENTER > 0 else 50.0
    return float(
        min(
            ROTATION_BREADTH_MULT_MAX,
            max(ROTATION_BREADTH_MULT_MIN, number / center),
        )
    )


def _zscore_series(values: pd.Series) -> pd.Series:
    clean = pd.to_numeric(values, errors="coerce")
    std = float(clean.std(ddof=0))
    if not math.isfinite(std) or std <= 0:
        return pd.Series(np.where(clean.notna(), 0.0, np.nan), index=clean.index, dtype=float)
    mean = float(clean.mean())
    return (clean - mean) / std


def rotation_score_frame(
    *,
    relative_strength_5d: pd.Series,
    relative_strength_10d: pd.Series,
    relative_strength_20d: pd.Series,
    breadth_score: pd.Series,
    weights: tuple[float, float, float] = ROTATION_RS_WEIGHTS,
) -> pd.Series:
    """Cross-sectional score: 0.2·z(RS5)+0.3·z(RS10)+0.5·z(RS20) × breadth multiplier.

    Z-scores are taken within the provided series (caller groups by trade_date×market).
    Rows missing any RS component receive NaN.
    """
    w5, w10, w20 = weights
    blend = w5 * _zscore_series(relative_strength_5d) + w10 * _zscore_series(relative_strength_10d) + w20 * _zscore_series(relative_strength_20d)
    mult = breadth_score.map(breadth_confirmation_multiplier)
    return blend * mult


def streak_days(daily_returns: Sequence[float], *, positive: bool) -> int:
    streak = 0
    for value in reversed(daily_returns):
        number = _finite(value)
        if number is None:
            break
        if positive and number > 0:
            streak += 1
            continue
        if not positive and number < 0:
            streak += 1
            continue
        break
    return streak


def dedupe_universe_members(members: pd.DataFrame) -> pd.DataFrame:
    """primary∪secondary, one row per ticker; keep primary when both exist."""
    if members.empty:
        return members
    ordered = members.sort_values(["ticker", "role"]).drop_duplicates(subset=["ticker"], keep="first")
    return ordered.reset_index(drop=True)


def role_counts(members: pd.DataFrame) -> tuple[int, int, int]:
    if members.empty:
        return 0, 0, 0
    primary = int((members["role"] == "primary").sum())
    secondary = int((members["role"] == "secondary").sum())
    deduped = dedupe_universe_members(members)
    return len(deduped), primary, secondary


def compute_breadth_for_day(
    *,
    member_tickers: Sequence[str],
    day_returns: Mapping[str, float | None],
    day_volumes: Mapping[str, float | None],
    avg_volumes: Mapping[str, float | None],
    day_closes: Mapping[str, float | None],
    rolling_highs: Mapping[str, float | None],
    volume_multiplier: float = VOLUME_MULTIPLIER,
) -> dict[str, Any]:
    advancers = decliners = unchanged = 0
    volume_expansion = 0
    new_highs = 0
    sample = 0
    volume_sample = 0
    high_sample = 0
    effective_high_lookbacks: list[int] = []

    for ticker in member_tickers:
        ret = day_returns.get(ticker)
        if ret is None or not math.isfinite(ret):
            continue
        sample += 1
        if ret > 0:
            advancers += 1
        elif ret < 0:
            decliners += 1
        else:
            unchanged += 1

        vol = day_volumes.get(ticker)
        avg = avg_volumes.get(ticker)
        if vol is not None and avg is not None and avg > 0 and math.isfinite(vol) and math.isfinite(avg):
            volume_sample += 1
            if vol > avg * volume_multiplier:
                volume_expansion += 1

        close = day_closes.get(ticker)
        high = rolling_highs.get(ticker)
        lookback = None
        if isinstance(rolling_highs.get(f"{ticker}__lookback"), (int, float)):
            lookback = int(rolling_highs[f"{ticker}__lookback"])  # type: ignore[index]
        if close is not None and high is not None and high > 0 and math.isfinite(close) and math.isfinite(high):
            high_sample += 1
            if lookback is not None:
                effective_high_lookbacks.append(lookback)
            if close >= high:
                new_highs += 1

    advancers_pct = (advancers / sample * 100.0) if sample else None
    volume_pct = (volume_expansion / volume_sample * 100.0) if volume_sample else None
    new_highs_pct = (new_highs / high_sample * 100.0) if high_sample else None

    components = [value for value in (advancers_pct, volume_pct, new_highs_pct) if value is not None]
    breadth_score = (sum(components) / len(components)) if components else None

    return {
        "advancers_pct": nan_or(advancers_pct),
        "volume_expansion_pct": nan_or(volume_pct),
        "new_highs_pct": nan_or(new_highs_pct),
        "breadth_score": nan_or(breadth_score),
        "advancers_count": advancers,
        "decliners_count": decliners,
        "unchanged_count": unchanged,
        "volume_expansion_count": volume_expansion,
        "new_highs_count": new_highs if high_sample else -1,
        "breadth_sample_count": sample,
        "volume_sample_count": volume_sample,
        "high_sample_count": high_sample,
        "high_effective_lookback_days": int(min(effective_high_lookbacks)) if effective_high_lookbacks else 0,
    }


def stage_hint_revenue_lite(
    *,
    revenue_yoy_pct: float | None,
    revenue_accel_pp: float | None,
    revenue_improvers_pct: float | None,
    fin_coverage_ratio: float | None,
    fin_sample_count: int,
) -> str | None:
    if fin_sample_count < MIN_ELIGIBLE_COUNT:
        return None
    if fin_coverage_ratio is None or fin_coverage_ratio < FIN_COVERAGE_MIN:
        return None
    if revenue_yoy_pct is None or revenue_improvers_pct is None:
        return None

    accel = revenue_accel_pp if revenue_accel_pp is not None else 0.0
    if revenue_yoy_pct > 0 and accel > 0 and revenue_improvers_pct >= 50.0:
        return "expanding"
    if revenue_yoy_pct > 0 and abs(accel) < ACCEL_STABLE_ABS_PP and revenue_improvers_pct >= 50.0:
        return "stable"
    if revenue_yoy_pct < 0 or (revenue_improvers_pct < 50.0 and revenue_yoy_pct <= 0):
        return "contracting"
    return "mixed"


def _metric_from_row(row: Mapping[str, Any], key: str) -> float | None:
    return _finite(row.get(key))


def _as_fin_row_dict(row: Any) -> dict[str, Any]:
    if isinstance(row, Mapping):
        return dict(row)
    if hasattr(row, "model_dump"):
        return dict(row.model_dump())
    if hasattr(row, "dict"):
        return dict(row.dict())
    if hasattr(row, "__dict__"):
        return {k: v for k, v in vars(row).items() if not k.startswith("_")}
    raise TypeError(f"Unsupported fin row type: {type(row)!r}")


def extract_quarter_metrics(rows: Iterable[dict[str, Any]], market: str) -> dict[str, dict[str, float]]:
    """Map natural-calendar quarter_key -> {revenue, net_profit} using single-quarter values.

    Fiscal labels are remapped via period-end dates so off-calendar FYE names
    (e.g. APD fiscal 2026Q2 ending 2026-03-31) align with calendar peers.
    """
    prepared = prepare_single_quarter_rows([_as_fin_row_dict(row) for row in rows], market)
    out: dict[str, dict[str, float]] = {}
    for row in prepared:
        meta = natural_comparable_quarter_key(row)
        if meta is None:
            continue
        year, quarter = meta
        key = quarter_key(year, quarter)
        revenue = _metric_from_row(row, "total_operating_revenue")
        profit = _metric_from_row(row, "net_profit_attr_parent")
        if revenue is None and profit is None:
            continue
        fiscal = comparable_quarter_key(row)
        slot = out.setdefault(key, {})
        if revenue is not None:
            slot["revenue"] = revenue
        if profit is not None:
            slot["net_profit"] = profit
        name = str(row.get("report_period_name") or "").strip()
        if name:
            slot["report_period_name"] = name  # type: ignore[assignment]
        if fiscal is not None:
            slot["fiscal_quarter_key"] = quarter_key(fiscal[0], fiscal[1])  # type: ignore[assignment]
        period_end = str(row.get("report_date") or "").strip()
        if period_end:
            slot["period_end"] = period_end[:10]  # type: ignore[assignment]
    return out


def _prior_year_key(qkey: str) -> str | None:
    try:
        year_s, quarter = qkey.split(":", 1)
        return f"{int(year_s) - 1}:{quarter}"
    except (TypeError, ValueError):
        return None


def _prior_quarter_key(qkey: str) -> str | None:
    try:
        year_s, quarter = qkey.split(":", 1)
        year = int(year_s)
    except (TypeError, ValueError):
        return None
    order = ("q1", "q2", "q3", "q4")
    if quarter not in order:
        return None
    idx = order.index(quarter)
    if idx == 0:
        return f"{year - 1}:q4"
    return f"{year}:{order[idx - 1]}"


def _revenue_pair_count(
    ticker_quarters: Mapping[str, Mapping[str, Mapping[str, float]]],
    report_period_key: str,
) -> int:
    prior_year = _prior_year_key(report_period_key)
    if prior_year is None:
        return 0
    pairs = 0
    for quarters in ticker_quarters.values():
        cur = quarters.get(report_period_key) or {}
        py = quarters.get(prior_year) or {}
        cur_rev = _finite(cur.get("revenue"))
        py_rev = _finite(py.get("revenue"))
        if cur_rev is not None and py_rev is not None and py_rev != 0:
            pairs += 1
    return pairs


def select_report_period_key(
    ticker_quarters: Mapping[str, Mapping[str, Mapping[str, float]]],
) -> str | None:
    """Pick the natural quarter with best YoY coverage (not the newest fiscal label)."""
    candidates = {str(key) for quarters in ticker_quarters.values() for key in quarters.keys()}
    if not candidates:
        return None

    scored: list[tuple[int, str]] = [(_revenue_pair_count(ticker_quarters, key), key) for key in candidates]
    meeting = [(pairs, key) for pairs, key in scored if pairs >= MIN_ELIGIBLE_COUNT]
    pool = meeting if meeting else scored
    # Max pairs, then newest natural quarter key.
    pool.sort(key=lambda item: (item[0], item[1]))
    return pool[-1][1]


def list_report_period_keys(
    ticker_quarters: Mapping[str, Mapping[str, Mapping[str, float]]],
    *,
    max_periods: int = 8,
) -> list[str]:
    """Return up to ``max_periods`` coverage-qualified quarter keys, newest-first."""
    candidates = {str(key) for quarters in ticker_quarters.values() for key in quarters.keys()}
    if not candidates:
        return []

    scored: list[tuple[int, str]] = [(_revenue_pair_count(ticker_quarters, key), key) for key in candidates]
    meeting = [(pairs, key) for pairs, key in scored if pairs >= MIN_ELIGIBLE_COUNT]
    pool = meeting if meeting else scored
    # Newest natural quarter first (string key sorts year:qN correctly for q1..q4).
    pool.sort(key=lambda item: item[1], reverse=True)
    keys = [key for _pairs, key in pool]
    if max_periods > 0:
        keys = keys[:max_periods]
    return keys


def aggregate_fundamentals_lite(
    ticker_quarters: Mapping[str, Mapping[str, Mapping[str, float]]],
    *,
    report_period_key: str | None = None,
) -> dict[str, Any]:
    """Aggregate industry revenue/profit lite metrics across tickers.

    ``ticker_quarters``: ticker -> natural quarter_key -> {revenue, net_profit, ...}
    """
    empty = {
        "fin_status": "insufficient_fundamentals",
        "fin_report_period": "",
        "fin_prior_year_period": "",
        "fin_sample_count": 0,
        "fin_coverage_ratio": float("nan"),
        "industry_revenue": float("nan"),
        "industry_revenue_prior_year": float("nan"),
        "industry_revenue_yoy_pct": float("nan"),
        "industry_revenue_yoy_prior_pct": float("nan"),
        "industry_revenue_accel_pp": float("nan"),
        "revenue_improvers_count": 0,
        "revenue_improvers_pct": float("nan"),
        "industry_net_profit": float("nan"),
        "industry_net_profit_yoy_pct": float("nan"),
        "profit_improvers_count": 0,
        "profit_improvers_pct": float("nan"),
        "industry_net_margin_pct": float("nan"),
        "industry_net_margin_change_pp": float("nan"),
        "stage_hint": "",
        "stage_hint_rule": STAGE_HINT_RULE,
        "report_period_key": "",
    }
    if not ticker_quarters:
        return empty

    if report_period_key is None:
        report_period_key = select_report_period_key(ticker_quarters)
        if report_period_key is None:
            return empty

    prior_year = _prior_year_key(report_period_key)
    prior_quarter = _prior_quarter_key(report_period_key)
    prior_quarter_prior_year = _prior_year_key(prior_quarter) if prior_quarter else None
    if prior_year is None:
        return empty

    rev_now = 0.0
    rev_py = 0.0
    rev_pairs = 0
    revenue_improvers = 0
    profit_now = 0.0
    profit_py = 0.0
    profit_pairs = 0
    profit_improvers = 0
    rev_prior_q = 0.0
    rev_prior_q_py = 0.0
    prior_q_pairs = 0

    for quarters in ticker_quarters.values():
        cur = quarters.get(report_period_key) or {}
        py = quarters.get(prior_year) or {}
        cur_rev = _finite(cur.get("revenue"))
        py_rev = _finite(py.get("revenue"))
        if cur_rev is not None and py_rev is not None and py_rev != 0:
            rev_now += cur_rev
            rev_py += py_rev
            rev_pairs += 1
            if cur_rev / py_rev - 1.0 > 0:
                revenue_improvers += 1

        cur_profit = _finite(cur.get("net_profit"))
        py_profit = _finite(py.get("net_profit"))
        if cur_profit is not None and py_profit is not None and py_profit != 0:
            profit_now += cur_profit
            profit_py += py_profit
            profit_pairs += 1
            if cur_profit / py_profit - 1.0 > 0:
                profit_improvers += 1

        if prior_quarter and prior_quarter_prior_year:
            pq = quarters.get(prior_quarter) or {}
            pq_py = quarters.get(prior_quarter_prior_year) or {}
            pq_rev = _finite(pq.get("revenue"))
            pq_py_rev = _finite(pq_py.get("revenue"))
            if pq_rev is not None and pq_py_rev is not None and pq_py_rev != 0:
                rev_prior_q += pq_rev
                rev_prior_q_py += pq_py_rev
                prior_q_pairs += 1

    if rev_pairs < MIN_ELIGIBLE_COUNT:
        out = dict(empty)
        out["fin_sample_count"] = rev_pairs
        out["report_period_key"] = report_period_key
        out["fin_report_period"] = report_period_key
        out["fin_prior_year_period"] = prior_year
        return out

    revenue_yoy = ((rev_now / rev_py) - 1.0) * 100.0 if rev_py else None
    prior_yoy = ((rev_prior_q / rev_prior_q_py) - 1.0) * 100.0 if prior_q_pairs >= MIN_ELIGIBLE_COUNT and rev_prior_q_py else None
    accel = (revenue_yoy - prior_yoy) if revenue_yoy is not None and prior_yoy is not None else None
    improvers_pct = revenue_improvers / rev_pairs * 100.0
    profit_yoy = ((profit_now / profit_py) - 1.0) * 100.0 if profit_pairs >= MIN_ELIGIBLE_COUNT and profit_py else None
    profit_improvers_pct = (profit_improvers / profit_pairs * 100.0) if profit_pairs else None
    margin = (profit_now / rev_now * 100.0) if rev_now and profit_pairs >= MIN_ELIGIBLE_COUNT else None
    margin_py = (profit_py / rev_py * 100.0) if rev_py and profit_pairs >= MIN_ELIGIBLE_COUNT else None
    margin_change = (margin - margin_py) if margin is not None and margin_py is not None else None

    eligible_proxy = max(len(ticker_quarters), rev_pairs)
    coverage = rev_pairs / eligible_proxy if eligible_proxy else None
    hint = stage_hint_revenue_lite(
        revenue_yoy_pct=revenue_yoy,
        revenue_accel_pp=accel,
        revenue_improvers_pct=improvers_pct,
        fin_coverage_ratio=coverage,
        fin_sample_count=rev_pairs,
    )

    return {
        "fin_status": "ok",
        "fin_report_period": report_period_key,
        "fin_prior_year_period": prior_year,
        "fin_sample_count": rev_pairs,
        "fin_coverage_ratio": nan_or(coverage),
        "industry_revenue": nan_or(rev_now),
        "industry_revenue_prior_year": nan_or(rev_py),
        "industry_revenue_yoy_pct": nan_or(revenue_yoy),
        "industry_revenue_yoy_prior_pct": nan_or(prior_yoy),
        "industry_revenue_accel_pp": nan_or(accel),
        "revenue_improvers_count": revenue_improvers,
        "revenue_improvers_pct": nan_or(improvers_pct),
        "industry_net_profit": nan_or(profit_now if profit_pairs else None),
        "industry_net_profit_yoy_pct": nan_or(profit_yoy),
        "profit_improvers_count": profit_improvers if profit_pairs else 0,
        "profit_improvers_pct": nan_or(profit_improvers_pct),
        "industry_net_margin_pct": nan_or(margin),
        "industry_net_margin_change_pp": nan_or(margin_change),
        "stage_hint": hint or "",
        "stage_hint_rule": STAGE_HINT_RULE,
        "report_period_key": report_period_key,
    }
