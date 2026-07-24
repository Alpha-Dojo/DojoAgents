"""Phase C: sector alpha factors (short + mid) from theme_state, horizon, and structure."""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd

from dojoagents.dashboard.services.sector_leader_concentration import compute_leader_concentration

ALPHA_FACTORS_RULE = "sector_alpha_factors_v1"
SECTOR_ALPHA_FACTORS_FILE = "sector_alpha_factors_daily.parquet"

JOIN_KEYS = ["trade_date", "market", "scope", "level1_id", "level2_id", "level3_id"]

# Factors that embed recent returns — OK to store, avoid as same-day labels.
RESEARCH_ONLY_LEAKAGE_RISK = frozenset(
    {
        "s_mom_ret_5d",
        "s_mom_ret_10d",
        "s_mom_riskadj_5d",
        "s_mom_riskadj_10d",
    }
)

STAGE_SCORE = {
    "expanding": 1.0,
    "stable": 0.0,
    "contracting": -1.0,
}

SECTOR_ALPHA_FACTORS_COLUMNS = [
    # keys
    "trade_date",
    "market",
    "scope",
    "level1_id",
    "level2_id",
    "level3_id",
    "link_key",
    # meta
    "eligible_count",
    "factor_universe_size",
    "theme_row_status",
    "horizon_row_status",
    "factor_rule",
    # ---- short ----
    "s_brd_breadth",
    "s_brd_advancers",
    "s_brd_vol_expand",
    "s_brd_new_highs",
    "s_mom_ret_5d",  # research_only / leakage risk — see RESEARCH_ONLY_LEAKAGE_RISK
    "s_mom_ret_10d",  # research_only / leakage risk
    "s_mom_ret_20d",
    "s_mom_riskadj_5d",  # research_only / leakage risk
    "s_mom_riskadj_10d",  # research_only / leakage risk
    "s_mom_riskadj_20d",
    "s_risk_vol_20d",
    "s_mom_up_streak",
    "s_mom_down_streak",
    "s_rs_5d",
    "s_rs_10d",
    "s_rs_20d",
    "s_rs_rank_5d_inv",
    "s_rs_rotation",
    "s_xmarket_confirm",
    "s_struct_leader_conc",
    "s_struct_ret_dispersion",
    # ---- mid ----
    "m_mom_ret_60d",
    "m_mom_ret_120d",
    "m_mom_ret_252d",
    "m_rs_60d",
    "m_rs_120d",
    "m_rs_252d",
    "m_mom_riskadj_60d",
    "m_mom_riskadj_120d",
    "m_mom_riskadj_252d",
    "m_risk_vol_60d",
    "m_risk_vol_120d",
    "m_risk_vol_252d",
    "m_risk_mdd_60d",
    "m_risk_mdd_120d",
    "m_risk_mdd_252d",
    "m_val_pe",
    "m_val_pe_cheap_cs",
    "m_val_pe_cheap_ts",
    "m_qual_rev_yoy",
    "m_qual_rev_accel",
    "m_qual_rev_improvers",
    "m_qual_np_yoy",
    "m_qual_np_improvers",
    "m_qual_margin",
    "m_qual_margin_chg",
    "m_qual_rev_yoy_4q_avg",
    "m_qual_rev_yoy_streak",
    "m_qual_stage_score",
    "m_struct_hhi_cap",
]


def _finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return number


def rank_to_inv_score(rank: Any, universe_size: Any) -> float | None:
    """Map 1-best rank into 0–100 (higher is better)."""
    r = _finite(rank)
    n = _finite(universe_size)
    if r is None or n is None or r <= 0 or n < 2:
        return None
    return float(max(0.0, min(100.0, 100.0 * (1.0 - (r - 1.0) / (n - 1.0)))))


def stage_to_score(stage_hint: Any) -> float | None:
    key = str(stage_hint or "").strip().lower()
    if not key:
        return None
    return float(STAGE_SCORE.get(key, 0.0))


