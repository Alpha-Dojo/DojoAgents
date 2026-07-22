"""Phase C: sector health radar + short/mid advice scores from theme_state + horizon."""

from __future__ import annotations

import json
import math
from typing import Any

import numpy as np
import pandas as pd

from dojoagents.dashboard.services.theme_state_metrics import MIN_ELIGIBLE_COUNT

RADAR_RULE = "radar_v1"
SHORT_ADVICE_RULE = "short_advice_v1"
MID_ADVICE_RULE = "mid_advice_v1"

SECTOR_HEALTH_RADAR_FILE = "sector_health_radar.parquet"
SECTOR_ADVICE_DAILY_FILE = "sector_advice_daily.parquet"

RADAR_AXIS_WEIGHTS = {
    "capital_heat": 0.20,
    "technical_momentum": 0.20,
    "relative_strength": 0.25,
    "valuation_safety": 0.15,
    "fundamental_trend": 0.20,
}

SHORT_SCORE_WEIGHTS = {
    "rotation": 0.40,
    "breadth": 0.20,
    "confirmation": 0.15,
    "rs_20d": 0.15,
    "stage": 0.10,
}

MID_SCORE_WEIGHTS = {
    "rs_mid": 0.25,
    "risk_adj": 0.20,
    "revenue_yoy": 0.20,
    "valuation": 0.15,
    "drawdown": 0.10,
    "stage": 0.10,
}

STAGE_SCORE = {
    "expanding": 80.0,
    "stable": 50.0,
    "contracting": 20.0,
}

JOIN_KEYS = ["trade_date", "market", "scope", "level1_id", "level2_id", "level3_id"]

SECTOR_HEALTH_RADAR_COLUMNS = [
    "trade_date",
    "market",
    "scope",
    "level1_id",
    "level2_id",
    "level3_id",
    "link_key",
    "overall_score",
    "overall_band",
    "confidence",
    "axes_available",
    "scoring_rule",
    "score_capital_heat",
    "score_technical_momentum",
    "score_relative_strength",
    "score_valuation_safety",
    "score_fundamental_trend",
    "stance_capital_heat",
    "stance_technical_momentum",
    "stance_relative_strength",
    "stance_valuation_safety",
    "stance_fundamental_trend",
    "raw_breadth_score",
    "raw_rotation_rank",
    "raw_rs_20d",
    "raw_pe_percentile_cs",
    "raw_revenue_yoy_pct",
    "raw_stage_hint",
    "raw_confirmation_score",
    "eligible_count",
    "theme_row_status",
    "horizon_row_status",
    "narrative_status",
    "overall_label_zh",
    "overall_label_en",
    "overall_summary_zh",
    "overall_summary_en",
]

SECTOR_ADVICE_DAILY_COLUMNS = [
    "trade_date",
    "market",
    "scope",
    "level1_id",
    "level2_id",
    "level3_id",
    "link_key",
    "short_score",
    "short_bucket",
    "short_action",
    "short_rank",
    "short_universe_size",
    "short_risk_flags",
    "short_scoring_rule",
    "mid_score",
    "mid_bucket",
    "mid_action",
    "mid_rank",
    "mid_universe_size",
    "mid_risk_flags",
    "mid_scoring_rule",
    "panel_mode",
    "short_eligible",
    "mid_eligible",
    "exclude_reason",
    "narrative_status",
    "short_rationale_zh",
    "short_rationale_en",
    "mid_rationale_zh",
    "mid_rationale_en",
]


def _finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return number


def _nan_or(value: float | None) -> float:
    return float("nan") if value is None else float(value)


def cross_section_percentile(values: pd.Series) -> pd.Series:
    """0–100 percentile: share of peers strictly below (same convention as horizon PE)."""
    numeric = pd.to_numeric(values, errors="coerce")
    arr = numeric.to_numpy(dtype=float)
    out = np.full(len(arr), np.nan, dtype=float)
    valid = np.isfinite(arr)
    if int(valid.sum()) < 2:
        return pd.Series(out, index=values.index, dtype=float)
    v = arr[valid]
    # count(v_j < v_i) / n
    pcts = (v[None, :] < v[:, None]).sum(axis=1).astype(float) / float(len(v)) * 100.0
    out[valid] = pcts
    return pd.Series(out, index=values.index, dtype=float)


