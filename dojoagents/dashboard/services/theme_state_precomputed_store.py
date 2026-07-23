"""Load and query theme-state / horizon / alpha-factor tables from unified sector precompute."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

import pandas as pd

from dojoagents.config.loader import FinancialDashboardConfig
from dojoagents.dashboard.jobs.precompute.sector_alpha_factors import SECTOR_ALPHA_FACTORS_FILE
from dojoagents.dashboard.jobs.precompute.sector_daily import PRECOMPUTE_DIR
from dojoagents.dashboard.jobs.precompute.sector_horizon import SECTOR_HORIZON_METRICS_FILE
from dojoagents.dashboard.jobs.precompute.sector_radar_advice import (
    SECTOR_ADVICE_DAILY_FILE,
    SECTOR_HEALTH_RADAR_FILE,
)
from dojoagents.dashboard.jobs.precompute.theme_state_daily import (
    FUNDAMENTALS_PERIOD_FILE,
    MANIFEST_FILE,
    MARKET_BENCHMARK_DAILY_FILE,
    THEME_STATE_DAILY_FILE,
    THEME_STATE_DIR,
)
from dojoagents.dashboard.jobs.precompute.ticker_alpha_factors import TICKER_ALPHA_FACTORS_FILE
from dojoagents.logging import LOGGER


class ThemeStatePrecomputedStore:
    def __init__(self, data_root: Path | None = None) -> None:
        self.data_root = Path(data_root or FinancialDashboardConfig.dashboard_data_root).expanduser().resolve()
        # Prefer unified dojo_sector_precomputed; fall back to legacy standalone dir.
        self.dataset_dir = self._resolve_dataset_dir()
        self._theme_df: Optional[pd.DataFrame] = None
        self._benchmark_df: Optional[pd.DataFrame] = None
        self._fundamentals_df: Optional[pd.DataFrame] = None
        self._horizon_df: Optional[pd.DataFrame] = None
        self._radar_df: Optional[pd.DataFrame] = None
        self._advice_df: Optional[pd.DataFrame] = None
        self._alpha_df: Optional[pd.DataFrame] = None
        self._ticker_alpha_df: Optional[pd.DataFrame] = None
        self._manifest: dict[str, Any] | None = None
        self._last_error: str | None = None

    def _resolve_dataset_dir(self) -> Path:
        unified = self.data_root / PRECOMPUTE_DIR
        legacy = self.data_root / THEME_STATE_DIR
        if (unified / THEME_STATE_DAILY_FILE).exists() and (unified / MANIFEST_FILE).exists():
            return unified
        if (legacy / THEME_STATE_DAILY_FILE).exists() and (legacy / MANIFEST_FILE).exists():
            return legacy
        return unified

    def available(self) -> bool:
        return self.dataset_dir.exists() and (self.dataset_dir / THEME_STATE_DAILY_FILE).exists()

    def clear_cache(self) -> None:
        self._theme_df = None
        self._benchmark_df = None
        self._fundamentals_df = None
        self._horizon_df = None
        self._radar_df = None
        self._advice_df = None
        self._alpha_df = None
        self._ticker_alpha_df = None
        self._manifest = None

    async def load(self) -> None:
        self.reload()

    def reload(self, dataset_dir: Path | None = None) -> None:
        if dataset_dir is None:
            self.dataset_dir = self._resolve_dataset_dir()
            target_dir = self.dataset_dir
        else:
            target_dir = Path(dataset_dir).expanduser().resolve()
        manifest_path = target_dir / MANIFEST_FILE
        theme_path = target_dir / THEME_STATE_DAILY_FILE
        if not theme_path.exists():
            self._last_error = "dataset_missing"
            LOGGER.error("Theme-state precomputed dataset missing at %s", target_dir)
            self.clear_cache()
            return
        try:
            theme_df = pd.read_parquet(theme_path)
            benchmark_path = target_dir / MARKET_BENCHMARK_DAILY_FILE
            fundamentals_path = target_dir / FUNDAMENTALS_PERIOD_FILE
            horizon_path = target_dir / SECTOR_HORIZON_METRICS_FILE
            radar_path = target_dir / SECTOR_HEALTH_RADAR_FILE
            advice_path = target_dir / SECTOR_ADVICE_DAILY_FILE
            alpha_path = target_dir / SECTOR_ALPHA_FACTORS_FILE
            ticker_alpha_path = target_dir / TICKER_ALPHA_FACTORS_FILE
            benchmark_df = pd.read_parquet(benchmark_path) if benchmark_path.exists() else pd.DataFrame()
            fundamentals_df = pd.read_parquet(fundamentals_path) if fundamentals_path.exists() else pd.DataFrame()
            horizon_df = pd.read_parquet(horizon_path) if horizon_path.exists() else pd.DataFrame()
            radar_df = pd.read_parquet(radar_path) if radar_path.exists() else pd.DataFrame()
            advice_df = pd.read_parquet(advice_path) if advice_path.exists() else pd.DataFrame()
            alpha_df = pd.read_parquet(alpha_path) if alpha_path.exists() else pd.DataFrame()
            ticker_alpha_df = pd.read_parquet(ticker_alpha_path) if ticker_alpha_path.exists() else pd.DataFrame()
            manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
        except Exception as exc:
            self._last_error = f"local_reload_failed: {exc}"
            LOGGER.warning("Failed to reload theme-state precomputed snapshot: %s", exc)
            self.clear_cache()
            return

        for frame in (
            theme_df,
            benchmark_df,
            fundamentals_df,
            horizon_df,
            radar_df,
            advice_df,
            alpha_df,
            ticker_alpha_df,
        ):
            for col in ("market", "trade_date", "ticker", "level1_id", "level2_id", "level3_id", "link_key", "scope"):
                if col in frame.columns:
                    frame[col] = frame[col].astype(str)

        self.dataset_dir = target_dir
        self._theme_df = theme_df
        self._benchmark_df = benchmark_df
        self._fundamentals_df = fundamentals_df
        self._horizon_df = horizon_df
        self._radar_df = radar_df
        self._advice_df = advice_df
        self._alpha_df = alpha_df
        self._ticker_alpha_df = ticker_alpha_df
        self._manifest = manifest
        self._last_error = None

    @property
    def manifest(self) -> dict[str, Any] | None:
        return self._manifest

    def _latest_keyed_row(
        self,
        frame: pd.DataFrame | None,
        *,
        level1_id: str,
        level2_id: str,
        level3_id: str,
        market: str,
        as_of: str | None = None,
    ) -> dict[str, Any] | None:
        if frame is None or frame.empty:
            return None
        mask = (frame["level1_id"] == str(level1_id)) & (frame["level2_id"] == str(level2_id)) & (frame["level3_id"] == str(level3_id)) & (frame["market"] == str(market))
        subset = frame.loc[mask]
        if subset.empty:
            return None
        if as_of:
            subset = subset[subset["trade_date"] <= as_of]
            if subset.empty:
                return None
        row = subset.sort_values("trade_date").iloc[-1]
        return {str(k): (None if pd.isna(v) else v) for k, v in row.to_dict().items()}

    def get_theme_state(
        self,
        *,
        level1_id: str,
        level2_id: str,
        level3_id: str,
        market: str,
        as_of: str | None = None,
    ) -> dict[str, Any] | None:
        return self._latest_keyed_row(
            self._theme_df,
            level1_id=level1_id,
            level2_id=level2_id,
            level3_id=level3_id,
            market=market,
            as_of=as_of,
        )

    def get_horizon_metrics(
        self,
        *,
        level1_id: str,
        level2_id: str,
        level3_id: str,
        market: str,
        as_of: str | None = None,
    ) -> dict[str, Any] | None:
        return self._latest_keyed_row(
            self._horizon_df,
            level1_id=level1_id,
            level2_id=level2_id,
            level3_id=level3_id,
            market=market,
            as_of=as_of,
        )

    def get_alpha_factors(
        self,
        *,
        level1_id: str,
        level2_id: str,
        level3_id: str,
        market: str,
        as_of: str | None = None,
    ) -> dict[str, Any] | None:
        return self._latest_keyed_row(
            self._alpha_df,
            level1_id=level1_id,
            level2_id=level2_id,
            level3_id=level3_id,
            market=market,
            as_of=as_of,
        )

    def get_ticker_alpha_factors(
        self,
        *,
        ticker: str,
        market: str,
        as_of: str | None = None,
    ) -> dict[str, Any] | None:
        frame = self._ticker_alpha_df
        if frame is None or frame.empty:
            return None
        mask = (frame["ticker"] == str(ticker)) & (frame["market"] == str(market))
        subset = frame.loc[mask]
        if subset.empty:
            return None
        if as_of:
            subset = subset[subset["trade_date"] <= as_of]
            if subset.empty:
                return None
        row = subset.sort_values("trade_date").iloc[-1]
        return {str(k): (None if pd.isna(v) else v) for k, v in row.to_dict().items()}

    def list_ticker_alpha_board(
        self,
        *,
        market: str,
        factor: str = "s_rs_20d",
        as_of: str | None = None,
        limit: int = 50,
        ascending: bool = False,
        level3_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Rank tickers by a single alpha factor on ``as_of`` (default latest)."""
        if self._ticker_alpha_df is None or self._ticker_alpha_df.empty:
            return []
        if factor not in self._ticker_alpha_df.columns:
            return []
        frame = self._ticker_alpha_df[self._ticker_alpha_df["market"] == str(market)]
        if level3_id:
            frame = frame[frame["level3_id"] == str(level3_id)]
        if frame.empty:
            return []
        trade_date = as_of or str(frame["trade_date"].max())
        day = frame[frame["trade_date"] == trade_date].copy()
        day = day[pd.to_numeric(day[factor], errors="coerce").notna()]
        day = day.sort_values([factor, "ticker"], ascending=[ascending, True])
        if limit > 0:
            day = day.head(limit)
        return [{str(k): (None if pd.isna(v) else v) for k, v in row.items()} for row in day.to_dict(orient="records")]

    def list_fundamentals_periods(
        self,
        *,
        level1_id: str,
        level2_id: str,
        level3_id: str,
        market: str,
    ) -> list[dict[str, Any]]:
        if self._fundamentals_df is None or self._fundamentals_df.empty:
            return []
        frame = self._fundamentals_df
        mask = (frame["level1_id"] == str(level1_id)) & (frame["level2_id"] == str(level2_id)) & (frame["level3_id"] == str(level3_id)) & (frame["market"] == str(market))
        subset = frame.loc[mask].copy()
        if subset.empty:
            return []
        if "report_period_key" in subset.columns:
            subset = subset.sort_values("report_period_key", ascending=False)
        return [{str(k): (None if pd.isna(v) else v) for k, v in row.items()} for row in subset.to_dict(orient="records")]

    def list_rotation(
        self,
        *,
        market: str,
        as_of: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        if self._theme_df is None or self._theme_df.empty:
            return []
        frame = self._theme_df[self._theme_df["market"] == str(market)]
        if frame.empty:
            return []
        trade_date = as_of or str(frame["trade_date"].max())
        day = frame[frame["trade_date"] == trade_date]
        day = day[day["row_status"].isin(["ok", "partial"])]
        if "rotation_rank" in day.columns and int((day["rotation_rank"] > 0).sum()) > 0:
            scored = day[day["rotation_rank"] > 0].sort_values(["rotation_rank", "level3_id"], ascending=[True, True])
            unscored = day[day["rotation_rank"] <= 0]
            if not unscored.empty and "rs_rank_5d" in unscored.columns:
                unscored = unscored.sort_values(["rs_rank_5d", "level3_id"], ascending=[True, True])
            day = pd.concat([scored, unscored], ignore_index=True)
        elif "rs_rank_5d" in day.columns:
            day = day.sort_values(["rs_rank_5d", "level3_id"], ascending=[True, True])
        else:
            day = day.sort_values(["level3_id"], ascending=[True])
        if limit > 0:
            day = day.head(limit)
        return [{str(k): (None if pd.isna(v) else v) for k, v in row.items()} for row in day.to_dict(orient="records")]

    def get_health_radar(
        self,
        *,
        level1_id: str,
        level2_id: str,
        level3_id: str,
        market: str,
        as_of: str | None = None,
    ) -> dict[str, Any] | None:
        return self._latest_keyed_row(
            self._radar_df,
            level1_id=level1_id,
            level2_id=level2_id,
            level3_id=level3_id,
            market=market,
            as_of=as_of,
        )

    def get_advice(
        self,
        *,
        level1_id: str,
        level2_id: str,
        level3_id: str,
        market: str,
        as_of: str | None = None,
    ) -> dict[str, Any] | None:
        return self._latest_keyed_row(
            self._advice_df,
            level1_id=level1_id,
            level2_id=level2_id,
            level3_id=level3_id,
            market=market,
            as_of=as_of,
        )

    def list_advice_board(
        self,
        *,
        market: str,
        horizon: str = "short",
        as_of: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        if self._advice_df is None or self._advice_df.empty:
            return []
        normalized_horizon = str(horizon).strip().lower()
        if normalized_horizon not in {"short", "mid"}:
            raise ValueError("horizon must be 'short' or 'mid'")
        frame = self._advice_df[self._advice_df["market"] == str(market)]
        if frame.empty:
            return []
        trade_date = as_of or str(frame["trade_date"].max())
        day = frame[frame["trade_date"] == trade_date].copy()
        rank_column = f"{normalized_horizon}_rank"
        if rank_column in day.columns:
            day = day.sort_values([rank_column, "level3_id"], ascending=[True, True])
        else:
            day = day.sort_values(["level3_id"], ascending=[True])
        if limit > 0:
            day = day.head(limit)
        return [{str(k): (None if pd.isna(v) else v) for k, v in row.items()} for row in day.to_dict(orient="records")]

    def list_alpha_board(
        self,
        *,
        market: str,
        factor: str = "s_rs_rotation",
        as_of: str | None = None,
        limit: int = 50,
        ascending: bool = False,
    ) -> list[dict[str, Any]]:
        """Rank L3 themes by a single alpha factor on ``as_of`` (default latest)."""
        if self._alpha_df is None or self._alpha_df.empty:
            return []
        if factor not in self._alpha_df.columns:
            return []
        frame = self._alpha_df[self._alpha_df["market"] == str(market)]
        if frame.empty:
            return []
        trade_date = as_of or str(frame["trade_date"].max())
        day = frame[frame["trade_date"] == trade_date].copy()
        day = day[pd.to_numeric(day[factor], errors="coerce").notna()]
        day = day.sort_values([factor, "level3_id"], ascending=[ascending, True])
        if limit > 0:
            day = day.head(limit)
        return [{str(k): (None if pd.isna(v) else v) for k, v in row.items()} for row in day.to_dict(orient="records")]