def factor_dictionary() -> list[dict[str, Any]]:
    """Human-readable factor meta for manifest / docs."""
    rows: list[dict[str, Any]] = []
    short = [
        ("s_brd_breadth", "theme", "breadth_score", "Breadth composite"),
        ("s_brd_advancers", "theme", "advancers_pct", "Advancers share"),
        ("s_brd_vol_expand", "theme", "volume_expansion_pct", "Volume expansion share"),
        ("s_brd_new_highs", "theme", "new_highs_pct", "New highs share"),
        ("s_mom_ret_5d", "theme", "return_5d_pct", "5D return (leakage risk)"),
        ("s_mom_ret_10d", "theme", "return_10d_pct", "10D return (leakage risk)"),
        ("s_mom_ret_20d", "theme", "return_20d_pct", "20D return"),
        ("s_mom_riskadj_5d", "theme", "risk_adjusted_5d", "5D risk-adjusted (leakage risk)"),
        ("s_mom_riskadj_10d", "theme", "risk_adjusted_10d", "10D risk-adjusted (leakage risk)"),
        ("s_mom_riskadj_20d", "theme", "risk_adjusted_20d", "20D risk-adjusted"),
        ("s_risk_vol_20d", "theme", "volatility_20d_pct", "20D volatility"),
        ("s_mom_up_streak", "theme", "up_streak_days", "Up streak"),
        ("s_mom_down_streak", "theme", "down_streak_days", "Down streak"),
        ("s_rs_5d", "theme", "relative_strength_5d", "RS vs benchmark 5D"),
        ("s_rs_10d", "theme", "relative_strength_10d", "RS vs benchmark 10D"),
        ("s_rs_20d", "theme", "relative_strength_20d", "RS vs benchmark 20D"),
        ("s_rs_rank_5d_inv", "theme", "rs_rank_5d", "Inverted RS rank (higher=better)"),
        ("s_rs_rotation", "theme", "rotation_score", "Rotation score"),
        ("s_xmarket_confirm", "theme", "confirmation_score", "Cross-market confirmation 0–100"),
        ("s_struct_leader_conc", "struct", "leader_concentration", "Top-1 return contribution share"),
        ("s_struct_ret_dispersion", "struct", "member_return_std", "Cross-sectional std of member returns"),
    ]
    mid = [
        ("m_mom_ret_60d", "horizon", "return_60d_pct", "60D return"),
        ("m_mom_ret_120d", "horizon", "return_120d_pct", "120D return"),
        ("m_mom_ret_252d", "horizon", "return_252d_pct", "252D return"),
        ("m_rs_60d", "horizon", "relative_strength_60d", "RS 60D"),
        ("m_rs_120d", "horizon", "relative_strength_120d", "RS 120D"),
        ("m_rs_252d", "horizon", "relative_strength_252d", "RS 252D"),
        ("m_mom_riskadj_60d", "horizon", "risk_adjusted_60d", "Risk-adjusted 60D"),
        ("m_mom_riskadj_120d", "horizon", "risk_adjusted_120d", "Risk-adjusted 120D"),
        ("m_mom_riskadj_252d", "horizon", "risk_adjusted_252d", "Risk-adjusted 252D"),
        ("m_risk_vol_60d", "horizon", "volatility_60d_pct", "Vol 60D"),
        ("m_risk_vol_120d", "horizon", "volatility_120d_pct", "Vol 120D"),
        ("m_risk_vol_252d", "horizon", "volatility_252d_pct", "Vol 252D"),
        ("m_risk_mdd_60d", "horizon", "max_drawdown_60d_pct", "Max drawdown 60D"),
        ("m_risk_mdd_120d", "horizon", "max_drawdown_120d_pct", "Max drawdown 120D"),
        ("m_risk_mdd_252d", "horizon", "max_drawdown_252d_pct", "Max drawdown 252D"),
        ("m_val_pe", "horizon", "weighted_pe", "Cap-weighted PE"),
        ("m_val_pe_cheap_cs", "horizon", "pe_percentile_cross_section", "100 - CS PE percentile"),
        ("m_val_pe_cheap_ts", "horizon", "pe_percentile_trailing_252d", "100 - trailing PE percentile"),
        ("m_qual_rev_yoy", "theme/horizon", "industry_revenue_yoy_pct", "Revenue YoY"),
        ("m_qual_rev_accel", "theme", "industry_revenue_accel_pp", "Revenue YoY acceleration"),
        ("m_qual_rev_improvers", "theme", "revenue_improvers_pct", "Share with improving revenue"),
        ("m_qual_np_yoy", "theme/horizon", "industry_net_profit_yoy_pct", "Net profit YoY"),
        ("m_qual_np_improvers", "theme", "profit_improvers_pct", "Share with improving profit"),
        ("m_qual_margin", "theme/horizon", "industry_net_margin_pct", "Net margin"),
        ("m_qual_margin_chg", "theme", "industry_net_margin_change_pp", "Net margin change"),
        ("m_qual_rev_yoy_4q_avg", "horizon", "revenue_yoy_avg_4q_pct", "Avg revenue YoY (up to 4Q)"),
        ("m_qual_rev_yoy_streak", "horizon", "revenue_yoy_positive_streak", "Positive YoY streak"),
        ("m_qual_stage_score", "theme/horizon", "stage_hint", "expanding=1 stable=0 contracting=-1"),
        ("m_struct_hhi_cap", "struct", "cap_hhi", "Market-cap HHI (snapshot weights)"),
    ]
    for name, source, raw, desc in short + mid:
        horizon = "short" if name.startswith("s_") else "mid"
        rows.append(
            {
                "name": name,
                "horizon": horizon,
                "source": source,
                "raw_field": raw,
                "description": desc,
                "research_only_leakage_risk": name in RESEARCH_ONLY_LEAKAGE_RISK,
                "higher_is_better": not name.startswith("s_risk_")
                and not name.startswith("m_risk_")
                and name != "s_mom_down_streak"
                and "mdd" not in name
                and name != "s_struct_leader_conc",
            }
        )
    return rows


