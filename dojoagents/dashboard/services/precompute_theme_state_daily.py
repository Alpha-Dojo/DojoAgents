"""Phase B: precompute industry theme-state daily snapshots from Phase A sector data."""

from __future__ import annotations

import asyncio
import hashlib
import json
import math
import shutil
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from dojoagents.dashboard.services.benchmark_store import DEFAULT_BENCHMARKS
from dojoagents.dashboard.services.market_sector_lead import concept_code_for, link_key_from_concept_code, slugify
from dojoagents.dashboard.services.precompute_sector_daily import (
    CONSTITUENTS_FILE,
    MANIFEST_FILE as PHASE_A_MANIFEST_FILE,
    PRECOMPUTE_DIR as PHASE_A_DIR,
    SECTOR_DAILY_FILE,
    TICKER_DAILY_FILE,
)
from dojoagents.dashboard.services.precompute_sector_horizon import (
    MAX_FUNDAMENTAL_PERIODS,
    SECTOR_HORIZON_METRICS_COLUMNS,
    SECTOR_HORIZON_METRICS_FILE,
    compute_sector_horizon_metrics_frame,
)
from dojoagents.dashboard.services.precompute_sector_radar_advice import (
    MID_ADVICE_RULE,
    MID_SCORE_WEIGHTS,
    RADAR_AXIS_WEIGHTS,
    RADAR_RULE,
    SECTOR_ADVICE_DAILY_COLUMNS,
    SECTOR_ADVICE_DAILY_FILE,
    SECTOR_HEALTH_RADAR_COLUMNS,
    SECTOR_HEALTH_RADAR_FILE,
    SHORT_ADVICE_RULE,
    SHORT_SCORE_WEIGHTS,
    compute_sector_radar_advice_frames,
)
from dojoagents.dashboard.services.stock_quote_filter import (
    filter_constituents_frame_by_ticker_cap_min,
    ticker_market_cap_min,
)
from dojoagents.dashboard.services.theme_state_metrics import (
    CONFIRMATION_WINDOW_DAYS,
    HIGH_LOOKBACK_DAYS,
    MIN_ELIGIBLE_COUNT,
    MOMENTUM_WINDOWS,
    ROLE_FILTER,
    ROTATION_BREADTH_CENTER,
    ROTATION_BREADTH_MULT_MAX,
    ROTATION_BREADTH_MULT_MIN,
    ROTATION_RANK_RULE,
    ROTATION_RS_WEIGHTS,
    STAGE_HINT_RULE,
    VOLUME_LOOKBACK_DAYS,
    VOLUME_MULTIPLIER,
    aggregate_fundamentals_lite,
    compute_breadth_for_day,
    dedupe_universe_members,
    extract_quarter_metrics,
    list_report_period_keys,
    nan_or,
    risk_adjusted,
    role_counts,
    rotation_score_frame,
    streak_days,
    window_return_pct,
    window_volatility_pct,
)
from dojoagents.logging import LOGGER

ProgressCallback = Callable[[str, int, int], None]

# Legacy standalone dir (read fallback only). New publishes write into PHASE_A_DIR.
THEME_STATE_DIR = "dojo_theme_state_precomputed"
THEME_STATE_DAILY_FILE = "theme_state_daily.parquet"
MARKET_BENCHMARK_DAILY_FILE = "market_benchmark_daily.parquet"
FUNDAMENTALS_PERIOD_FILE = "fundamentals_period.parquet"
MANIFEST_FILE = "manifest.json"
# Unified bundle schema inside dojo_sector_precomputed (Phase A + theme + horizon + radar/advice).
SCHEMA_VERSION = "5"
THEME_STATE_RULES_VERSION = "2"
SUPPORTED_PHASE_A_SCHEMA_VERSIONS = frozenset({"3", "4", "5"})
PHASE_A_BASE_FILES = (CONSTITUENTS_FILE, TICKER_DAILY_FILE, SECTOR_DAILY_FILE)

THEME_STATE_DAILY_COLUMNS = [
    "trade_date",
    "market",
    "scope",
    "level1_id",
    "level2_id",
    "level3_id",
    "link_key",
    "eligible_count",
    "primary_count",
    "secondary_count",
    "quoted_count",
    "total_market_cap",
    "min_market_cap",
    "role_filter",
    "coverage_ratio",
    "row_status",
    "advancers_pct",
    "volume_expansion_pct",
    "new_highs_pct",
    "breadth_score",
    "advancers_count",
    "decliners_count",
    "unchanged_count",
    "volume_expansion_count",
    "new_highs_count",
    "breadth_sample_count",
    "volume_lookback_days",
    "volume_multiplier",
    "high_lookback_days",
    "high_effective_lookback_days",
    "return_5d_pct",
    "return_10d_pct",
    "return_20d_pct",
    "risk_adjusted_5d",
    "risk_adjusted_10d",
    "risk_adjusted_20d",
    "volatility_20d_pct",
    "up_streak_days",
    "down_streak_days",
    "market_return_5d_pct",
    "market_return_10d_pct",
    "market_return_20d_pct",
    "relative_strength_5d",
    "relative_strength_10d",
    "relative_strength_20d",
    "rs_rank_5d",
    "rs_rank_universe_size",
    "rotation_score",
    "rotation_rank",
    "benchmark_id",
    "benchmark_source",
    "confirmation_window_days",
    "confirmation_markets_available",
    "confirmation_markets_up",
    "confirmation_markets_down",
    "confirmation_score",
    "fin_status",
    "fin_report_period",
    "fin_prior_year_period",
    "fin_sample_count",
    "fin_coverage_ratio",
    "industry_revenue",
    "industry_revenue_prior_year",
    "industry_revenue_yoy_pct",
    "industry_revenue_yoy_prior_pct",
    "industry_revenue_accel_pp",
    "revenue_improvers_count",
    "revenue_improvers_pct",
    "industry_net_profit",
    "industry_net_profit_yoy_pct",
    "profit_improvers_count",
    "profit_improvers_pct",
    "industry_net_margin_pct",
    "industry_net_margin_change_pp",
    "stage_hint",
    "stage_hint_rule",
]

MARKET_BENCHMARK_DAILY_COLUMNS = [
    "trade_date",
    "market",
    "benchmark_id",
    "benchmark_source",
    "daily_return_pct",
    "return_5d_pct",
    "return_10d_pct",
    "return_20d_pct",
]

FUNDAMENTALS_PERIOD_COLUMNS = [
    "market",
    "scope",
    "level1_id",
    "level2_id",
    "level3_id",
    "link_key",
    "report_period_key",
    "fin_status",
    "fin_report_period",
    "fin_prior_year_period",
    "fin_sample_count",
    "fin_coverage_ratio",
    "industry_revenue",
    "industry_revenue_prior_year",
    "industry_revenue_yoy_pct",
    "industry_revenue_yoy_prior_pct",
    "industry_revenue_accel_pp",
    "revenue_improvers_count",
    "revenue_improvers_pct",
    "industry_net_profit",
    "industry_net_profit_yoy_pct",
    "profit_improvers_count",
    "profit_improvers_pct",
    "industry_net_margin_pct",
    "industry_net_margin_change_pp",
    "stage_hint",
    "stage_hint_rule",
    "eligible_count",
    "computed_at",
]


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json_list(values: list[str]) -> str:
    return json.dumps(values, ensure_ascii=False, separators=(",", ":"))