def rank_to_score(rank: Any, universe_size: Any) -> float | None:
    """Map 1-best rank into 0–100 (higher is better)."""
    r = _finite(rank)
    n = _finite(universe_size)
    if r is None or n is None or r <= 0 or n < 2:
        return None
    return float(max(0.0, min(100.0, 100.0 * (1.0 - (r - 1.0) / (n - 1.0)))))


def stage_to_score(stage_hint: Any) -> float:
    key = str(stage_hint or "").strip().lower()
    return float(STAGE_SCORE.get(key, 40.0))


def stance_from_score(score: float | None) -> str:
    if score is None or not math.isfinite(score):
        return "unavailable"
    if score >= 65.0:
        return "strong"
    if score >= 35.0:
        return "neutral"
    return "weak"


def overall_band(score: float | None) -> str:
    if score is None or not math.isfinite(score):
        return "mixed"
    if score >= 70.0:
        return "expansion"
    if score >= 55.0:
        return "constructive"
    if score >= 40.0:
        return "mixed"
    if score >= 25.0:
        return "cooling"
    return "stress"


def _weighted_mean(parts: list[tuple[float | None, float]]) -> tuple[float | None, int]:
    total_w = 0.0
    acc = 0.0
    used = 0
    for value, weight in parts:
        if value is None or not math.isfinite(value) or weight <= 0:
            continue
        acc += float(value) * float(weight)
        total_w += float(weight)
        used += 1
    if used == 0 or total_w <= 0:
        return None, 0
    return acc / total_w, used


def _bucket_from_score(score: float | None, *, attack: float = 70.0, balanced: float = 55.0, watch: float = 40.0) -> str:
    if score is None or not math.isfinite(score):
        return "unavailable"
    if score >= attack:
        return "attack"
    if score >= balanced:
        return "balanced"
    if score >= watch:
        return "watch"
    return "avoid"


def _short_action(bucket: str) -> str:
    return {
        "attack": "momentum_follow",
        "balanced": "accumulate_watch",
        "watch": "accumulate_watch",
        "avoid": "stay_sidelines",
        "unavailable": "stay_sidelines",
    }.get(bucket, "stay_sidelines")


def _mid_action(bucket: str) -> str:
    return {
        "attack": "quality_accumulate",
        "balanced": "trend_hold",
        "watch": "valuation_caution",
        "avoid": "de_risk",
        "unavailable": "de_risk",
    }.get(bucket, "de_risk")


def _panel_mode(short_bucket: str, mid_bucket: str) -> str:
    if short_bucket == "unavailable" and mid_bucket == "unavailable":
        return "unavailable"
    if short_bucket == "attack" and mid_bucket == "avoid":
        return "tactical_only"
    if short_bucket == "avoid" and mid_bucket == "attack":
        return "dip_watch"
    if short_bucket == "attack" and mid_bucket == "attack":
        return "aligned_bullish"
    if short_bucket == "avoid" and mid_bucket == "avoid":
        return "aligned_bearish"
    return "mixed"