def compute_cap_hhi_by_sector(constituents: pd.DataFrame) -> pd.DataFrame:
    """HHI from latest market-cap snapshot weights (constant across dates)."""
    if constituents is None or constituents.empty:
        return pd.DataFrame(columns=["market", "level1_id", "level2_id", "level3_id", "m_struct_hhi_cap"])
    frame = constituents.copy()
    for col in ("market", "level1_id", "level2_id", "level3_id", "ticker"):
        if col in frame.columns:
            frame[col] = frame[col].astype(str)
    frame["market_cap"] = pd.to_numeric(frame.get("market_cap"), errors="coerce")
    frame = frame[frame["market_cap"].notna() & (frame["market_cap"] > 0)]
    if frame.empty:
        return pd.DataFrame(columns=["market", "level1_id", "level2_id", "level3_id", "m_struct_hhi_cap"])

    rows: list[dict[str, Any]] = []
    keys = ["market", "level1_id", "level2_id", "level3_id"]
    for key_vals, group in frame.groupby(keys, sort=False):
        if not isinstance(key_vals, tuple):
            key_vals = (key_vals,)
        caps = group["market_cap"].to_numpy(dtype=float)
        total = float(caps.sum())
        if total <= 0 or len(caps) < 1:
            hhi = float("nan")
        else:
            weights = caps / total
            hhi = float(np.sum(weights * weights))
        rows.append(
            {
                "market": key_vals[0],
                "level1_id": key_vals[1],
                "level2_id": key_vals[2],
                "level3_id": key_vals[3],
                "m_struct_hhi_cap": hhi,
            }
        )
    return pd.DataFrame(rows)