def phase_a_dir(data_root: Path) -> Path:
    return data_root.expanduser().resolve() / PHASE_A_DIR


def load_phase_a_snapshot(data_root: Path) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    root = phase_a_dir(data_root)
    manifest_path = root / PHASE_A_MANIFEST_FILE
    if not manifest_path.exists():
        raise FileNotFoundError(f"Phase A manifest missing: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    schema = str(manifest.get("schema_version") or "")
    if schema not in SUPPORTED_PHASE_A_SCHEMA_VERSIONS:
        raise ValueError(f"Unsupported Phase A schema_version={schema!r}; supported={sorted(SUPPORTED_PHASE_A_SCHEMA_VERSIONS)}")
    # Unified schema 4/5 embeds original Phase A metadata under phase_a.
    if schema in {"4", "5"} and isinstance(manifest.get("phase_a"), dict):
        nested = dict(manifest.get("phase_a") or {})
        nested.setdefault("schema_version", nested.get("schema_version") or schema)
        nested.setdefault("files", (manifest.get("files") or {}))
        nested.setdefault("window_start", manifest.get("window_start"))
        nested.setdefault("window_end", manifest.get("window_end"))
        nested.setdefault("latest_trade_date_by_market", manifest.get("latest_trade_date_by_market"))
        manifest = nested

    constituents = pd.read_parquet(root / CONSTITUENTS_FILE)
    ticker_daily = pd.read_parquet(root / TICKER_DAILY_FILE)
    sector_daily = pd.read_parquet(root / SECTOR_DAILY_FILE)
    for frame, cols in (
        (constituents, ("market", "ticker", "level1_id", "level2_id", "level3_id", "role")),
        (ticker_daily, ("market", "ticker", "trade_date")),
        (sector_daily, ("market", "scope", "level1_id", "level2_id", "level3_id", "trade_date")),
    ):
        for col in cols:
            if col in frame.columns:
                frame[col] = frame[col].astype(str)

    before = len(constituents)
    constituents = filter_constituents_frame_by_ticker_cap_min(constituents)
    dropped = before - len(constituents)
    if dropped:
        LOGGER.warning(
            "Phase B dropped %s Phase A constituents at/below ticker market-cap floor "
            "(rebuild Phase A to permanently purge them).",
            dropped,
        )
        if not ticker_daily.empty and {"market", "ticker"}.issubset(ticker_daily.columns):
            keep = constituents[["market", "ticker"]].drop_duplicates()
            ticker_daily = ticker_daily.merge(keep, on=["market", "ticker"], how="inner")

    files_sha = {
        CONSTITUENTS_FILE: _file_sha256(root / CONSTITUENTS_FILE),
        TICKER_DAILY_FILE: _file_sha256(root / TICKER_DAILY_FILE),
        SECTOR_DAILY_FILE: _file_sha256(root / SECTOR_DAILY_FILE),
    }
    manifest = {**manifest, "_files_sha256": files_sha, "_dir": str(root)}
    return constituents, ticker_daily, sector_daily, manifest


def build_link_key_map(sector_store: Any | None, constituents: pd.DataFrame) -> dict[str, str]:
    """Map level3_id -> link_key (english slug)."""
    out: dict[str, str] = {}
    if sector_store is not None and hasattr(sector_store, "iter_resolved_paths"):
        for path in sector_store.iter_resolved_paths():
            code = concept_code_for("xx", path.level3_zh, path.level3_en, "L3")
            key = link_key_from_concept_code(code) or slugify(path.level3_en or path.level3_zh)
            out[str(path.level3_id)] = key
    for level3_id in constituents["level3_id"].astype(str).unique():
        out.setdefault(str(level3_id), slugify(str(level3_id)))
    return out


def _ensure_volume_column(ticker_daily: pd.DataFrame) -> pd.DataFrame:
    frame = ticker_daily.copy()
    if "volume" not in frame.columns:
        frame["volume"] = np.nan
    return frame


def _build_market_cap_lookup(constituents: pd.DataFrame) -> dict[tuple[str, str], float]:
    deduped = (
        constituents.sort_values(["market", "ticker", "role"])
        .drop_duplicates(subset=["market", "ticker"], keep="first")
    )
    out: dict[tuple[str, str], float] = {}
    for row in deduped.itertuples(index=False):
        cap = float(getattr(row, "market_cap", 0.0) or 0.0)
        out[(str(row.market), str(row.ticker))] = cap
    return out


def _market_daily_returns_from_tickers(
    ticker_daily: pd.DataFrame,
    cap_lookup: dict[tuple[str, str], float],
) -> pd.DataFrame:
    """Cap-weighted market daily returns as benchmark fallback."""
    if ticker_daily.empty:
        return pd.DataFrame(columns=MARKET_BENCHMARK_DAILY_COLUMNS)

    frame = ticker_daily.copy()
    frame["market_cap"] = [
        float(cap_lookup.get((str(m), str(t)), 0.0) or 0.0)
        for m, t in zip(frame["market"], frame["ticker"])
    ]
    frame = frame[(frame["market_cap"] > 0) & frame["daily_return_pct"].notna()]
    if frame.empty:
        return pd.DataFrame(columns=MARKET_BENCHMARK_DAILY_COLUMNS)
    frame["weighted_ret"] = frame["daily_return_pct"].astype(float) * frame["market_cap"]
    grouped = frame.groupby(["market", "trade_date"], sort=True).agg(
        weighted_ret=("weighted_ret", "sum"),
        market_cap=("market_cap", "sum"),
    )
    grouped["daily_return_pct"] = grouped["weighted_ret"] / grouped["market_cap"]
    rows: list[dict[str, Any]] = []
    for market, market_frame in grouped.groupby(level=0, sort=True):
        daily = market_frame["daily_return_pct"].astype(float).tolist()
        dates = [str(d) for d in market_frame.index.get_level_values("trade_date")]
        levels: list[float] = []
        level = 100.0
        for ret in daily:
            if math.isfinite(ret):
                level *= 1.0 + ret / 100.0
            levels.append(level)
        level_s = pd.Series(levels)
        rows.extend(
            {
                "trade_date": dates[idx],
                "market": str(market),
                "benchmark_id": "market_cap_weighted_universe",
                "benchmark_source": "market_cap_weighted_universe",
                "daily_return_pct": daily[idx],
                "return_5d_pct": nan_or(((level_s.iloc[idx] / level_s.iloc[idx - 4]) - 1.0) * 100.0 if idx >= 4 else None),
                "return_10d_pct": nan_or(((level_s.iloc[idx] / level_s.iloc[idx - 9]) - 1.0) * 100.0 if idx >= 9 else None),
                "return_20d_pct": nan_or(((level_s.iloc[idx] / level_s.iloc[idx - 19]) - 1.0) * 100.0 if idx >= 19 else None),
            }
            for idx in range(len(dates))
        )
    return pd.DataFrame(rows)


def _streak_array(values: np.ndarray, *, positive: bool) -> np.ndarray:
    out = np.zeros(len(values), dtype=np.int32)
    streak = 0
    for i, value in enumerate(values):
        if np.isfinite(value) and ((positive and value > 0) or ((not positive) and value < 0)):
            streak += 1
        else:
            streak = 0
        out[i] = streak
    return out


def _apply_rs_ranks(theme_df: pd.DataFrame) -> pd.DataFrame:
    theme_df = theme_df.copy()
    theme_df["rs_rank_5d"] = 0
    theme_df["rs_rank_universe_size"] = 0
    theme_df["rotation_score"] = np.nan
    theme_df["rotation_rank"] = 0

    eligible_5d = theme_df["row_status"].isin(["ok", "partial"]) & theme_df["relative_strength_5d"].notna()
    if bool(eligible_5d.any()):
        theme_df.loc[eligible_5d, "rs_rank_universe_size"] = (
            theme_df.loc[eligible_5d].groupby(["trade_date", "market"], sort=False)["level3_id"].transform("size")
        )
        ordered_5d = theme_df.loc[eligible_5d].sort_values(
            ["trade_date", "market", "relative_strength_5d", "level3_id"],
            ascending=[True, True, False, True],
        )
        ranks_5d = ordered_5d.groupby(["trade_date", "market"], sort=False).cumcount() + 1
        theme_df.loc[ordered_5d.index, "rs_rank_5d"] = ranks_5d.to_numpy()

    eligible_rot = (
        theme_df["row_status"].isin(["ok", "partial"])
        & theme_df["relative_strength_5d"].notna()
        & theme_df["relative_strength_10d"].notna()
        & theme_df["relative_strength_20d"].notna()
    )
    if not bool(eligible_rot.any()):
        return theme_df

    for (_, _), group in theme_df.loc[eligible_rot].groupby(["trade_date", "market"], sort=False):
        scores = rotation_score_frame(
            relative_strength_5d=group["relative_strength_5d"],
            relative_strength_10d=group["relative_strength_10d"],
            relative_strength_20d=group["relative_strength_20d"],
            breadth_score=group["breadth_score"],
            weights=ROTATION_RS_WEIGHTS,
        )
        theme_df.loc[group.index, "rotation_score"] = scores.to_numpy(dtype=float)

    ranked = theme_df.loc[eligible_rot & theme_df["rotation_score"].notna()].sort_values(
        ["trade_date", "market", "rotation_score", "level3_id"],
        ascending=[True, True, False, True],
    )
    ranks = ranked.groupby(["trade_date", "market"], sort=False).cumcount() + 1
    theme_df.loc[ranked.index, "rotation_rank"] = ranks.to_numpy()
    return theme_df


def _apply_confirmation(theme_df: pd.DataFrame) -> pd.DataFrame:
    theme_df = theme_df.copy()
    # One representative return per (trade_date, link_key, market)
    reps = (
        theme_df.sort_values(["trade_date", "link_key", "market", "level3_id"])
        .drop_duplicates(subset=["trade_date", "link_key", "market"], keep="first")
    )
    conf_rows: list[dict[str, Any]] = []
    for (trade_date, link_key), group in reps.groupby(["trade_date", "link_key"], sort=False):
        available: list[str] = []
        ups: list[str] = []
        downs: list[str] = []
        if link_key:
            for row in group.itertuples(index=False):
                ret = float(row.return_5d_pct) if pd.notna(row.return_5d_pct) else None
                if ret is None or not math.isfinite(ret):
                    continue
                market = str(row.market)
                available.append(market)
                if ret > 0:
                    ups.append(market)
                elif ret < 0:
                    downs.append(market)
        score = (len(ups) / len(available) * 100.0) if available else float("nan")
        conf_rows.append(
            {
                "trade_date": trade_date,
                "link_key": link_key,
                "confirmation_markets_available": _json_list(sorted(available)),
                "confirmation_markets_up": _json_list(sorted(ups)),
                "confirmation_markets_down": _json_list(sorted(downs)),
                "confirmation_score": score,
            }
        )
    if not conf_rows:
        return theme_df
    conf_df = pd.DataFrame(conf_rows)
    theme_df = theme_df.drop(
        columns=[
            "confirmation_markets_available",
            "confirmation_markets_up",
            "confirmation_markets_down",
            "confirmation_score",
        ],
        errors="ignore",
    )
    return theme_df.merge(conf_df, on=["trade_date", "link_key"], how="left")


def _benchmark_daily_from_closes(
    closes_by_market: dict[str, pd.DataFrame],
) -> pd.DataFrame:
    """Build benchmark daily frame from {market: DataFrame[trade_date, close, benchmark_id]}."""
    rows: list[dict[str, Any]] = []
    for market, frame in closes_by_market.items():
        if frame is None or frame.empty:
            continue
        sorted_frame = frame.sort_values("trade_date")
        closes = [float(v) for v in sorted_frame["close"].tolist()]
        dates = [str(v) for v in sorted_frame["trade_date"].tolist()]
        benchmark_id = str(sorted_frame.iloc[0].get("benchmark_id") or DEFAULT_BENCHMARKS.get(market, ""))
        daily_rets: list[float] = [float("nan")]
        for idx in range(1, len(closes)):
            prev, cur = closes[idx - 1], closes[idx]
            daily_rets.append(((cur / prev) - 1.0) * 100.0 if prev > 0 else float("nan"))
        for idx, trade_date in enumerate(dates):
            rows.append(
                {
                    "trade_date": trade_date,
                    "market": market,
                    "benchmark_id": benchmark_id,
                    "benchmark_source": "index",
                    "daily_return_pct": daily_rets[idx],
                    "return_5d_pct": nan_or(window_return_pct(closes[: idx + 1], 5)),
                    "return_10d_pct": nan_or(window_return_pct(closes[: idx + 1], 10)),
                    "return_20d_pct": nan_or(window_return_pct(closes[: idx + 1], 20)),
                }
            )
    if not rows:
        return pd.DataFrame(columns=MARKET_BENCHMARK_DAILY_COLUMNS)
    return pd.DataFrame(rows)[MARKET_BENCHMARK_DAILY_COLUMNS]


def _default_fin_payload() -> dict[str, Any]:
    return {
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
    }


def compute_theme_state_frames(
    *,
    constituents: pd.DataFrame,
    ticker_daily: pd.DataFrame,
    sector_daily: pd.DataFrame,
    link_key_by_level3: dict[str, str],
    benchmark_daily: pd.DataFrame | None = None,
    fundamentals_by_theme: (
        dict[tuple[str, str, str, str], list[dict[str, Any]] | dict[str, Any]] | None
    ) = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Compute theme_state_daily, market_benchmark_daily, fundamentals_period frames."""
    ticker_daily = _ensure_volume_column(ticker_daily)
    cap_lookup = _build_market_cap_lookup(constituents)

    if benchmark_daily is None or benchmark_daily.empty:
        benchmark_daily = _market_daily_returns_from_tickers(ticker_daily, cap_lookup)
        benchmark_daily = benchmark_daily[MARKET_BENCHMARK_DAILY_COLUMNS]
    else:
        benchmark_daily = benchmark_daily.copy()
        for col in MARKET_BENCHMARK_DAILY_COLUMNS:
            if col not in benchmark_daily.columns:
                benchmark_daily[col] = np.nan if col.endswith("_pct") else ""

    sector_l3 = sector_daily[sector_daily["scope"].astype(str) == "L3"].copy()
    if start_date:
        sector_l3 = sector_l3[sector_l3["trade_date"] >= start_date]
        ticker_daily = ticker_daily[ticker_daily["trade_date"] >= start_date]
        benchmark_daily = benchmark_daily[benchmark_daily["trade_date"] >= start_date]
    if end_date:
        sector_l3 = sector_l3[sector_l3["trade_date"] <= end_date]
        ticker_daily = ticker_daily[ticker_daily["trade_date"] <= end_date]
        benchmark_daily = benchmark_daily[benchmark_daily["trade_date"] <= end_date]

    if sector_l3.empty:
        raise ValueError("No L3 sector_daily rows available for theme-state precompute.")

    sector_l3 = sector_l3.sort_values(["market", "level1_id", "level2_id", "level3_id", "trade_date"])
    bench_lookup = {
        (str(row.market), str(row.trade_date)): row
        for row in benchmark_daily.itertuples(index=False)
    }

    # Precompute market panels + rolling helpers once.
    ticker_panels: dict[str, dict[str, Any]] = {}
    for market, market_td in ticker_daily.groupby("market", sort=True):
        ret_pivot = (
            market_td.pivot_table(index="trade_date", columns="ticker", values="daily_return_pct", aggfunc="last")
            .sort_index()
        )
        close_pivot = (
            market_td.pivot_table(index="trade_date", columns="ticker", values="close", aggfunc="last")
            .sort_index()
            .reindex(index=ret_pivot.index, columns=ret_pivot.columns)
        )
        vol_pivot = (
            market_td.pivot_table(index="trade_date", columns="ticker", values="volume", aggfunc="last")
            .sort_index()
            .reindex(index=ret_pivot.index, columns=ret_pivot.columns)
        )
        ticker_panels[str(market)] = {
            "ret": ret_pivot,
            "close": close_pivot,
            "vol": vol_pivot,
            "vol_ma": vol_pivot.rolling(VOLUME_LOOKBACK_DAYS, min_periods=1).mean(),
            "close_high": close_pivot.rolling(HIGH_LOOKBACK_DAYS, min_periods=1).max(),
            "dates": [str(d) for d in ret_pivot.index],
        }

    theme_parts: list[pd.DataFrame] = []
    path_cols = ["level1_id", "level2_id", "level3_id"]
    empty_fin = _default_fin_payload()

    for (market, level1_id, level2_id, level3_id), members in constituents.groupby(
        ["market", *path_cols], sort=True
    ):
        market_s = str(market)
        panel = ticker_panels.get(market_s)
        if panel is None:
            continue
        eligible_count, primary_count, secondary_count = role_counts(members)
        universe = dedupe_universe_members(members)
        tickers = [str(t) for t in universe["ticker"].tolist() if str(t) in panel["ret"].columns]
        if not tickers:
            continue
        total_cap = float(pd.to_numeric(universe["market_cap"], errors="coerce").fillna(0).sum())
        min_cap = ticker_market_cap_min(market_s)
        link_key = link_key_by_level3.get(str(level3_id), slugify(str(level3_id)))

        theme_sector = sector_l3[
            (sector_l3["market"] == market_s)
            & (sector_l3["level1_id"] == str(level1_id))
            & (sector_l3["level2_id"] == str(level2_id))
            & (sector_l3["level3_id"] == str(level3_id))
        ]
        if theme_sector.empty:
            continue

        dates = theme_sector["trade_date"].astype(str).to_numpy()
        levels = theme_sector["index_level"].astype(float).to_numpy()
        daily_rets = theme_sector["daily_return_pct"].astype(float).to_numpy()
        level_s = pd.Series(levels)
        ret_s = pd.Series(daily_rets)
        ret_5 = ((level_s / level_s.shift(4)) - 1.0) * 100.0
        ret_10 = ((level_s / level_s.shift(9)) - 1.0) * 100.0
        ret_20 = ((level_s / level_s.shift(19)) - 1.0) * 100.0
        vol_5 = ret_s.rolling(5, min_periods=2).std(ddof=1) * math.sqrt(5)
        vol_10 = ret_s.rolling(10, min_periods=2).std(ddof=1) * math.sqrt(10)
        vol_20 = ret_s.rolling(20, min_periods=2).std(ddof=1) * math.sqrt(20)
        up_streak = _streak_array(daily_rets, positive=True)
        down_streak = _streak_array(daily_rets, positive=False)

        # Align member panels onto theme dates.
        ret_m = panel["ret"].reindex(index=dates, columns=tickers)
        vol_m = panel["vol"].reindex(index=dates, columns=tickers)
        vol_ma_m = panel["vol_ma"].reindex(index=dates, columns=tickers)
        close_m = panel["close"].reindex(index=dates, columns=tickers)
        high_m = panel["close_high"].reindex(index=dates, columns=tickers)

        valid = ret_m.notna()
        advancers = (ret_m > 0) & valid
        decliners = (ret_m < 0) & valid
        unchanged = (ret_m == 0) & valid
        sample = valid.sum(axis=1)
        volume_valid = vol_m.notna() & vol_ma_m.notna() & (vol_ma_m > 0)
        volume_exp = (vol_m > (vol_ma_m * VOLUME_MULTIPLIER)) & volume_valid
        volume_sample = volume_valid.sum(axis=1)
        high_valid = close_m.notna() & high_m.notna() & (high_m > 0)
        new_highs = (close_m >= high_m) & high_valid
        high_sample = high_valid.sum(axis=1)

        advancers_pct = (advancers.sum(axis=1) / sample * 100.0).where(sample > 0)
        volume_pct = (volume_exp.sum(axis=1) / volume_sample * 100.0).where(volume_sample > 0)
        new_highs_pct = (new_highs.sum(axis=1) / high_sample * 100.0).where(high_sample > 0)
        component_count = advancers_pct.notna().astype(int) + volume_pct.notna().astype(int) + new_highs_pct.notna().astype(int)
        breadth_score = (
            advancers_pct.fillna(0) + volume_pct.fillna(0) + new_highs_pct.fillna(0)
        ) / component_count.replace(0, np.nan)

        fin_payload = dict(
            _latest_fundamentals_payload(
                (fundamentals_by_theme or {}).get(
                    (market_s, str(level1_id), str(level2_id), str(level3_id))
                )
            )
            or empty_fin
        )
        if fin_payload.get("fin_status") == "ok" and eligible_count > 0:
            fin_payload["fin_coverage_ratio"] = nan_or(
                float(fin_payload.get("fin_sample_count") or 0) / eligible_count
            )

        n = len(dates)
        part = pd.DataFrame(
            {
                "trade_date": dates,
                "market": market_s,
                "scope": "L3",
                "level1_id": str(level1_id),
                "level2_id": str(level2_id),
                "level3_id": str(level3_id),
                "link_key": link_key,
                "eligible_count": eligible_count,
                "primary_count": primary_count,
                "secondary_count": secondary_count,
                "quoted_count": sample.astype(int).to_numpy(),
                "total_market_cap": total_cap,
                "min_market_cap": float(min_cap) if min_cap is not None else float("nan"),
                "role_filter": ROLE_FILTER,
                "coverage_ratio": (sample / eligible_count).to_numpy() if eligible_count else np.full(n, np.nan),
                "advancers_pct": advancers_pct.to_numpy(dtype=float),
                "volume_expansion_pct": volume_pct.to_numpy(dtype=float),
                "new_highs_pct": new_highs_pct.to_numpy(dtype=float),
                "breadth_score": breadth_score.to_numpy(dtype=float),
                "advancers_count": advancers.sum(axis=1).astype(int).to_numpy(),
                "decliners_count": decliners.sum(axis=1).astype(int).to_numpy(),
                "unchanged_count": unchanged.sum(axis=1).astype(int).to_numpy(),
                "volume_expansion_count": volume_exp.sum(axis=1).astype(int).to_numpy(),
                "new_highs_count": np.where(high_sample.to_numpy() > 0, new_highs.sum(axis=1).to_numpy(), -1),
                "breadth_sample_count": sample.astype(int).to_numpy(),
                "volume_lookback_days": VOLUME_LOOKBACK_DAYS,
                "volume_multiplier": VOLUME_MULTIPLIER,
                "high_lookback_days": HIGH_LOOKBACK_DAYS,
                "high_effective_lookback_days": np.minimum(
                    np.arange(1, n + 1),
                    HIGH_LOOKBACK_DAYS,
                ),
                "return_5d_pct": ret_5.to_numpy(dtype=float),
                "return_10d_pct": ret_10.to_numpy(dtype=float),
                "return_20d_pct": ret_20.to_numpy(dtype=float),
                "risk_adjusted_5d": (ret_5 / vol_5).to_numpy(dtype=float),
                "risk_adjusted_10d": (ret_10 / vol_10).to_numpy(dtype=float),
                "risk_adjusted_20d": (ret_20 / vol_20).to_numpy(dtype=float),
                "volatility_20d_pct": vol_20.to_numpy(dtype=float),
                "up_streak_days": up_streak,
                "down_streak_days": down_streak,
                "confirmation_window_days": CONFIRMATION_WINDOW_DAYS,
                "fin_status": fin_payload.get("fin_status", "insufficient_fundamentals"),
                "fin_report_period": fin_payload.get("fin_report_period", ""),
                "fin_prior_year_period": fin_payload.get("fin_prior_year_period", ""),
                "fin_sample_count": int(fin_payload.get("fin_sample_count") or 0),
                "fin_coverage_ratio": fin_payload.get("fin_coverage_ratio", float("nan")),
                "industry_revenue": fin_payload.get("industry_revenue", float("nan")),
                "industry_revenue_prior_year": fin_payload.get("industry_revenue_prior_year", float("nan")),
                "industry_revenue_yoy_pct": fin_payload.get("industry_revenue_yoy_pct", float("nan")),
                "industry_revenue_yoy_prior_pct": fin_payload.get("industry_revenue_yoy_prior_pct", float("nan")),
                "industry_revenue_accel_pp": fin_payload.get("industry_revenue_accel_pp", float("nan")),
                "revenue_improvers_count": int(fin_payload.get("revenue_improvers_count") or 0),
                "revenue_improvers_pct": fin_payload.get("revenue_improvers_pct", float("nan")),
                "industry_net_profit": fin_payload.get("industry_net_profit", float("nan")),
                "industry_net_profit_yoy_pct": fin_payload.get("industry_net_profit_yoy_pct", float("nan")),
                "profit_improvers_count": int(fin_payload.get("profit_improvers_count") or 0),
                "profit_improvers_pct": fin_payload.get("profit_improvers_pct", float("nan")),
                "industry_net_margin_pct": fin_payload.get("industry_net_margin_pct", float("nan")),
                "industry_net_margin_change_pp": fin_payload.get("industry_net_margin_change_pp", float("nan")),
                "stage_hint": fin_payload.get("stage_hint", ""),
                "stage_hint_rule": fin_payload.get("stage_hint_rule", STAGE_HINT_RULE),
            }
        )

        mret5 = np.full(n, np.nan)
        mret10 = np.full(n, np.nan)
        mret20 = np.full(n, np.nan)
        bench_ids = np.full(n, "market_cap_weighted_universe", dtype=object)
        bench_sources = np.full(n, "market_cap_weighted_universe", dtype=object)
        for i, trade_date in enumerate(dates):
            bench = bench_lookup.get((market_s, str(trade_date)))
            if bench is None:
                continue
            mret5[i] = float(bench.return_5d_pct) if pd.notna(bench.return_5d_pct) else np.nan
            mret10[i] = float(bench.return_10d_pct) if pd.notna(bench.return_10d_pct) else np.nan
            mret20[i] = float(bench.return_20d_pct) if pd.notna(bench.return_20d_pct) else np.nan
            bench_ids[i] = str(bench.benchmark_id)
            bench_sources[i] = str(bench.benchmark_source)
        part["market_return_5d_pct"] = mret5
        part["market_return_10d_pct"] = mret10
        part["market_return_20d_pct"] = mret20
        part["relative_strength_5d"] = part["return_5d_pct"] - part["market_return_5d_pct"]
        part["relative_strength_10d"] = part["return_10d_pct"] - part["market_return_10d_pct"]
        part["relative_strength_20d"] = part["return_20d_pct"] - part["market_return_20d_pct"]
        part["benchmark_id"] = bench_ids
        part["benchmark_source"] = bench_sources
        part["rs_rank_5d"] = 0
        part["rs_rank_universe_size"] = 0
        part["rotation_score"] = np.nan
        part["rotation_rank"] = 0
        part["confirmation_markets_available"] = "[]"
        part["confirmation_markets_up"] = "[]"
        part["confirmation_markets_down"] = "[]"
        part["confirmation_score"] = np.nan

        row_status = np.full(n, "ok", dtype=object)
        if eligible_count < MIN_ELIGIBLE_COUNT:
            row_status[:] = "insufficient_sample"
        else:
            partial_mask = part["volume_expansion_pct"].isna() | part["new_highs_pct"].isna()
            row_status[partial_mask.to_numpy()] = "partial"
        part["row_status"] = row_status
        theme_parts.append(part)

    if not theme_parts:
        raise ValueError("Theme-state output is empty; refusing to publish.")
    theme_df = pd.concat(theme_parts, ignore_index=True)
    theme_df = _apply_rs_ranks(theme_df)
    theme_df = _apply_confirmation(theme_df)
    theme_df = theme_df[THEME_STATE_DAILY_COLUMNS]

    fundamentals_rows: list[dict[str, Any]] = []
    computed_at = datetime.now(timezone.utc).isoformat()
    eligible_by_theme = {
        (str(m), str(l1), str(l2), str(l3)): role_counts(group)[0]
        for (m, l1, l2, l3), group in constituents.groupby(
            ["market", "level1_id", "level2_id", "level3_id"], sort=False
        )
    }
    if fundamentals_by_theme:
        for (market, l1, l2, l3), payloads in fundamentals_by_theme.items():
            period_payloads = payloads if isinstance(payloads, list) else [payloads]
            for payload in period_payloads:
                fundamentals_rows.append(
                    {
                        "market": market,
                        "scope": "L3",
                        "level1_id": l1,
                        "level2_id": l2,
                        "level3_id": l3,
                        "link_key": link_key_by_level3.get(l3, slugify(l3)),
                        "report_period_key": payload.get("report_period_key")
                        or payload.get("fin_report_period")
                        or "",
                        "fin_status": payload.get("fin_status", "insufficient_fundamentals"),
                        "fin_report_period": payload.get("fin_report_period", ""),
                        "fin_prior_year_period": payload.get("fin_prior_year_period", ""),
                        "fin_sample_count": int(payload.get("fin_sample_count") or 0),
                        "fin_coverage_ratio": payload.get("fin_coverage_ratio", float("nan")),
                        "industry_revenue": payload.get("industry_revenue", float("nan")),
                        "industry_revenue_prior_year": payload.get(
                            "industry_revenue_prior_year", float("nan")
                        ),
                        "industry_revenue_yoy_pct": payload.get(
                            "industry_revenue_yoy_pct", float("nan")
                        ),
                        "industry_revenue_yoy_prior_pct": payload.get(
                            "industry_revenue_yoy_prior_pct", float("nan")
                        ),
                        "industry_revenue_accel_pp": payload.get(
                            "industry_revenue_accel_pp", float("nan")
                        ),
                        "revenue_improvers_count": int(payload.get("revenue_improvers_count") or 0),
                        "revenue_improvers_pct": payload.get("revenue_improvers_pct", float("nan")),
                        "industry_net_profit": payload.get("industry_net_profit", float("nan")),
                        "industry_net_profit_yoy_pct": payload.get(
                            "industry_net_profit_yoy_pct", float("nan")
                        ),
                        "profit_improvers_count": int(payload.get("profit_improvers_count") or 0),
                        "profit_improvers_pct": payload.get("profit_improvers_pct", float("nan")),
                        "industry_net_margin_pct": payload.get("industry_net_margin_pct", float("nan")),
                        "industry_net_margin_change_pp": payload.get(
                            "industry_net_margin_change_pp", float("nan")
                        ),
                        "stage_hint": payload.get("stage_hint", ""),
                        "stage_hint_rule": payload.get("stage_hint_rule", STAGE_HINT_RULE),
                        "eligible_count": int(eligible_by_theme.get((market, l1, l2, l3), 0)),
                        "computed_at": computed_at,
                    }
                )
    fundamentals_df = (
        pd.DataFrame(fundamentals_rows)[FUNDAMENTALS_PERIOD_COLUMNS]
        if fundamentals_rows
        else pd.DataFrame(columns=FUNDAMENTALS_PERIOD_COLUMNS)
    )
    benchmark_out = benchmark_daily[MARKET_BENCHMARK_DAILY_COLUMNS].copy()
    return theme_df, benchmark_out, fundamentals_df


async def _enrich_ticker_volumes_from_kline(
    ticker_daily: pd.DataFrame,
    kline_store: Any,
    *,
    on_progress: ProgressCallback | None = None,
) -> pd.DataFrame:
    if kline_store is None or ticker_daily.empty:
        return _ensure_volume_column(ticker_daily)
    if "volume" in ticker_daily.columns and ticker_daily["volume"].notna().any():
        return ticker_daily

    pairs = ticker_daily[["market", "ticker"]].drop_duplicates().values.tolist()
    volume_map: dict[tuple[str, str, str], float] = {}
    total = len(pairs)
    for idx, (market, ticker) in enumerate(pairs, start=1):
        try:
            response = await kline_store.get_or_fetch_kline(
                str(ticker),
                market=str(market),
                kline_t="1D",
                limit=0,
            )
        except Exception as exc:  # noqa: BLE001 — boundary: skip ticker
            LOGGER.warning("theme-state volume enrich failed for %s:%s: %s", market, ticker, exc)
            response = None
        if response is not None and response.bars:
            for bar in response.bars:
                volume_map[(str(market), str(ticker), str(bar.bar_time)[:10])] = float(bar.vol or 0.0)
        if on_progress is not None:
            on_progress("volume", idx, total)

    if not volume_map:
        return _ensure_volume_column(ticker_daily)

    frame = ticker_daily.copy()
    frame["volume"] = [
        volume_map.get((str(m), str(t), str(d)), float("nan"))
        for m, t, d in zip(frame["market"], frame["ticker"], frame["trade_date"])
    ]
    return frame


async def _load_benchmark_closes(
    benchmark_store: Any,
    markets: list[str],
) -> dict[str, pd.DataFrame]:
    if benchmark_store is None:
        return {}
    out: dict[str, pd.DataFrame] = {}
    for market in markets:
        symbol = DEFAULT_BENCHMARKS.get(market)
        if not symbol:
            continue
        try:
            response = await benchmark_store.get_kline(symbol, limit=500)
        except Exception as exc:  # noqa: BLE001
            LOGGER.warning("benchmark kline failed for %s (%s): %s", market, symbol, exc)
            continue
        bars = list(getattr(response, "bars", None) or [])
        if not bars:
            continue
        out[market] = pd.DataFrame(
            {
                "trade_date": [str(bar.bar_time)[:10] for bar in bars],
                "close": [float(bar.close) for bar in bars],
                "benchmark_id": symbol,
            }
        )
    return out


async def _build_fundamentals_by_theme(
    *,
    constituents: pd.DataFrame,
    fin_store: Any,
    on_progress: ProgressCallback | None = None,
    concurrency: int = 8,
) -> dict[tuple[str, str, str, str], list[dict[str, Any]]]:
    if fin_store is None or constituents.empty:
        return {}

    universe = (
        constituents.sort_values(["market", "ticker", "role"])
        .drop_duplicates(subset=["market", "ticker"], keep="first")
    )
    pairs = [(str(r.market), str(r.ticker)) for r in universe.itertuples(index=False)]
    sem = asyncio.Semaphore(concurrency)
    ticker_quarters: dict[tuple[str, str], dict[str, dict[str, float]]] = {}

    async def _one(market: str, ticker: str) -> None:
        async with sem:
            try:
                response = await fin_store.get_for_ticker(ticker, market=market, limit=24)
            except Exception as exc:  # noqa: BLE001
                LOGGER.warning("fin indicators failed for %s:%s: %s", market, ticker, exc)
                return
            items = list(response.items or [])
            if not items:
                return
            ticker_quarters[(market, ticker)] = extract_quarter_metrics(items, market)

    total = len(pairs)
    for idx in range(0, total, concurrency):
        chunk = pairs[idx : idx + concurrency]
        await asyncio.gather(*[_one(m, t) for m, t in chunk])
        if on_progress is not None:
            on_progress("fundamentals", min(idx + len(chunk), total), total)

    out: dict[tuple[str, str, str, str], list[dict[str, Any]]] = {}
    for (market, l1, l2, l3), members in constituents.groupby(
        ["market", "level1_id", "level2_id", "level3_id"], sort=True
    ):
        deduped = dedupe_universe_members(members)
        per_ticker = {
            str(ticker): ticker_quarters[(str(market), str(ticker))]
            for ticker in deduped["ticker"].tolist()
            if (str(market), str(ticker)) in ticker_quarters
        }
        period_keys = list_report_period_keys(per_ticker, max_periods=MAX_FUNDAMENTAL_PERIODS)
        payloads: list[dict[str, Any]] = []
        if not period_keys:
            payloads.append(aggregate_fundamentals_lite(per_ticker))
        else:
            for period_key in period_keys:
                payload = aggregate_fundamentals_lite(per_ticker, report_period_key=period_key)
                if payload.get("fin_status") == "ok" and len(deduped):
                    payload["fin_coverage_ratio"] = nan_or(
                        float(payload.get("fin_sample_count") or 0) / float(len(deduped))
                    )
                payloads.append(payload)
        out[(str(market), str(l1), str(l2), str(l3))] = payloads
    return out


def _latest_fundamentals_payload(
    payloads: list[dict[str, Any]] | dict[str, Any] | None,
) -> dict[str, Any]:
    """Theme-state daily rows attach the newest coverage-qualified period."""
    if payloads is None:
        return {}
    if isinstance(payloads, dict):
        return payloads
    if not payloads:
        return {}
    ok = [row for row in payloads if str(row.get("fin_status") or "") == "ok"]
    return (ok or payloads)[0]


def validate_theme_state_frames(
    theme_df: pd.DataFrame,
    benchmark_df: pd.DataFrame,
    fundamentals_df: pd.DataFrame,
    horizon_df: pd.DataFrame | None = None,
    radar_df: pd.DataFrame | None = None,
    advice_df: pd.DataFrame | None = None,
) -> None:
    if list(theme_df.columns) != THEME_STATE_DAILY_COLUMNS:
        raise ValueError("theme_state_daily schema mismatch.")
    if list(benchmark_df.columns) != MARKET_BENCHMARK_DAILY_COLUMNS:
        raise ValueError("market_benchmark_daily schema mismatch.")
    if list(fundamentals_df.columns) != FUNDAMENTALS_PERIOD_COLUMNS:
        raise ValueError("fundamentals_period schema mismatch.")
    if theme_df.duplicated(subset=["trade_date", "market", "scope", "level1_id", "level2_id", "level3_id"]).any():
        raise ValueError("theme_state_daily contains duplicate keys.")
    if fundamentals_df.duplicated(
        subset=["market", "scope", "level1_id", "level2_id", "level3_id", "report_period_key"]
    ).any():
        raise ValueError("fundamentals_period contains duplicate theme/period keys.")
    if horizon_df is not None:
        if list(horizon_df.columns) != SECTOR_HORIZON_METRICS_COLUMNS:
            raise ValueError("sector_horizon_metrics schema mismatch.")
        if horizon_df.duplicated(
            subset=["trade_date", "market", "scope", "level1_id", "level2_id", "level3_id"]
        ).any():
            raise ValueError("sector_horizon_metrics contains duplicate keys.")
    if radar_df is not None:
        if list(radar_df.columns) != SECTOR_HEALTH_RADAR_COLUMNS:
            raise ValueError("sector_health_radar schema mismatch.")
        if radar_df.duplicated(
            subset=["trade_date", "market", "scope", "level1_id", "level2_id", "level3_id"]
        ).any():
            raise ValueError("sector_health_radar contains duplicate keys.")
    if advice_df is not None:
        if list(advice_df.columns) != SECTOR_ADVICE_DAILY_COLUMNS:
            raise ValueError("sector_advice_daily schema mismatch.")
        if advice_df.duplicated(
            subset=["trade_date", "market", "scope", "level1_id", "level2_id", "level3_id"]
        ).any():
            raise ValueError("sector_advice_daily contains duplicate keys.")


def compute_and_stage_theme_state(
    *,
    theme_df: pd.DataFrame,
    benchmark_df: pd.DataFrame,
    fundamentals_df: pd.DataFrame,
    horizon_df: pd.DataFrame,
    radar_df: pd.DataFrame,
    advice_df: pd.DataFrame,
    out_dir: Path,
    phase_a_dir: Path,
    phase_a_manifest: dict[str, Any],
    start_date: str | None,
    end_date: str | None,
) -> tuple[dict[str, Any], Path]:
    """Stage a unified bundle: Phase A base files + theme/horizon/radar/advice into ``out_dir``."""
    validate_theme_state_frames(
        theme_df, benchmark_df, fundamentals_df, horizon_df, radar_df, advice_df
    )
    for name in PHASE_A_BASE_FILES:
        if not (phase_a_dir / name).exists():
            raise FileNotFoundError(f"Phase A file missing for unified publish: {phase_a_dir / name}")

    staging_dir = out_dir.with_name(f"{out_dir.name}.staging")
    if staging_dir.exists():
        shutil.rmtree(staging_dir)
    staging_dir.mkdir(parents=True, exist_ok=True)

    # Preserve Phase A artifacts in the same published dataset.
    for name in PHASE_A_BASE_FILES:
        shutil.copy2(phase_a_dir / name, staging_dir / name)

    theme_path = staging_dir / THEME_STATE_DAILY_FILE
    bench_path = staging_dir / MARKET_BENCHMARK_DAILY_FILE
    fin_path = staging_dir / FUNDAMENTALS_PERIOD_FILE
    horizon_path = staging_dir / SECTOR_HORIZON_METRICS_FILE
    radar_path = staging_dir / SECTOR_HEALTH_RADAR_FILE
    advice_path = staging_dir / SECTOR_ADVICE_DAILY_FILE
    theme_df.to_parquet(theme_path, index=False)
    benchmark_df.to_parquet(bench_path, index=False)
    fundamentals_df.to_parquet(fin_path, index=False)
    horizon_df.to_parquet(horizon_path, index=False)
    radar_df.to_parquet(radar_path, index=False)
    advice_df.to_parquet(advice_path, index=False)

    generated_at = datetime.now(timezone.utc).isoformat()
    latest = {
        str(market): str(group["trade_date"].max())
        for market, group in theme_df.groupby("market")
    }
    phase_a_files = {
        name: {
            "rows": int((phase_a_manifest.get("files") or {}).get(name, {}).get("rows") or 0),
            "sha256": _file_sha256(staging_dir / name),
        }
        for name in PHASE_A_BASE_FILES
    }
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "phase": "sector_unified",
        "build_id": generated_at.replace(":", "").replace("-", ""),
        "generated_at": generated_at,
        "phase_a": {
            "schema_version": str(phase_a_manifest.get("schema_version") or ""),
            "build_id": str(phase_a_manifest.get("build_id") or ""),
            "weighting_method": phase_a_manifest.get("weighting_method"),
            "constituent_count": phase_a_manifest.get("constituent_count"),
            "ticker_daily_rows": phase_a_manifest.get("ticker_daily_rows"),
            "sector_daily_rows": phase_a_manifest.get("sector_daily_rows"),
            "stats": phase_a_manifest.get("stats") or {},
        },
        "theme_state_rules_version": THEME_STATE_RULES_VERSION,
        "window_start": start_date
        or str(phase_a_manifest.get("window_start") or theme_df["trade_date"].min()),
        "window_end": end_date or str(theme_df["trade_date"].max()),
        "latest_trade_date_by_market": latest,
        "theme_state_daily_rows": int(len(theme_df)),
        "fundamentals_period_rows": int(len(fundamentals_df)),
        "sector_horizon_metrics_rows": int(len(horizon_df)),
        "sector_health_radar_rows": int(len(radar_df)),
        "sector_advice_daily_rows": int(len(advice_df)),
        "scoring": {
            "radar_rule": RADAR_RULE,
            "short_advice_rule": SHORT_ADVICE_RULE,
            "mid_advice_rule": MID_ADVICE_RULE,
            "radar_weights": dict(RADAR_AXIS_WEIGHTS),
            "short_score_weights": dict(SHORT_SCORE_WEIGHTS),
            "mid_score_weights": dict(MID_SCORE_WEIGHTS),
        },
        "rules": {
            "role_filter": ROLE_FILTER,
            "min_eligible_count": MIN_ELIGIBLE_COUNT,
            "volume_lookback_days": VOLUME_LOOKBACK_DAYS,
            "volume_multiplier": VOLUME_MULTIPLIER,
            "high_lookback_days": HIGH_LOOKBACK_DAYS,
            "confirmation_window_days": CONFIRMATION_WINDOW_DAYS,
            "momentum_windows": list(MOMENTUM_WINDOWS),
            "horizon_windows": [60, 120, 252],
            "max_fundamental_periods": MAX_FUNDAMENTAL_PERIODS,
            "stage_hint_rule": STAGE_HINT_RULE,
            "rotation_rank_rule": ROTATION_RANK_RULE,
            "rotation_rs_weights": {
                "5d": ROTATION_RS_WEIGHTS[0],
                "10d": ROTATION_RS_WEIGHTS[1],
                "20d": ROTATION_RS_WEIGHTS[2],
            },
            "rotation_breadth_center": ROTATION_BREADTH_CENTER,
            "rotation_breadth_mult_min": ROTATION_BREADTH_MULT_MIN,
            "rotation_breadth_mult_max": ROTATION_BREADTH_MULT_MAX,
        },
        "files": {
            **phase_a_files,
            THEME_STATE_DAILY_FILE: {"rows": len(theme_df), "sha256": _file_sha256(theme_path)},
            MARKET_BENCHMARK_DAILY_FILE: {
                "rows": len(benchmark_df),
                "sha256": _file_sha256(bench_path),
            },
            FUNDAMENTALS_PERIOD_FILE: {
                "rows": len(fundamentals_df),
                "sha256": _file_sha256(fin_path),
            },
            SECTOR_HORIZON_METRICS_FILE: {
                "rows": len(horizon_df),
                "sha256": _file_sha256(horizon_path),
            },
            SECTOR_HEALTH_RADAR_FILE: {
                "rows": len(radar_df),
                "sha256": _file_sha256(radar_path),
            },
            SECTOR_ADVICE_DAILY_FILE: {
                "rows": len(advice_df),
                "sha256": _file_sha256(advice_path),
            },
        },
    }
    (staging_dir / MANIFEST_FILE).write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return manifest, staging_dir


def publish_staged_theme_state(staging_dir: Path, out_dir: Path) -> Path:
    backup_dir = out_dir.with_name(f"{out_dir.name}.bak")
    if backup_dir.exists():
        shutil.rmtree(backup_dir)
    if out_dir.exists():
        out_dir.replace(backup_dir)
    staging_dir.replace(out_dir)
    if backup_dir.exists():
        shutil.rmtree(backup_dir)
    return out_dir


async def build_theme_state_precomputed(
    data_root: Path,
    *,
    sector_store: Any | None = None,
    kline_store: Any | None = None,
    benchmark_store: Any | None = None,
    fin_store: Any | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    out_dir: Path | None = None,
    upload_client: Any | None = None,
    upload_dataset_name: str = PHASE_A_DIR,
    skip_fundamentals: bool = False,
    skip_volume_enrich: bool = False,
    on_progress: ProgressCallback | None = None,
) -> dict[str, Any]:
    """Enrich ``dojo_sector_precomputed`` with theme-state, horizon, radar, and advice."""
    data_root = data_root.expanduser().resolve()
    out_dir = (out_dir or (data_root / PHASE_A_DIR)).resolve()
    phase_a_source_dir = data_root / PHASE_A_DIR

    if on_progress is not None:
        on_progress("load_phase_a", 0, 1)
    constituents, ticker_daily, sector_daily, phase_a_manifest = load_phase_a_snapshot(data_root)
    if on_progress is not None:
        on_progress("load_phase_a", 1, 1)

    if not skip_volume_enrich:
        ticker_daily = await _enrich_ticker_volumes_from_kline(
            ticker_daily, kline_store, on_progress=on_progress
        )
    else:
        ticker_daily = _ensure_volume_column(ticker_daily)

    link_key_by_level3 = build_link_key_map(sector_store, constituents)

    markets = sorted(constituents["market"].astype(str).unique().tolist())
    closes = await _load_benchmark_closes(benchmark_store, markets)
    if closes:
        benchmark_daily = _benchmark_daily_from_closes(closes)
    else:
        benchmark_daily = None

    fundamentals_by_theme: dict[tuple[str, str, str, str], list[dict[str, Any]]] = {}
    if not skip_fundamentals:
        fundamentals_by_theme = await _build_fundamentals_by_theme(
            constituents=constituents,
            fin_store=fin_store,
            on_progress=on_progress,
        )

    if on_progress is not None:
        on_progress("compute", 0, 3)
    theme_df, benchmark_df, fundamentals_df = await asyncio.to_thread(
        compute_theme_state_frames,
        constituents=constituents,
        ticker_daily=ticker_daily,
        sector_daily=sector_daily,
        link_key_by_level3=link_key_by_level3,
        benchmark_daily=benchmark_daily,
        fundamentals_by_theme=fundamentals_by_theme,
        start_date=start_date,
        end_date=end_date,
    )
    if on_progress is not None:
        on_progress("compute", 1, 3)

    horizon_source = sector_daily
    if start_date:
        horizon_source = horizon_source[horizon_source["trade_date"].astype(str) >= start_date]
    if end_date:
        horizon_source = horizon_source[horizon_source["trade_date"].astype(str) <= end_date]
    horizon_df = await asyncio.to_thread(
        compute_sector_horizon_metrics_frame,
        sector_daily=horizon_source,
        benchmark_daily=benchmark_df,
        fundamentals_period=fundamentals_df,
        link_key_by_level3=link_key_by_level3,
    )
    if on_progress is not None:
        on_progress("compute", 2, 3)

    radar_df, advice_df = await asyncio.to_thread(
        compute_sector_radar_advice_frames,
        theme_state_daily=theme_df,
        sector_horizon_metrics=horizon_df,
    )
    if on_progress is not None:
        on_progress("compute", 3, 3)
        on_progress("publish", 0, 1)

    manifest, staging_dir = await asyncio.to_thread(
        compute_and_stage_theme_state,
        theme_df=theme_df,
        benchmark_df=benchmark_df,
        fundamentals_df=fundamentals_df,
        horizon_df=horizon_df,
        radar_df=radar_df,
        advice_df=advice_df,
        out_dir=out_dir,
        phase_a_dir=phase_a_source_dir,
        phase_a_manifest=phase_a_manifest,
        start_date=start_date,
        end_date=end_date,
    )
    published_dir = await asyncio.to_thread(publish_staged_theme_state, staging_dir, out_dir)
    if on_progress is not None:
        on_progress("publish", 1, 1)
    manifest["published_dir"] = str(published_dir)

    if upload_client is not None:
        if on_progress is not None:
            on_progress("upload", 0, 1)
        await upload_client.upload_dataset(upload_dataset_name, str(published_dir))
        if on_progress is not None:
            on_progress("upload", 1, 1)
        manifest["uploaded_dataset"] = upload_dataset_name
    return manifest