def _merge_theme_horizon(theme_df: pd.DataFrame, horizon_df: pd.DataFrame) -> pd.DataFrame:
    theme = theme_df.copy()
    for col in JOIN_KEYS + ["link_key"]:
        if col in theme.columns:
            theme[col] = theme[col].astype(str)

    if horizon_df is None or horizon_df.empty:
        merged = theme.copy()
        for col in (
            "pe_percentile_cross_section",
            "pe_percentile_trailing_252d",
            "relative_strength_60d",
            "relative_strength_120d",
            "risk_adjusted_60d",
            "risk_adjusted_120d",
            "max_drawdown_120d_pct",
            "return_60d_pct",
            "return_120d_pct",
            "revenue_yoy_avg_4q_pct",
            "industry_revenue_yoy_pct",
            "industry_net_profit_yoy_pct",
            "fin_status",
            "row_status",
            "stage_hint",
        ):
            if col not in merged.columns:
                merged[col] = np.nan
        merged = merged.rename(columns={"row_status": "horizon_row_status"})
        if "horizon_row_status" not in merged.columns:
            merged["horizon_row_status"] = ""
        return merged

    horizon = horizon_df.copy()
    for col in JOIN_KEYS + ["link_key"]:
        if col in horizon.columns:
            horizon[col] = horizon[col].astype(str)

    keep = [
        c
        for c in (
            *JOIN_KEYS,
            "pe_percentile_cross_section",
            "pe_percentile_trailing_252d",
            "relative_strength_60d",
            "relative_strength_120d",
            "risk_adjusted_60d",
            "risk_adjusted_120d",
            "max_drawdown_120d_pct",
            "return_60d_pct",
            "return_120d_pct",
            "revenue_yoy_avg_4q_pct",
            "industry_revenue_yoy_pct",
            "industry_net_profit_yoy_pct",
            "fin_status",
            "row_status",
            "stage_hint",
            "fin_quarters_available",
        )
        if c in horizon.columns
    ]
    horizon = horizon[keep].rename(
        columns={
            "row_status": "horizon_row_status",
            "stage_hint": "horizon_stage_hint",
            "industry_revenue_yoy_pct": "horizon_revenue_yoy_pct",
            "industry_net_profit_yoy_pct": "horizon_net_profit_yoy_pct",
        }
    )
    merged = theme.merge(horizon, on=JOIN_KEYS, how="left", suffixes=("", "_h"))
    if "link_key_h" in merged.columns:
        merged["link_key"] = merged["link_key"].where(
            merged["link_key"].astype(str).str.len() > 0, merged["link_key_h"]
        )
        merged = merged.drop(columns=["link_key_h"])
    return merged