def compute_structure_daily_factors(
    *,
    constituents: pd.DataFrame,
    ticker_daily: pd.DataFrame,
    sector_daily: pd.DataFrame,
) -> pd.DataFrame:
    """Daily leader concentration + member return dispersion for L3 sectors."""
    empty_cols = JOIN_KEYS + ["s_struct_leader_conc", "s_struct_ret_dispersion"]
    if constituents is None or constituents.empty or ticker_daily is None or ticker_daily.empty or sector_daily is None or sector_daily.empty:
        return pd.DataFrame(columns=empty_cols)

    cons = constituents.copy()
    for col in ("market", "level1_id", "level2_id", "level3_id", "ticker"):
        cons[col] = cons[col].astype(str)
    cons["market_cap"] = pd.to_numeric(cons["market_cap"], errors="coerce")
    cons = cons[cons["market_cap"].notna() & (cons["market_cap"] > 0)]
    cons = cons.drop_duplicates(subset=["market", "level1_id", "level2_id", "level3_id", "ticker"], keep="first")

    td = ticker_daily.copy()
    for col in ("market", "ticker", "trade_date"):
        td[col] = td[col].astype(str)
    td["daily_return_pct"] = pd.to_numeric(td["daily_return_pct"], errors="coerce")

    sd = sector_daily.copy()
    sd = sd[sd["scope"].astype(str) == "L3"].copy()
    for col in JOIN_KEYS:
        sd[col] = sd[col].astype(str)
    sd["daily_return_pct"] = pd.to_numeric(sd["daily_return_pct"], errors="coerce")

    members = cons.merge(td, on=["market", "ticker"], how="inner")
    if members.empty:
        return pd.DataFrame(columns=empty_cols)

    # Dispersion: std of member returns (equal-weight cross-section).
    disp = (
        members.groupby(["trade_date", "market", "level1_id", "level2_id", "level3_id"], sort=False)["daily_return_pct"]
        .agg(s_struct_ret_dispersion=lambda s: float(s.std(ddof=1)) if s.notna().sum() >= 2 else float("nan"))
        .reset_index()
    )
    disp["scope"] = "L3"

    # Leader concentration: per sector-day.
    sector_ret = sd[JOIN_KEYS + ["daily_return_pct"]].rename(columns={"daily_return_pct": "sector_return_pct"})
    merged = members.merge(
        sector_ret,
        on=["trade_date", "market", "level1_id", "level2_id", "level3_id"],
        how="inner",
    )
    conc_rows: list[dict[str, Any]] = []
    group_cols = ["trade_date", "market", "level1_id", "level2_id", "level3_id", "sector_return_pct"]
    for key_vals, group in merged.groupby(group_cols, sort=False):
        trade_date, market, l1, l2, l3, sector_ret_v = key_vals
        member_tuples = [(str(r.ticker), float(r.market_cap), float(r.daily_return_pct) if pd.notna(r.daily_return_pct) else None) for r in group.itertuples(index=False)]
        payload = compute_leader_concentration(member_tuples, float(sector_ret_v))
        conc_rows.append(
            {
                "trade_date": trade_date,
                "market": market,
                "scope": "L3",
                "level1_id": l1,
                "level2_id": l2,
                "level3_id": l3,
                "s_struct_leader_conc": (float(payload.leader_concentration_pct) if payload is not None else float("nan")),
            }
        )
    conc = pd.DataFrame(conc_rows) if conc_rows else pd.DataFrame(columns=empty_cols)
    out = disp.merge(conc, on=JOIN_KEYS, how="outer")
    return out.reindex(columns=empty_cols)


