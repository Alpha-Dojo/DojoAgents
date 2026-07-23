"""Phase B+: medium/long horizon sector metrics (60D/120D/252D + multi-quarter fin + PE ranks)."""

from __future__ import annotations

import math
from typing import Any, Sequence

import numpy as np
import pandas as pd

from dojoagents.dashboard.services.theme_state_metrics import (
    nan_or,
    risk_adjusted,
    window_return_pct,
    window_volatility_pct,
)

HORIZON_WINDOWS = (60, 120, 252)
MAX_FUNDAMENTAL_PERIODS = 8
SECTOR_HORIZON_METRICS_FILE = "sector_horizon_metrics.parquet"

SECTOR_HORIZON_METRICS_COLUMNS = [
    "trade_date",
    "market",
    "scope",
    "level1_id",
    "level2_id",
    "level3_id",
    "link_key",
    "member_count",
    "index_level",
    "weighted_pe",
    "return_60d_pct",
    "return_120d_pct",
    "return_252d_pct",
    "market_return_60d_pct",
    "market_return_120d_pct",
    "market_return_252d_pct",
    "relative_strength_60d",
    "relative_strength_120d",
    "relative_strength_252d",
    "volatility_60d_pct",
    "volatility_120d_pct",
    "volatility_252d_pct",
    "max_drawdown_60d_pct",
    "max_drawdown_120d_pct",
    "max_drawdown_252d_pct",
    "risk_adjusted_60d",
    "risk_adjusted_120d",
    "risk_adjusted_252d",
    "pe_percentile_cross_section",
    "pe_percentile_trailing_252d",
    "fin_status",
    "fin_report_period",
    "fin_quarters_available",
    "industry_revenue_yoy_pct",
    "industry_net_profit_yoy_pct",
    "industry_net_margin_pct",
    "revenue_yoy_positive_streak",
    "revenue_yoy_avg_4q_pct",
    "stage_hint",
    "row_status",
]


def _finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return number


def max_drawdown_pct(levels: Sequence[float]) -> float | None:
    """Peak-to-trough max drawdown over ``levels`` (%)."""
    clean = [_finite(level) for level in levels]
    clean = [level for level in clean if level is not None and level > 0]
    if len(clean) < 2:
        return None
    peak = clean[0]
    worst = 0.0
    for level in clean[1:]:
        peak = max(peak, level)
        drawdown = (level / peak - 1.0) * 100.0
        if drawdown < worst:
            worst = drawdown
    return worst