def _score_group(group: pd.DataFrame) -> pd.DataFrame:
    g = group.copy()
    n = len(g)

    pct_breadth = cross_section_percentile(g["breadth_score"]) if "breadth_score" in g else pd.Series(np.nan, index=g.index)
    pct_vol_exp = (
        cross_section_percentile(g["volume_expansion_pct"])
        if "volume_expansion_pct" in g
        else pd.Series(np.nan, index=g.index)
    )
    pct_new_high = (
        cross_section_percentile(g["new_highs_pct"]) if "new_highs_pct" in g else pd.Series(np.nan, index=g.index)
    )
    pct_ret20 = cross_section_percentile(g["return_20d_pct"]) if "return_20d_pct" in g else pd.Series(np.nan, index=g.index)
    pct_ra20 = (
        cross_section_percentile(g["risk_adjusted_20d"])
        if "risk_adjusted_20d" in g
        else pd.Series(np.nan, index=g.index)
    )
    pct_ret5 = cross_section_percentile(g["return_5d_pct"]) if "return_5d_pct" in g else pd.Series(np.nan, index=g.index)
    pct_rs20 = (
        cross_section_percentile(g["relative_strength_20d"])
        if "relative_strength_20d" in g
        else pd.Series(np.nan, index=g.index)
    )
    pct_rev = (
        cross_section_percentile(g["industry_revenue_yoy_pct"])
        if "industry_revenue_yoy_pct" in g
        else pd.Series(np.nan, index=g.index)
    )
    pct_profit = (
        cross_section_percentile(g["industry_net_profit_yoy_pct"])
        if "industry_net_profit_yoy_pct" in g
        else pd.Series(np.nan, index=g.index)
    )
    avg4q = g["revenue_yoy_avg_4q_pct"] if "revenue_yoy_avg_4q_pct" in g else pd.Series(np.nan, index=g.index)
    if avg4q.isna().all() and "horizon_revenue_yoy_pct" in g.columns:
        avg4q = g["horizon_revenue_yoy_pct"]
    pct_avg4q = cross_section_percentile(avg4q)
    pct_improvers = (
        cross_section_percentile(g["revenue_improvers_pct"])
        if "revenue_improvers_pct" in g
        else pd.Series(np.nan, index=g.index)
    )

    rs_mid = g["relative_strength_120d"] if "relative_strength_120d" in g else pd.Series(np.nan, index=g.index)
    if rs_mid.isna().all() and "relative_strength_60d" in g.columns:
        rs_mid = g["relative_strength_60d"]
    elif "relative_strength_60d" in g.columns:
        rs_mid = rs_mid.fillna(g["relative_strength_60d"])
    pct_rs_mid = cross_section_percentile(rs_mid)

    ra_mid = g["risk_adjusted_120d"] if "risk_adjusted_120d" in g else pd.Series(np.nan, index=g.index)
    if "risk_adjusted_60d" in g.columns:
        ra_mid = ra_mid.fillna(g["risk_adjusted_60d"])
    pct_ra_mid = cross_section_percentile(ra_mid)

    # Shallower drawdown is better: max_drawdown is negative → higher (closer to 0) is better.
    dd = g["max_drawdown_120d_pct"] if "max_drawdown_120d_pct" in g else pd.Series(np.nan, index=g.index)
    pct_dd = cross_section_percentile(dd)

    universe = g["rs_rank_universe_size"] if "rs_rank_universe_size" in g else pd.Series(n, index=g.index)
    rot_scores = [
        rank_to_score(rank, size)
        for rank, size in zip(g.get("rotation_rank", pd.Series(np.nan, index=g.index)), universe, strict=False)
    ]
    rot_series = pd.Series(rot_scores, index=g.index, dtype=float)

    streak_scores = []
    for raw in g.get("up_streak_days", pd.Series(0, index=g.index)):
        days = _finite(raw) or 0.0
        streak_scores.append(float(max(0.0, min(100.0, days / 5.0 * 100.0))))
    streak_series = pd.Series(streak_scores, index=g.index, dtype=float)

    stage_theme = g["stage_hint"] if "stage_hint" in g else pd.Series("", index=g.index)
    if "horizon_stage_hint" in g.columns:
        stage_theme = stage_theme.where(stage_theme.astype(str).str.len() > 0, g["horizon_stage_hint"])
    stage_series = stage_theme.map(stage_to_score)

    pe_cs = g["pe_percentile_cross_section"] if "pe_percentile_cross_section" in g else pd.Series(np.nan, index=g.index)
    pe_tr = (
        g["pe_percentile_trailing_252d"] if "pe_percentile_trailing_252d" in g else pd.Series(np.nan, index=g.index)
    )
    val_safety = []
    for cs, tr in zip(pe_cs, pe_tr, strict=False):
        cs_v = _finite(cs)
        tr_v = _finite(tr)
        parts: list[tuple[float | None, float]] = []
        if cs_v is not None:
            parts.append((100.0 - cs_v, 0.70))
        if tr_v is not None:
            parts.append((100.0 - tr_v, 0.30))
        score, _ = _weighted_mean(parts)
        val_safety.append(score)
    val_series = pd.Series(val_safety, index=g.index, dtype=float)

    # theme_state confirmation_score is already 0–100 (ups/available*100).
    conf = pd.to_numeric(g.get("confirmation_score", pd.Series(np.nan, index=g.index)), errors="coerce")
    conf = conf.clip(lower=0.0, upper=100.0)

    radar_rows: list[dict[str, Any]] = []
    advice_rows: list[dict[str, Any]] = []

    for idx in g.index:
        row = g.loc[idx]
        capital, _ = _weighted_mean(
            [
                (_finite(pct_breadth.loc[idx]), 0.50),
                (_finite(pct_vol_exp.loc[idx]), 0.25),
                (_finite(pct_new_high.loc[idx]), 0.25),
            ]
        )
        technical, _ = _weighted_mean(
            [
                (_finite(pct_ret20.loc[idx]), 0.40),
                (_finite(pct_ra20.loc[idx]), 0.30),
                (_finite(pct_ret5.loc[idx]), 0.20),
                (_finite(streak_series.loc[idx]), 0.10),
            ]
        )
        relative, _ = _weighted_mean(
            [
                (_finite(rot_series.loc[idx]), 0.50),
                (_finite(pct_rs20.loc[idx]), 0.30),
                (_finite(conf.loc[idx]), 0.20),
            ]
        )
        valuation = _finite(val_series.loc[idx])
        fundamental, _ = _weighted_mean(
            [
                (_finite(pct_rev.loc[idx]), 0.35),
                (_finite(pct_profit.loc[idx]), 0.25),
                (_finite(pct_avg4q.loc[idx]), 0.20),
                (_finite(stage_series.loc[idx]), 0.10),
                (_finite(pct_improvers.loc[idx]), 0.10),
            ]
        )

        overall, axes_available = _weighted_mean(
            [
                (capital, RADAR_AXIS_WEIGHTS["capital_heat"]),
                (technical, RADAR_AXIS_WEIGHTS["technical_momentum"]),
                (relative, RADAR_AXIS_WEIGHTS["relative_strength"]),
                (valuation, RADAR_AXIS_WEIGHTS["valuation_safety"]),
                (fundamental, RADAR_AXIS_WEIGHTS["fundamental_trend"]),
            ]
        )
        # axes_available from weighted_mean counts non-null parts
        theme_status = str(row.get("row_status") or "")
        horizon_status = str(row.get("horizon_row_status") or "")
        eligible = int(_finite(row.get("eligible_count")) or 0)
        if axes_available >= 4 and theme_status == "ok" and eligible >= MIN_ELIGIBLE_COUNT:
            confidence = "high"
        elif axes_available >= 3 or theme_status == "partial":
            confidence = "medium"
        else:
            confidence = "low"

        rev_yoy = _finite(row.get("industry_revenue_yoy_pct"))
        if rev_yoy is None:
            rev_yoy = _finite(row.get("horizon_revenue_yoy_pct"))

        radar_rows.append(
            {
                "trade_date": str(row.get("trade_date") or ""),
                "market": str(row.get("market") or ""),
                "scope": str(row.get("scope") or "L3"),
                "level1_id": str(row.get("level1_id") or ""),
                "level2_id": str(row.get("level2_id") or ""),
                "level3_id": str(row.get("level3_id") or ""),
                "link_key": str(row.get("link_key") or ""),
                "overall_score": _nan_or(overall),
                "overall_band": overall_band(overall),
                "confidence": confidence,
                "axes_available": int(axes_available),
                "scoring_rule": RADAR_RULE,
                "score_capital_heat": _nan_or(capital),
                "score_technical_momentum": _nan_or(technical),
                "score_relative_strength": _nan_or(relative),
                "score_valuation_safety": _nan_or(valuation),
                "score_fundamental_trend": _nan_or(fundamental),
                "stance_capital_heat": stance_from_score(capital),
                "stance_technical_momentum": stance_from_score(technical),
                "stance_relative_strength": stance_from_score(relative),
                "stance_valuation_safety": stance_from_score(valuation),
                "stance_fundamental_trend": stance_from_score(fundamental),
                "raw_breadth_score": _nan_or(_finite(row.get("breadth_score"))),
                "raw_rotation_rank": _nan_or(_finite(row.get("rotation_rank"))),
                "raw_rs_20d": _nan_or(_finite(row.get("relative_strength_20d"))),
                "raw_pe_percentile_cs": _nan_or(_finite(row.get("pe_percentile_cross_section"))),
                "raw_revenue_yoy_pct": _nan_or(rev_yoy),
                "raw_stage_hint": str(stage_theme.loc[idx] or ""),
                "raw_confirmation_score": _nan_or(_finite(row.get("confirmation_score"))),
                "eligible_count": eligible,
                "theme_row_status": theme_status,
                "horizon_row_status": horizon_status,
                "narrative_status": "empty",
                "overall_label_zh": "",
                "overall_label_en": "",
                "overall_summary_zh": "",
                "overall_summary_en": "",
            }
        )

        short_eligible = theme_status in {"ok", "partial"} and eligible >= MIN_ELIGIBLE_COUNT
        short_score, _ = _weighted_mean(
            [
                (_finite(rot_series.loc[idx]), SHORT_SCORE_WEIGHTS["rotation"]),
                (_finite(pct_breadth.loc[idx]), SHORT_SCORE_WEIGHTS["breadth"]),
                (_finite(conf.loc[idx]), SHORT_SCORE_WEIGHTS["confirmation"]),
                (_finite(pct_rs20.loc[idx]), SHORT_SCORE_WEIGHTS["rs_20d"]),
                (_finite(stage_series.loc[idx]), SHORT_SCORE_WEIGHTS["stage"]),
            ]
        )
        if not short_eligible:
            short_score = None

        mid_hist_ok = horizon_status in {"ok", "partial"}
        has_mid_ret = _finite(row.get("return_120d_pct")) is not None or _finite(row.get("return_60d_pct")) is not None
        mid_eligible = mid_hist_ok and has_mid_ret
        mid_rev = _finite(pct_rev.loc[idx])
        if mid_rev is None:
            mid_rev = _finite(pct_avg4q.loc[idx])
        mid_score, _ = _weighted_mean(
            [
                (_finite(pct_rs_mid.loc[idx]), MID_SCORE_WEIGHTS["rs_mid"]),
                (_finite(pct_ra_mid.loc[idx]), MID_SCORE_WEIGHTS["risk_adj"]),
                (mid_rev, MID_SCORE_WEIGHTS["revenue_yoy"]),
                (valuation, MID_SCORE_WEIGHTS["valuation"]),
                (_finite(pct_dd.loc[idx]), MID_SCORE_WEIGHTS["drawdown"]),
                (_finite(stage_series.loc[idx]), MID_SCORE_WEIGHTS["stage"]),
            ]
        )
        if not mid_eligible:
            mid_score = None

        short_bucket = _bucket_from_score(short_score)
        mid_bucket = _bucket_from_score(mid_score)
        # Mid attack requires usable fundamentals when available.
        fin_status = str(row.get("fin_status") or "")
        if mid_bucket == "attack" and fin_status not in {"", "ok"} and mid_score is not None and mid_score < 80.0:
            mid_bucket = "balanced"

        short_flags: list[str] = []
        breadth_v = _finite(row.get("breadth_score"))
        if breadth_v is not None and breadth_v < 20.0:
            short_flags.append("weak_breadth")
        vol20 = _finite(row.get("volatility_20d_pct"))
        if vol20 is not None and _finite(pct_ret20.loc[idx]) is not None:
            # flag if vol is high vs peers via inverse: use raw threshold
            if vol20 >= 40.0:
                short_flags.append("high_volatility")
        conf_v = _finite(row.get("confirmation_score"))
        if conf_v is not None and conf_v <= 0.0:
            short_flags.append("cross_market_divergence")
        down_streak = _finite(row.get("down_streak_days")) or 0.0
        if down_streak >= 3:
            short_flags.append("down_streak_ge_3")

        mid_flags: list[str] = []
        if not mid_eligible:
            mid_flags.append("insufficient_history")
        if fin_status and fin_status != "ok":
            mid_flags.append("weak_fundamentals")
        pe_cs_v = _finite(row.get("pe_percentile_cross_section"))
        if pe_cs_v is not None and pe_cs_v >= 80.0:
            mid_flags.append("rich_valuation")
        dd_v = _finite(row.get("max_drawdown_120d_pct"))
        if dd_v is not None and dd_v <= -35.0:
            mid_flags.append("deep_drawdown")

        exclude_reason = ""
        if not short_eligible and not mid_eligible:
            if theme_status and theme_status not in {"ok", "partial"}:
                exclude_reason = "insufficient_sample"
            elif not mid_hist_ok:
                exclude_reason = "insufficient_history"
            else:
                exclude_reason = "ineligible"

        advice_rows.append(
            {
                "trade_date": str(row.get("trade_date") or ""),
                "market": str(row.get("market") or ""),
                "scope": str(row.get("scope") or "L3"),
                "level1_id": str(row.get("level1_id") or ""),
                "level2_id": str(row.get("level2_id") or ""),
                "level3_id": str(row.get("level3_id") or ""),
                "link_key": str(row.get("link_key") or ""),
                "short_score": _nan_or(short_score),
                "short_bucket": short_bucket,
                "short_action": _short_action(short_bucket),
                "short_rank": 0,
                "short_universe_size": 0,
                "short_risk_flags": json.dumps(short_flags, ensure_ascii=False, separators=(",", ":")),
                "short_scoring_rule": SHORT_ADVICE_RULE,
                "mid_score": _nan_or(mid_score),
                "mid_bucket": mid_bucket,
                "mid_action": _mid_action(mid_bucket),
                "mid_rank": 0,
                "mid_universe_size": 0,
                "mid_risk_flags": json.dumps(mid_flags, ensure_ascii=False, separators=(",", ":")),
                "mid_scoring_rule": MID_ADVICE_RULE,
                "panel_mode": _panel_mode(short_bucket, mid_bucket),
                "short_eligible": bool(short_eligible),
                "mid_eligible": bool(mid_eligible),
                "exclude_reason": exclude_reason,
                "narrative_status": "empty",
                "short_rationale_zh": "",
                "short_rationale_en": "",
                "mid_rationale_zh": "",
                "mid_rationale_en": "",
            }
        )

    radar_df = pd.DataFrame(radar_rows)
    advice_df = pd.DataFrame(advice_rows)

    # Ranks within the day/market group.
    short_mask = advice_df["short_eligible"] & advice_df["short_score"].notna()
    mid_mask = advice_df["mid_eligible"] & advice_df["mid_score"].notna()
    short_n = int(short_mask.sum())
    mid_n = int(mid_mask.sum())
    advice_df["short_universe_size"] = short_n
    advice_df["mid_universe_size"] = mid_n
    if short_n > 0:
        ranks = advice_df.loc[short_mask, "short_score"].rank(ascending=False, method="first")
        advice_df.loc[short_mask, "short_rank"] = ranks.astype(int)
    if mid_n > 0:
        ranks = advice_df.loc[mid_mask, "mid_score"].rank(ascending=False, method="first")
        advice_df.loc[mid_mask, "mid_rank"] = ranks.astype(int)

    return radar_df, advice_df


