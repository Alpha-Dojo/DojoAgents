"""Ticker-level short/mid alpha factors from ticker_daily + constituents + benchmarks."""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd

TICKER_ALPHA_FACTORS_RULE = "ticker_alpha_factors_v1"
TICKER_ALPHA_FACTORS_FILE = "ticker_alpha_factors_daily.parquet"

SHORT_WINDOWS = (5, 10, 20)
MID_WINDOWS = (60, 120, 252)

# Embed recent returns — store OK, avoid as same-day labels.
RESEARCH_ONLY_LEAKAGE_RISK = frozenset(
    {
        "s_mom_ret_5d",
        "s_mom_ret_10d",
        "s_mom_riskadj_5d",
        "s_mom_riskadj_10d",
        "s_mom_reversal_1d",
    }
)

TICKER_ALPHA_FACTORS_COLUMNS = [
    # keys
    "trade_date",
    "market",
    "ticker",
    # primary sector attachment (for joining sector factors)
    "level1_id",
    "level2_id",
    "level3_id",
    "role",
    # meta
    "factor_universe_size",
    "factor_rule",
    "row_status",
    # ---- short ----
    "s_mom_ret_5d",  # research_only / leakage risk
    "s_mom_ret_10d",  # research_only / leakage risk
    "s_mom_ret_20d",
    "s_mom_riskadj_5d",  # research_only / leakage risk
    "s_mom_riskadj_10d",  # research_only / leakage risk
    "s_mom_riskadj_20d",
    "s_risk_vol_20d",
    "s_mom_up_streak",
    "s_mom_down_streak",
    "s_mom_reversal_1d",  # research_only / leakage risk (= -daily_return)
    "s_rs_5d",
    "s_rs_10d",
    "s_rs_20d",
    "s_rs_vs_sector_20d",
    "s_tech_dist_ma20",
    "s_size_log_cap",
    "s_val_pe",
    "s_val_pe_cheap_cs",
    # ---- mid ----
    "m_mom_ret_60d",
    "m_mom_ret_120d",
    "m_mom_ret_252d",
    "m_mom_riskadj_60d",
    "m_mom_riskadj_120d",
    "m_mom_riskadj_252d",
    "m_risk_vol_60d",
    "m_risk_vol_120d",
    "m_risk_vol_252d",
    "m_risk_dd_from_peak_60d",
    "m_risk_dd_from_peak_120d",
    "m_risk_dd_from_peak_252d",
    "m_rs_60d",
    "m_rs_120d",
    "m_rs_252d",
    "m_rs_vs_sector_60d",
    "m_rs_vs_sector_120d",
    "m_tech_dist_ma60",
    "m_tech_dist_ma120",
    "m_size_log_cap",
    "m_val_pe",
    "m_val_pe_cheap_cs",
]


def _finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return number