def _compound_return_pct(daily_returns: Sequence[float | None], days: int) -> float | None:
    if days <= 0 or len(daily_returns) < days:
        return None
    window = daily_returns[-days:]
    product = 1.0
    used = 0
    for raw in window:
        value = _finite(raw)
        if value is None:
            continue
        product *= 1.0 + value / 100.0
        used += 1
    if used < max(2, days // 2):
        return None
    return (product - 1.0) * 100.0


def _percentile_rank(values: Sequence[float | None], target: float | None) -> float | None:
    if target is None or not math.isfinite(target):
        return None
    clean = [_finite(value) for value in values]
    clean = [value for value in clean if value is not None and value > 0]
    if len(clean) < 2:
        return None
    arr = np.asarray(clean, dtype=float)
    # Fraction of peers strictly below target (0–100).
    return float(np.mean(arr < target) * 100.0)


def _trailing_percentile(history: Sequence[float | None], target: float | None) -> float | None:
    return _percentile_rank(history, target)


def _quarter_sort_key(period_key: str) -> tuple[int, int]:
    try:
        year_s, quarter = str(period_key).split(":", 1)
        order = {"q1": 1, "q2": 2, "q3": 3, "q4": 4}
        return int(year_s), int(order.get(quarter.lower(), 0))
    except (TypeError, ValueError):
        return (-1, -1)


def summarize_multi_quarter_fundamentals(period_rows: pd.DataFrame) -> dict[str, Any]:
    """Collapse multi-period fundamentals_period rows for one theme into horizon fields."""
    empty = {
        "fin_status": "insufficient_fundamentals",
        "fin_report_period": "",
        "fin_quarters_available": 0,
        "industry_revenue_yoy_pct": float("nan"),
        "industry_net_profit_yoy_pct": float("nan"),
        "industry_net_margin_pct": float("nan"),
        "revenue_yoy_positive_streak": 0,
        "revenue_yoy_avg_4q_pct": float("nan"),
        "stage_hint": "",
    }
    if period_rows is None or period_rows.empty:
        return empty

    rows = period_rows.copy()
    rows["_sort"] = rows["report_period_key"].map(_quarter_sort_key)
    rows = rows.sort_values("_sort", ascending=False)
    ok_rows = rows[rows["fin_status"].astype(str) == "ok"]
    if ok_rows.empty:
        latest = rows.iloc[0]
        out = dict(empty)
        out["fin_status"] = str(latest.get("fin_status") or "insufficient_fundamentals")
        out["fin_report_period"] = str(latest.get("fin_report_period") or latest.get("report_period_key") or "")
        out["fin_quarters_available"] = int(len(rows))
        return out

    latest = ok_rows.iloc[0]
    yoy_series: list[float] = []
    for value in ok_rows["industry_revenue_yoy_pct"].tolist():
        number = _finite(value)
        if number is not None:
            yoy_series.append(number)

    streak = 0
    for number in yoy_series:
        if number > 0:
            streak += 1
        else:
            break

    avg_4q = float(np.mean(yoy_series[:4])) if yoy_series else None
    return {
        "fin_status": "ok",
        "fin_report_period": str(latest.get("fin_report_period") or latest.get("report_period_key") or ""),
        "fin_quarters_available": int(len(ok_rows)),
        "industry_revenue_yoy_pct": nan_or(_finite(latest.get("industry_revenue_yoy_pct"))),
        "industry_net_profit_yoy_pct": nan_or(_finite(latest.get("industry_net_profit_yoy_pct"))),
        "industry_net_margin_pct": nan_or(_finite(latest.get("industry_net_margin_pct"))),
        "revenue_yoy_positive_streak": int(streak),
        "revenue_yoy_avg_4q_pct": nan_or(avg_4q),
        "stage_hint": str(latest.get("stage_hint") or ""),
    }


def compute_sector_horizon_metrics_frame(
    *,
    sector_daily: pd.DataFrame,
    benchmark_daily: pd.DataFrame | None = None,
    fundamentals_period: pd.DataFrame | None = None,
    link_key_by_level3: dict[str, str] | None = None,
    scope: str = "L3",
) -> pd.DataFrame:
    """Build daily L3 horizon metrics from Phase A sector_daily (+ optional bench/fin)."""
    if sector_daily is None or sector_daily.empty:
        return pd.DataFrame(columns=SECTOR_HORIZON_METRICS_COLUMNS)

    frame = sector_daily.copy()
    for col in ("market", "scope", "level1_id", "level2_id", "level3_id", "trade_date"):
        if col in frame.columns:
            frame[col] = frame[col].astype(str)
    frame = frame[frame["scope"] == scope].copy()
    if frame.empty:
        return pd.DataFrame(columns=SECTOR_HORIZON_METRICS_COLUMNS)

    link_map = link_key_by_level3 or {}
    bench_by_market: dict[str, pd.DataFrame] = {}
    if benchmark_daily is not None and not benchmark_daily.empty:
        bench = benchmark_daily.copy()
        for col in ("market", "trade_date"):
            if col in bench.columns:
                bench[col] = bench[col].astype(str)
        for market, group in bench.groupby("market", sort=False):
            bench_by_market[str(market)] = group.sort_values("trade_date").reset_index(drop=True)

    fin_by_theme: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    if fundamentals_period is not None and not fundamentals_period.empty:
        fin = fundamentals_period.copy()
        for col in ("market", "level1_id", "level2_id", "level3_id"):
            if col in fin.columns:
                fin[col] = fin[col].astype(str)
        for key, group in fin.groupby(["market", "level1_id", "level2_id", "level3_id"], sort=False):
            fin_by_theme[(str(key[0]), str(key[1]), str(key[2]), str(key[3]))] = summarize_multi_quarter_fundamentals(group)

    rows: list[dict[str, Any]] = []
    group_cols = ["market", "level1_id", "level2_id", "level3_id"]
    for key, group in frame.groupby(group_cols, sort=True):
        market, l1, l2, l3 = (str(key[0]), str(key[1]), str(key[2]), str(key[3]))
        series = group.sort_values("trade_date").reset_index(drop=True)
        levels = [_finite(value) if _finite(value) is not None else float("nan") for value in series["index_level"].tolist()]
        daily_rets = [_finite(value) if _finite(value) is not None else float("nan") for value in series["daily_return_pct"].tolist()]
        pe_hist = [_finite(value) for value in series["weighted_pe"].tolist()]
        dates = series["trade_date"].astype(str).tolist()

        bench = bench_by_market.get(market)
        bench_rets: list[float | None] = []
        if bench is not None and not bench.empty:
            bench_map = {str(row.trade_date): _finite(row.daily_return_pct) for row in bench.itertuples(index=False)}
            bench_rets = [bench_map.get(day) for day in dates]

        fin_payload = fin_by_theme.get((market, l1, l2, l3)) or summarize_multi_quarter_fundamentals(pd.DataFrame())
        link_key = link_map.get(l3) or str(series.iloc[0].get("link_key") or l3)

        for idx in range(len(series)):
            end = idx + 1
            level_window = levels[:end]
            ret_window = daily_rets[:end]
            pe_window = pe_hist[:end]
            bench_window = bench_rets[:end] if bench_rets else []

            metrics: dict[str, Any] = {
                "trade_date": dates[idx],
                "market": market,
                "scope": scope,
                "level1_id": l1,
                "level2_id": l2,
                "level3_id": l3,
                "link_key": link_key,
                "member_count": int(series.iloc[idx].get("member_count") or 0),
                "index_level": nan_or(_finite(levels[idx])),
                "weighted_pe": nan_or(pe_hist[idx]),
            }

            available_windows = 0
            for days in HORIZON_WINDOWS:
                suffix = f"{days}d"
                sector_ret = window_return_pct(level_window, days)
                vol = window_volatility_pct(ret_window, days)
                dd = max_drawdown_pct(level_window[-days:]) if end >= days else None
                market_ret = _compound_return_pct(bench_window, days) if bench_window else None
                rs = sector_ret - market_ret if sector_ret is not None and market_ret is not None else None
                metrics[f"return_{suffix}_pct"] = nan_or(sector_ret)
                metrics[f"market_return_{suffix}_pct"] = nan_or(market_ret)
                metrics[f"relative_strength_{suffix}"] = nan_or(rs)
                metrics[f"volatility_{suffix}_pct"] = nan_or(vol)
                metrics[f"max_drawdown_{suffix}_pct"] = nan_or(dd)
                metrics[f"risk_adjusted_{suffix}"] = nan_or(risk_adjusted(sector_ret, vol))
                if sector_ret is not None:
                    available_windows += 1

            trailing_pe = _trailing_percentile(pe_window[-252:], pe_hist[idx])
            metrics["pe_percentile_trailing_252d"] = nan_or(trailing_pe)
            metrics["pe_percentile_cross_section"] = float("nan")  # filled later
            metrics.update(fin_payload)

            if available_windows <= 0:
                metrics["row_status"] = "insufficient_history"
            elif available_windows < len(HORIZON_WINDOWS):
                metrics["row_status"] = "partial"
            else:
                metrics["row_status"] = "ok"
            rows.append(metrics)

    if not rows:
        return pd.DataFrame(columns=SECTOR_HORIZON_METRICS_COLUMNS)

    out = pd.DataFrame(rows)

    # Cross-section PE percentile within market×trade_date among L3 peers.
    def _fill_cross(group: pd.DataFrame) -> pd.DataFrame:
        pe_values = group["weighted_pe"].tolist()
        ranks = [_percentile_rank(pe_values, _finite(value)) for value in pe_values]
        group = group.copy()
        group["pe_percentile_cross_section"] = [nan_or(rank) for rank in ranks]
        return group

    filled_parts = [_fill_cross(group) for _, group in out.groupby(["market", "trade_date"], sort=False)]
    out = pd.concat(filled_parts, ignore_index=True) if filled_parts else out
    out = out[SECTOR_HORIZON_METRICS_COLUMNS].sort_values(["trade_date", "market", "level1_id", "level2_id", "level3_id"]).reset_index(drop=True)
    return out