def _map_theme_horizon_factors(
    theme_df: pd.DataFrame,
    horizon_df: pd.DataFrame | None,
) -> pd.DataFrame:
    theme = theme_df.copy()
    for col in JOIN_KEYS + ["link_key"]:
        if col in theme.columns:
            theme[col] = theme[col].astype(str)
    if "scope" in theme.columns:
        theme = theme[theme["scope"].astype(str) == "L3"].copy()

    if horizon_df is not None and not horizon_df.empty:
        horizon = horizon_df.copy()
        for col in JOIN_KEYS + ["link_key"]:
            if col in horizon.columns:
                horizon[col] = horizon[col].astype(str)
        keep = [
            c
            for c in (
                *JOIN_KEYS,
                "return_60d_pct",
                "return_120d_pct",
                "return_252d_pct",
                "relative_strength_60d",
                "relative_strength_120d",
                "relative_strength_252d",
                "risk_adjusted_60d",
                "risk_adjusted_120d",
                "risk_adjusted_252d",
                "volatility_60d_pct",
                "volatility_120d_pct",
                "volatility_252d_pct",
                "max_drawdown_60d_pct",
                "max_drawdown_120d_pct",
                "max_drawdown_252d_pct",
                "weighted_pe",
                "pe_percentile_cross_section",
                "pe_percentile_trailing_252d",
                "industry_revenue_yoy_pct",
                "industry_net_profit_yoy_pct",
                "industry_net_margin_pct",
                "revenue_yoy_avg_4q_pct",
                "revenue_yoy_positive_streak",
                "stage_hint",
                "row_status",
            )
            if c in horizon.columns
        ]
        horizon = horizon[keep].rename(
            columns={
                "row_status": "horizon_row_status",
                "stage_hint": "horizon_stage_hint",
                "industry_revenue_yoy_pct": "horizon_rev_yoy",
                "industry_net_profit_yoy_pct": "horizon_np_yoy",
                "industry_net_margin_pct": "horizon_margin",
            }
        )
        base = theme.merge(horizon, on=JOIN_KEYS, how="left", suffixes=("", "_h"))
        if "link_key_h" in base.columns:
            base["link_key"] = base["link_key"].where(base["link_key"].astype(str).str.len() > 0, base["link_key_h"])
            base = base.drop(columns=["link_key_h"])
    else:
        base = theme.copy()
        base["horizon_row_status"] = ""

    universe = pd.to_numeric(base.get("rs_rank_universe_size"), errors="coerce")
    inv_rank = [
        rank_to_inv_score(rank, size)
        for rank, size in zip(
            base.get("rs_rank_5d", pd.Series(np.nan, index=base.index)),
            universe if universe is not None else pd.Series(np.nan, index=base.index),
            strict=False,
        )
    ]
    pe_cs = pd.to_numeric(base.get("pe_percentile_cross_section"), errors="coerce")
    pe_ts = pd.to_numeric(base.get("pe_percentile_trailing_252d"), errors="coerce")
    stage = base.get("stage_hint", pd.Series("", index=base.index))
    if "horizon_stage_hint" in base.columns:
        stage = stage.where(stage.astype(str).str.len() > 0, base["horizon_stage_hint"])

    rev_yoy = pd.to_numeric(base.get("industry_revenue_yoy_pct"), errors="coerce")
    if "horizon_rev_yoy" in base.columns:
        rev_yoy = rev_yoy.fillna(pd.to_numeric(base["horizon_rev_yoy"], errors="coerce"))
    np_yoy = pd.to_numeric(base.get("industry_net_profit_yoy_pct"), errors="coerce")
    if "horizon_np_yoy" in base.columns:
        np_yoy = np_yoy.fillna(pd.to_numeric(base["horizon_np_yoy"], errors="coerce"))
    margin = pd.to_numeric(base.get("industry_net_margin_pct"), errors="coerce")
    if "horizon_margin" in base.columns:
        margin = margin.fillna(pd.to_numeric(base["horizon_margin"], errors="coerce"))

    out = pd.DataFrame(
        {
            "trade_date": base["trade_date"].astype(str),
            "market": base["market"].astype(str),
            "scope": base.get("scope", "L3").astype(str),
            "level1_id": base["level1_id"].astype(str),
            "level2_id": base["level2_id"].astype(str),
            "level3_id": base["level3_id"].astype(str),
            "link_key": base.get("link_key", "").astype(str),
            "eligible_count": pd.to_numeric(base.get("eligible_count"), errors="coerce"),
            "factor_universe_size": universe,
            "theme_row_status": base.get("row_status", "").astype(str),
            "horizon_row_status": base.get("horizon_row_status", "").astype(str),
            "factor_rule": ALPHA_FACTORS_RULE,
            "s_brd_breadth": pd.to_numeric(base.get("breadth_score"), errors="coerce"),
            "s_brd_advancers": pd.to_numeric(base.get("advancers_pct"), errors="coerce"),
            "s_brd_vol_expand": pd.to_numeric(base.get("volume_expansion_pct"), errors="coerce"),
            "s_brd_new_highs": pd.to_numeric(base.get("new_highs_pct"), errors="coerce"),
            "s_mom_ret_5d": pd.to_numeric(base.get("return_5d_pct"), errors="coerce"),
            "s_mom_ret_10d": pd.to_numeric(base.get("return_10d_pct"), errors="coerce"),
            "s_mom_ret_20d": pd.to_numeric(base.get("return_20d_pct"), errors="coerce"),
            "s_mom_riskadj_5d": pd.to_numeric(base.get("risk_adjusted_5d"), errors="coerce"),
            "s_mom_riskadj_10d": pd.to_numeric(base.get("risk_adjusted_10d"), errors="coerce"),
            "s_mom_riskadj_20d": pd.to_numeric(base.get("risk_adjusted_20d"), errors="coerce"),
            "s_risk_vol_20d": pd.to_numeric(base.get("volatility_20d_pct"), errors="coerce"),
            "s_mom_up_streak": pd.to_numeric(base.get("up_streak_days"), errors="coerce"),
            "s_mom_down_streak": pd.to_numeric(base.get("down_streak_days"), errors="coerce"),
            "s_rs_5d": pd.to_numeric(base.get("relative_strength_5d"), errors="coerce"),
            "s_rs_10d": pd.to_numeric(base.get("relative_strength_10d"), errors="coerce"),
            "s_rs_20d": pd.to_numeric(base.get("relative_strength_20d"), errors="coerce"),
            "s_rs_rank_5d_inv": pd.Series(inv_rank, index=base.index, dtype=float),
            "s_rs_rotation": pd.to_numeric(base.get("rotation_score"), errors="coerce"),
            "s_xmarket_confirm": pd.to_numeric(base.get("confirmation_score"), errors="coerce"),
            "m_mom_ret_60d": pd.to_numeric(base.get("return_60d_pct"), errors="coerce"),
            "m_mom_ret_120d": pd.to_numeric(base.get("return_120d_pct"), errors="coerce"),
            "m_mom_ret_252d": pd.to_numeric(base.get("return_252d_pct"), errors="coerce"),
            "m_rs_60d": pd.to_numeric(base.get("relative_strength_60d"), errors="coerce"),
            "m_rs_120d": pd.to_numeric(base.get("relative_strength_120d"), errors="coerce"),
            "m_rs_252d": pd.to_numeric(base.get("relative_strength_252d"), errors="coerce"),
            "m_mom_riskadj_60d": pd.to_numeric(base.get("risk_adjusted_60d"), errors="coerce"),
            "m_mom_riskadj_120d": pd.to_numeric(base.get("risk_adjusted_120d"), errors="coerce"),
            "m_mom_riskadj_252d": pd.to_numeric(base.get("risk_adjusted_252d"), errors="coerce"),
            "m_risk_vol_60d": pd.to_numeric(base.get("volatility_60d_pct"), errors="coerce"),
            "m_risk_vol_120d": pd.to_numeric(base.get("volatility_120d_pct"), errors="coerce"),
            "m_risk_vol_252d": pd.to_numeric(base.get("volatility_252d_pct"), errors="coerce"),
            "m_risk_mdd_60d": pd.to_numeric(base.get("max_drawdown_60d_pct"), errors="coerce"),
            "m_risk_mdd_120d": pd.to_numeric(base.get("max_drawdown_120d_pct"), errors="coerce"),
            "m_risk_mdd_252d": pd.to_numeric(base.get("max_drawdown_252d_pct"), errors="coerce"),
            "m_val_pe": pd.to_numeric(base.get("weighted_pe"), errors="coerce"),
            "m_val_pe_cheap_cs": (100.0 - pe_cs).where(pe_cs.notna()),
            "m_val_pe_cheap_ts": (100.0 - pe_ts).where(pe_ts.notna()),
            "m_qual_rev_yoy": rev_yoy,
            "m_qual_rev_accel": pd.to_numeric(base.get("industry_revenue_accel_pp"), errors="coerce"),
            "m_qual_rev_improvers": pd.to_numeric(base.get("revenue_improvers_pct"), errors="coerce"),
            "m_qual_np_yoy": np_yoy,
            "m_qual_np_improvers": pd.to_numeric(base.get("profit_improvers_pct"), errors="coerce"),
            "m_qual_margin": margin,
            "m_qual_margin_chg": pd.to_numeric(base.get("industry_net_margin_change_pp"), errors="coerce"),
            "m_qual_rev_yoy_4q_avg": pd.to_numeric(base.get("revenue_yoy_avg_4q_pct"), errors="coerce"),
            "m_qual_rev_yoy_streak": pd.to_numeric(base.get("revenue_yoy_positive_streak"), errors="coerce"),
            "m_qual_stage_score": stage.map(stage_to_score),
        }
    )
    return out