def ticker_factor_dictionary() -> list[dict[str, Any]]:
    rows = [
        ("s_mom_ret_5d", "short", "5D compound return (leakage risk)"),
        ("s_mom_ret_10d", "short", "10D compound return (leakage risk)"),
        ("s_mom_ret_20d", "short", "20D compound return"),
        ("s_mom_riskadj_5d", "short", "5D risk-adjusted return (leakage risk)"),
        ("s_mom_riskadj_10d", "short", "10D risk-adjusted return (leakage risk)"),
        ("s_mom_riskadj_20d", "short", "20D risk-adjusted return"),
        ("s_risk_vol_20d", "short", "20D realized volatility"),
        ("s_mom_up_streak", "short", "Consecutive up days"),
        ("s_mom_down_streak", "short", "Consecutive down days"),
        ("s_mom_reversal_1d", "short", "Negative 1D return (leakage risk)"),
        ("s_rs_5d", "short", "Return minus market benchmark 5D"),
        ("s_rs_10d", "short", "Return minus market benchmark 10D"),
        ("s_rs_20d", "short", "Return minus market benchmark 20D"),
        ("s_rs_vs_sector_20d", "short", "Return minus primary L3 sector 20D"),
        ("s_tech_dist_ma20", "short", "Close / MA20 - 1"),
        ("s_size_log_cap", "short", "log(market_cap) snapshot"),
        ("s_val_pe", "short", "PE snapshot"),
        ("s_val_pe_cheap_cs", "short", "100 - market CS PE percentile"),
        ("m_mom_ret_60d", "mid", "60D compound return"),
        ("m_mom_ret_120d", "mid", "120D compound return"),
        ("m_mom_ret_252d", "mid", "252D compound return"),
        ("m_mom_riskadj_60d", "mid", "60D risk-adjusted return"),
        ("m_mom_riskadj_120d", "mid", "120D risk-adjusted return"),
        ("m_mom_riskadj_252d", "mid", "252D risk-adjusted return"),
        ("m_risk_vol_60d", "mid", "60D volatility"),
        ("m_risk_vol_120d", "mid", "120D volatility"),
        ("m_risk_vol_252d", "mid", "252D volatility"),
        ("m_risk_dd_from_peak_60d", "mid", "Drawdown from 60D peak"),
        ("m_risk_dd_from_peak_120d", "mid", "Drawdown from 120D peak"),
        ("m_risk_dd_from_peak_252d", "mid", "Drawdown from 252D peak"),
        ("m_rs_60d", "mid", "Return minus market 60D"),
        ("m_rs_120d", "mid", "Return minus market 120D"),
        ("m_rs_252d", "mid", "Return minus market 252D"),
        ("m_rs_vs_sector_60d", "mid", "Return minus primary L3 sector 60D"),
        ("m_rs_vs_sector_120d", "mid", "Return minus primary L3 sector 120D"),
        ("m_tech_dist_ma60", "mid", "Close / MA60 - 1"),
        ("m_tech_dist_ma120", "mid", "Close / MA120 - 1"),
        ("m_size_log_cap", "mid", "log(market_cap) snapshot"),
        ("m_val_pe", "mid", "PE snapshot"),
        ("m_val_pe_cheap_cs", "mid", "100 - market CS PE percentile"),
    ]
    return [
        {
            "name": name,
            "horizon": horizon,
            "description": desc,
            "research_only_leakage_risk": name in RESEARCH_ONLY_LEAKAGE_RISK,
        }
        for name, horizon, desc in rows
    ]


def _primary_constituent_map(constituents: pd.DataFrame) -> pd.DataFrame:
    """One sector assignment per ticker: prefer primary role, then largest cap."""
    if constituents is None or constituents.empty:
        return pd.DataFrame(columns=["market", "ticker", "level1_id", "level2_id", "level3_id", "role", "market_cap", "pe"])
    frame = constituents.copy()
    for col in ("market", "ticker", "level1_id", "level2_id", "level3_id", "role"):
        if col in frame.columns:
            frame[col] = frame[col].astype(str)
    frame["market_cap"] = pd.to_numeric(frame.get("market_cap"), errors="coerce")
    frame["pe"] = pd.to_numeric(frame.get("pe"), errors="coerce")
    frame["role_rank"] = np.where(frame["role"].str.lower() == "primary", 0, 1)
    frame = frame.sort_values(
        ["market", "ticker", "role_rank", "market_cap"],
        ascending=[True, True, True, False],
    )
    return frame.drop_duplicates(subset=["market", "ticker"], keep="first")[["market", "ticker", "level1_id", "level2_id", "level3_id", "role", "market_cap", "pe"]].reset_index(
        drop=True
    )