def compute_sector_radar_advice_frames(
    *,
    theme_state_daily: pd.DataFrame,
    sector_horizon_metrics: pd.DataFrame | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Build radar + advice daily frames aligned to theme_state keys."""
    if theme_state_daily is None or theme_state_daily.empty:
        return (
            pd.DataFrame(columns=SECTOR_HEALTH_RADAR_COLUMNS),
            pd.DataFrame(columns=SECTOR_ADVICE_DAILY_COLUMNS),
        )

    horizon = sector_horizon_metrics if sector_horizon_metrics is not None else pd.DataFrame()
    merged = _merge_theme_horizon(theme_state_daily, horizon)
    # Prefer L3 scope rows when present.
    if "scope" in merged.columns:
        l3 = merged[merged["scope"].astype(str) == "L3"]
        if not l3.empty:
            merged = l3

    radar_parts: list[pd.DataFrame] = []
    advice_parts: list[pd.DataFrame] = []
    for _, group in merged.groupby(["trade_date", "market"], sort=False):
        radar_part, advice_part = _score_group(group)
        radar_parts.append(radar_part)
        advice_parts.append(advice_part)

    radar_df = (
        pd.concat(radar_parts, ignore_index=True)
        if radar_parts
        else pd.DataFrame(columns=SECTOR_HEALTH_RADAR_COLUMNS)
    )
    advice_df = (
        pd.concat(advice_parts, ignore_index=True)
        if advice_parts
        else pd.DataFrame(columns=SECTOR_ADVICE_DAILY_COLUMNS)
    )
    radar_df = radar_df.reindex(columns=SECTOR_HEALTH_RADAR_COLUMNS)
    advice_df = advice_df.reindex(columns=SECTOR_ADVICE_DAILY_COLUMNS)
    return radar_df, advice_df