def compute_sector_alpha_factors_frame(
    *,
    theme_state_daily: pd.DataFrame,
    sector_horizon_metrics: pd.DataFrame | None = None,
    constituents: pd.DataFrame | None = None,
    ticker_daily: pd.DataFrame | None = None,
    sector_daily: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Build unified short+mid alpha factor daily table."""
    if theme_state_daily is None or theme_state_daily.empty:
        return pd.DataFrame(columns=SECTOR_ALPHA_FACTORS_COLUMNS)

    factors = _map_theme_horizon_factors(theme_state_daily, sector_horizon_metrics)

    if constituents is not None and not constituents.empty:
        hhi = compute_cap_hhi_by_sector(constituents)
        factors = factors.merge(
            hhi,
            on=["market", "level1_id", "level2_id", "level3_id"],
            how="left",
        )
    else:
        factors["m_struct_hhi_cap"] = np.nan

    if constituents is not None and ticker_daily is not None and sector_daily is not None and not constituents.empty and not ticker_daily.empty and not sector_daily.empty:
        struct = compute_structure_daily_factors(
            constituents=constituents,
            ticker_daily=ticker_daily,
            sector_daily=sector_daily,
        )
        factors = factors.merge(struct, on=JOIN_KEYS, how="left")
    else:
        factors["s_struct_leader_conc"] = np.nan
        factors["s_struct_ret_dispersion"] = np.nan

    # Cross-section universe size fallback.
    if "factor_universe_size" in factors.columns:
        factors["factor_universe_size"] = factors.groupby(["trade_date", "market"], sort=False)["level3_id"].transform("size")

    return factors.reindex(columns=SECTOR_ALPHA_FACTORS_COLUMNS)