def _compound_return_from_daily(ret_pct: pd.Series, window: int) -> pd.Series:
    r = pd.to_numeric(ret_pct, errors="coerce") / 100.0
    # log-sum-exp for numerical stability
    log_r = np.log1p(r.clip(lower=-0.999999))
    return (np.expm1(log_r.rolling(window, min_periods=max(2, window // 2)).sum())) * 100.0


def _rolling_vol(ret_pct: pd.Series, window: int) -> pd.Series:
    r = pd.to_numeric(ret_pct, errors="coerce")
    return r.rolling(window, min_periods=max(2, window // 2)).std(ddof=1) * math.sqrt(window)


def _benchmark_window_returns(benchmark_daily: pd.DataFrame) -> pd.DataFrame:
    if benchmark_daily is None or benchmark_daily.empty:
        return pd.DataFrame(columns=["market", "trade_date"])
    frame = benchmark_daily.copy()
    for col in ("market", "trade_date"):
        frame[col] = frame[col].astype(str)
    frame["daily_return_pct"] = pd.to_numeric(frame["daily_return_pct"], errors="coerce")
    frame = frame.sort_values(["market", "trade_date"])
    out_parts = []
    for _, group in frame.groupby("market", sort=False):
        g = group.copy()
        for w in (*SHORT_WINDOWS, *MID_WINDOWS):
            g[f"mkt_ret_{w}d"] = _compound_return_from_daily(g["daily_return_pct"], w)
        out_parts.append(g[["market", "trade_date", *[f"mkt_ret_{w}d" for w in (*SHORT_WINDOWS, *MID_WINDOWS)]]])
    return pd.concat(out_parts, ignore_index=True) if out_parts else pd.DataFrame(columns=["market", "trade_date"])


def _sector_window_returns(sector_daily: pd.DataFrame) -> pd.DataFrame:
    if sector_daily is None or sector_daily.empty:
        return pd.DataFrame(columns=["market", "level1_id", "level2_id", "level3_id", "trade_date"])
    frame = sector_daily.copy()
    frame = frame[frame["scope"].astype(str) == "L3"].copy()
    for col in ("market", "level1_id", "level2_id", "level3_id", "trade_date"):
        frame[col] = frame[col].astype(str)
    frame["daily_return_pct"] = pd.to_numeric(frame["daily_return_pct"], errors="coerce")
    frame = frame.sort_values(["market", "level1_id", "level2_id", "level3_id", "trade_date"])
    parts = []
    for _, group in frame.groupby(["market", "level1_id", "level2_id", "level3_id"], sort=False):
        g = group.copy()
        for w in (20, 60, 120):
            g[f"sec_ret_{w}d"] = _compound_return_from_daily(g["daily_return_pct"], w)
        parts.append(
            g[
                [
                    "market",
                    "level1_id",
                    "level2_id",
                    "level3_id",
                    "trade_date",
                    "sec_ret_20d",
                    "sec_ret_60d",
                    "sec_ret_120d",
                ]
            ]
        )
    return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(columns=["market", "level1_id", "level2_id", "level3_id", "trade_date"])


def _cross_section_pe_cheap(pe: pd.Series) -> pd.Series:
    """100 - percentile rank of positive PE within the group (caller groupby)."""
    vals = pd.to_numeric(pe, errors="coerce")
    out = pd.Series(np.nan, index=pe.index, dtype=float)
    valid = vals.notna() & (vals > 0)
    if int(valid.sum()) < 2:
        return out
    # Lower PE → higher cheap score.
    pct = vals.where(valid).rank(method="average", pct=True) * 100.0
    out.loc[valid] = 100.0 - pct.loc[valid]
    return out


def _add_rolling_features(td: pd.DataFrame) -> pd.DataFrame:
    """Vectorized rolling mom/vol/MA/drawdown features per ticker."""
    td = td.copy()
    r = pd.to_numeric(td["daily_return_pct"], errors="coerce") / 100.0
    td["_log_r"] = np.log1p(r.clip(lower=-0.999999))
    grouped = td.groupby(["market", "ticker"], sort=False)

    def _roll_sum(series: pd.Series, window: int, min_p: int) -> pd.Series:
        return grouped[series.name].rolling(window, min_periods=min_p).sum().droplevel([0, 1])

    def _roll_std(series: pd.Series, window: int, min_p: int) -> pd.Series:
        return grouped[series.name].rolling(window, min_periods=min_p).std(ddof=1).droplevel([0, 1])

    def _roll_mean(series: pd.Series, window: int, min_p: int) -> pd.Series:
        return grouped[series.name].rolling(window, min_periods=min_p).mean().droplevel([0, 1])

    def _roll_max(series: pd.Series, window: int, min_p: int) -> pd.Series:
        return grouped[series.name].rolling(window, min_periods=min_p).max().droplevel([0, 1])

    for w in (*SHORT_WINDOWS, *MID_WINDOWS):
        min_p = max(2, w // 2)
        td[f"_ret_{w}d"] = np.expm1(_roll_sum(td["_log_r"], w, min_p)) * 100.0
        td[f"_vol_{w}d"] = _roll_std(td["daily_return_pct"], w, min_p) * math.sqrt(w)

    td["s_mom_ret_5d"] = td["_ret_5d"]
    td["s_mom_ret_10d"] = td["_ret_10d"]
    td["s_mom_ret_20d"] = td["_ret_20d"]
    td["m_mom_ret_60d"] = td["_ret_60d"]
    td["m_mom_ret_120d"] = td["_ret_120d"]
    td["m_mom_ret_252d"] = td["_ret_252d"]
    td["s_risk_vol_20d"] = td["_vol_20d"]
    td["m_risk_vol_60d"] = td["_vol_60d"]
    td["m_risk_vol_120d"] = td["_vol_120d"]
    td["m_risk_vol_252d"] = td["_vol_252d"]

    for w, prefix in ((5, "s"), (10, "s"), (20, "s"), (60, "m"), (120, "m"), (252, "m")):
        vol = td[f"_vol_{w}d"]
        ret = td[f"_ret_{w}d"]
        adj = ret / vol
        adj = adj.where((vol > 0) & ret.notna() & vol.notna())
        td[f"{prefix}_mom_riskadj_{w}d"] = adj

    td["s_mom_reversal_1d"] = -pd.to_numeric(td["daily_return_pct"], errors="coerce")

    # Streaks: scan within each ticker (numpy, still O(N) total).
    up = np.full(len(td), np.nan, dtype=float)
    down = np.full(len(td), np.nan, dtype=float)
    rets = pd.to_numeric(td["daily_return_pct"], errors="coerce").to_numpy(dtype=float)
    keys = td["market"].astype(str) + "\0" + td["ticker"].astype(str)
    key_arr = keys.to_numpy()
    prev_key = None
    prev_up = 0.0
    prev_down = 0.0
    for i in range(len(td)):
        key = key_arr[i]
        if key != prev_key:
            prev_key = key
            prev_up = 0.0
            prev_down = 0.0
        val = rets[i]
        if not np.isfinite(val):
            up[i] = np.nan
            down[i] = np.nan
            prev_up = 0.0
            prev_down = 0.0
            continue
        if val > 0:
            prev_up += 1.0
            prev_down = 0.0
        elif val < 0:
            prev_down += 1.0
            prev_up = 0.0
        else:
            prev_up = 0.0
            prev_down = 0.0
        up[i] = prev_up
        down[i] = prev_down
    td["s_mom_up_streak"] = up
    td["s_mom_down_streak"] = down

    close = pd.to_numeric(td["close"], errors="coerce")
    td["_close"] = close
    td["s_tech_dist_ma20"] = close / _roll_mean(td["_close"], 20, 10) - 1.0
    td["m_tech_dist_ma60"] = close / _roll_mean(td["_close"], 60, 30) - 1.0
    td["m_tech_dist_ma120"] = close / _roll_mean(td["_close"], 120, 60) - 1.0
    for w in (60, 120, 252):
        peak = _roll_max(td["_close"], w, max(2, w // 2))
        td[f"m_risk_dd_from_peak_{w}d"] = (close / peak - 1.0) * 100.0
    return td


def compute_ticker_alpha_factors_frame(
    *,
    ticker_daily: pd.DataFrame,
    constituents: pd.DataFrame | None = None,
    benchmark_daily: pd.DataFrame | None = None,
    sector_daily: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Build ticker short+mid alpha factor daily table."""
    if ticker_daily is None or ticker_daily.empty:
        return pd.DataFrame(columns=TICKER_ALPHA_FACTORS_COLUMNS)

    td = ticker_daily.copy()
    for col in ("market", "ticker", "trade_date"):
        td[col] = td[col].astype(str)
    td["close"] = pd.to_numeric(td["close"], errors="coerce")
    td["daily_return_pct"] = pd.to_numeric(td["daily_return_pct"], errors="coerce")
    td = td.sort_values(["market", "ticker", "trade_date"]).reset_index(drop=True)

    primary = _primary_constituent_map(constituents if constituents is not None else pd.DataFrame())
    td = td.merge(primary, on=["market", "ticker"], how="left")
    td = _add_rolling_features(td)

    cap = pd.to_numeric(td.get("market_cap"), errors="coerce")
    pe = pd.to_numeric(td.get("pe"), errors="coerce")
    td["s_size_log_cap"] = np.log(cap.where(cap > 0))
    td["m_size_log_cap"] = td["s_size_log_cap"]
    td["s_val_pe"] = pe
    td["m_val_pe"] = pe
    td["s_val_pe_cheap_cs"] = td.groupby(["trade_date", "market"], sort=False)["pe"].transform(_cross_section_pe_cheap)
    td["m_val_pe_cheap_cs"] = td["s_val_pe_cheap_cs"]

    mkt = _benchmark_window_returns(benchmark_daily if benchmark_daily is not None else pd.DataFrame())
    if not mkt.empty:
        td = td.merge(mkt, on=["market", "trade_date"], how="left")
        for w, prefix in ((5, "s"), (10, "s"), (20, "s"), (60, "m"), (120, "m"), (252, "m")):
            td[f"{prefix}_rs_{w}d"] = td[f"_ret_{w}d"] - td[f"mkt_ret_{w}d"]
    else:
        for w, prefix in ((5, "s"), (10, "s"), (20, "s"), (60, "m"), (120, "m"), (252, "m")):
            td[f"{prefix}_rs_{w}d"] = np.nan

    sec = _sector_window_returns(sector_daily if sector_daily is not None else pd.DataFrame())
    if not sec.empty:
        td = td.merge(sec, on=["market", "level1_id", "level2_id", "level3_id", "trade_date"], how="left")
        td["s_rs_vs_sector_20d"] = td["_ret_20d"] - td["sec_ret_20d"]
        td["m_rs_vs_sector_60d"] = td["_ret_60d"] - td["sec_ret_60d"]
        td["m_rs_vs_sector_120d"] = td["_ret_120d"] - td["sec_ret_120d"]
    else:
        td["s_rs_vs_sector_20d"] = np.nan
        td["m_rs_vs_sector_60d"] = np.nan
        td["m_rs_vs_sector_120d"] = np.nan

    td["factor_universe_size"] = td.groupby(["trade_date", "market"], sort=False)["ticker"].transform("size")
    td["factor_rule"] = TICKER_ALPHA_FACTORS_RULE
    has_ret = td["daily_return_pct"].notna()
    has_sector = td["level3_id"].notna() & (td["level3_id"].astype(str).str.len() > 0) & (td["level3_id"] != "nan")
    td["row_status"] = np.where(has_ret & has_sector, "ok", np.where(has_ret, "partial", "insufficient"))

    for col in ("level1_id", "level2_id", "level3_id", "role"):
        if col not in td.columns:
            td[col] = ""
        td[col] = td[col].fillna("").astype(str)

    return td.reindex(columns=TICKER_ALPHA_FACTORS_COLUMNS)
