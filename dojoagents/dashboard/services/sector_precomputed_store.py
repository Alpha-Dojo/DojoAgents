from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Optional

import pandas as pd

from dojoagents.config.loader import FinancialDashboardConfig
from dojoagents.dashboard.services.domain_utils import normalize_market_code, sanitize_mapping, sanitize_records
from dojoagents.dashboard.services.precompute_sector_daily import (
    CONSTITUENTS_FILE,
    MANIFEST_FILE,
    PRECOMPUTE_DIR,
    SECTOR_DAILY_FILE,
    TICKER_DAILY_FILE,
)

logger = logging.getLogger(__name__)


class SectorPrecomputedStore:
    def __init__(self, data_root: Path | None = None) -> None:
        self.data_root = Path(data_root or FinancialDashboardConfig.dashboard_data_root).expanduser().resolve()
        self.dataset_dir = self.data_root / PRECOMPUTE_DIR
        self._constituents_df: Optional[pd.DataFrame] = None
        self._sector_daily_df: Optional[pd.DataFrame] = None
        self._ticker_daily_df: Optional[pd.DataFrame] = None
        self._manifest: dict[str, Any] | None = None
        self._last_error: str | None = None
        self._load_generation = 0
        self._constituents_exact_index: dict[tuple[str, str, str, str], list[dict[str, Any]]] = {}
        self._sector_window_cache: dict[int, pd.DataFrame] = {}
        self._ticker_window_cache: dict[int, pd.DataFrame] = {}

    def available(self) -> bool:
        return self.dataset_dir.exists() and (self.dataset_dir / MANIFEST_FILE).exists()

    async def load(self) -> None:
        await self.reload_async()

    async def reload_async(self, dataset_dir: Path | None = None) -> None:
        self.reload(dataset_dir)

    def reload(self, dataset_dir: Path | None = None) -> None:
        import os
        from dojo.datasource.upload import download_dataset

        target_dir = Path(dataset_dir).expanduser().resolve() if dataset_dir else self.dataset_dir

        offline_only = os.environ.get("DOJO_HF_OFFLINE", "false").lower() in ("1", "true", "yes")
        if not offline_only:
            try:
                logger.info("Syncing dojo_sector_precomputed dataset from HuggingFace to %s...", target_dir)
                download_dataset("dojo_sector_precomputed", target_dir)
            except Exception as exc:
                logger.warning("Failed to sync dojo_sector_precomputed dataset, will try to use existing local files: %s", exc)

        manifest_path = target_dir / MANIFEST_FILE
        if manifest_path.exists():
            try:
                constituents_df = self._normalize_constituents_frame(pd.read_parquet(target_dir / CONSTITUENTS_FILE))
                sector_daily_df = self._normalize_sector_daily_frame(pd.read_parquet(target_dir / SECTOR_DAILY_FILE))
                ticker_daily_df = self._normalize_ticker_daily_frame(pd.read_parquet(target_dir / TICKER_DAILY_FILE))
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            except Exception as exc:
                self._last_error = f"local_reload_failed: {exc}"
                logger.warning("Failed to reload local sector precomputed snapshot: %s", exc)
                self.clear_cache()
            else:
                self.dataset_dir = target_dir
                self._constituents_df = constituents_df
                self._sector_daily_df = sector_daily_df
                self._ticker_daily_df = ticker_daily_df
                self._manifest = manifest
                self._last_error = None
                self._rebuild_indexes_locked()
                return

        self._last_error = "dataset_missing"
        logger.error("Sector precomputed dataset missing and sync failed or offline.")
        self.clear_cache()

    def _load_constituents(self) -> pd.DataFrame:
        return self._constituents_df if self._constituents_df is not None else pd.DataFrame()

    def _load_sector_daily(self) -> pd.DataFrame:
        return self._sector_daily_df if self._sector_daily_df is not None else pd.DataFrame()

    def _load_ticker_daily(self) -> pd.DataFrame:
        return self._ticker_daily_df if self._ticker_daily_df is not None else pd.DataFrame()

    def manifest(self) -> dict[str, Any] | None:
        return self._manifest

    @property
    def load_generation(self) -> int:
        return self._load_generation

    def stats(self) -> dict[str, Any]:
        return {
            "available": self.available(),
            "constituents_rows": len(self._load_constituents()),
            "sector_daily_rows": len(self._load_sector_daily()),
            "ticker_daily_rows": len(self._load_ticker_daily()),
            "last_error": self._last_error,
            "manifest": self._manifest,
        }

    def get_sector_constituents(self, level1_id: str, level2_id: str, level3_id: str, market: Optional[str] = None) -> list[dict]:
        df = self._load_constituents()
        if df.empty:
            return []

        exact = self.get_sector_constituents_exact(level1_id, level2_id, level3_id, market=market)
        if market and level2_id and level3_id and exact:
            return exact

        mask = df["level1_id"] == level1_id
        if level2_id:
            mask &= df["level2_id"] == level2_id
        if level3_id:
            mask &= df["level3_id"] == level3_id
        if market:
            mask &= df["market"] == (normalize_market_code(market) or market)

        return sanitize_records(df[mask])

    def get_sector_constituents_exact(
        self,
        level1_id: str,
        level2_id: str,
        level3_id: str,
        market: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        normalized_market = normalize_market_code(market) or market
        if not normalized_market or not level2_id or not level3_id:
            return []
        key = (normalized_market, str(level1_id), str(level2_id), str(level3_id))
        rows = self._constituents_exact_index.get(key)
        return list(rows) if rows is not None else []

    def get_sector_daily(self, scope: str, level1_id: str, level2_id: str, level3_id: str, market: Optional[str] = None) -> list[dict]:
        df = self._load_sector_daily()
        if df.empty:
            return []

        mask = (df["scope"] == scope) & (df["level1_id"] == level1_id)
        if scope in ("L2", "L3"):
            mask &= df["level2_id"] == level2_id
        if scope == "L3":
            mask &= df["level3_id"] == level3_id
        if market:
            mask &= df["market"] == (normalize_market_code(market) or market)
        return sanitize_records(df[mask])

    def get_sector_movers(self, date: str) -> list[dict]:
        df = self._load_sector_daily()
        if df.empty:
            return []
        target_date = date or str(df["trade_date"].max())
        return sanitize_records(df[df["trade_date"] == target_date])

    def get_sector_movers_window_frame(self, days: int) -> pd.DataFrame:
        df = self._load_sector_daily()
        if df.empty:
            return pd.DataFrame()
        cached = self._sector_window_cache.get(days)
        if cached is not None:
            return cached
        computed = self._compute_window_frame(
            df,
            group_cols=["scope", "level1_id", "level2_id", "level3_id", "market"],
            value_col="index_level",
            days=days,
        )
        existing = self._sector_window_cache.get(days)
        if existing is not None:
            return existing
        self._sector_window_cache[days] = computed
        return computed

    def get_sector_movers_by_window(self, days: int) -> list[dict]:
        return sanitize_records(self.get_sector_movers_window_frame(days))

    def get_ticker_daily(self, date: str, tickers: list[str], market: str | None = None) -> list[dict]:
        df = self._load_ticker_daily()
        if df.empty:
            return []
        mask = (df["trade_date"] == date) & (df["ticker"].isin(tickers))
        if market:
            mask &= df["market"] == (normalize_market_code(market) or market)
        return sanitize_records(df[mask])

    def get_ticker_daily_window_frame(self, days: int) -> pd.DataFrame:
        df = self._load_ticker_daily()
        if df.empty:
            return pd.DataFrame()
        cached = self._ticker_window_cache.get(days)
        if cached is not None:
            return cached
        computed = self._compute_window_frame(
            df,
            group_cols=["market", "ticker"],
            value_col="close",
            days=days,
        )
        existing = self._ticker_window_cache.get(days)
        if existing is not None:
            return existing
        self._ticker_window_cache[days] = computed
        return computed

    def get_ticker_daily_by_window(self, days: int, tickers: list[str], market: str | None = None) -> list[dict]:
        df = self.get_ticker_daily_window_frame(days)
        if df.empty or not tickers:
            return []

        mask = df["ticker"].isin(tickers)
        if market:
            mask &= df["market"] == (normalize_market_code(market) or market)
        return sanitize_records(df[mask])

    def clear_cache(self) -> None:
        self._constituents_df = None
        self._sector_daily_df = None
        self._ticker_daily_df = None
        self._manifest = None
        self._constituents_exact_index = {}
        self._sector_window_cache = {}
        self._ticker_window_cache = {}
        self._load_generation += 1

    def _rebuild_indexes_locked(self) -> None:
        self._constituents_exact_index = {}
        self._sector_window_cache = {}
        self._ticker_window_cache = {}
        self._load_generation += 1
        df = self._constituents_df
        if df is None or df.empty:
            return
        for row in sanitize_records(df):
            key = (
                str(row.get("market") or ""),
                str(row.get("level1_id") or ""),
                str(row.get("level2_id") or ""),
                str(row.get("level3_id") or ""),
            )
            self._constituents_exact_index.setdefault(key, []).append(row)

    @staticmethod
    def _normalize_constituents_frame(df: pd.DataFrame) -> pd.DataFrame:
        if df.empty:
            return df
        normalized = df
        for col in ("market", "ticker", "level1_id", "level2_id", "level3_id"):
            if col in normalized.columns:
                normalized[col] = normalized[col].astype(str)
        return normalized

    @staticmethod
    def _normalize_sector_daily_frame(df: pd.DataFrame) -> pd.DataFrame:
        if df.empty:
            return df
        normalized = df
        for col in ("scope", "market", "level1_id", "level2_id", "level3_id", "trade_date"):
            if col in normalized.columns:
                normalized[col] = normalized[col].astype(str)
        return normalized

    @staticmethod
    def _normalize_ticker_daily_frame(df: pd.DataFrame) -> pd.DataFrame:
        if df.empty:
            return df
        normalized = df
        for col in ("market", "ticker", "trade_date"):
            if col in normalized.columns:
                normalized[col] = normalized[col].astype(str)
        return normalized

    @staticmethod
    def _compute_window_frame(
        df: pd.DataFrame,
        *,
        group_cols: list[str],
        value_col: str,
        days: int,
    ) -> pd.DataFrame:
        if df.empty:
            return pd.DataFrame()

        sort_cols = [*group_cols, "trade_date"]
        df_sorted = df.sort_values(by=sort_cols).reset_index(drop=True)
        if days <= 1:
            return df_sorted.groupby(group_cols, sort=False, as_index=False).tail(1)

        group_sizes = df_sorted.groupby(group_cols, sort=False)["trade_date"].transform("size")
        positions = df_sorted.groupby(group_cols, sort=False).cumcount()
        latest_mask = positions == (group_sizes - 1)
        start_positions = (group_sizes - days).clip(lower=0)
        start_mask = positions == start_positions

        latest_rows = df_sorted[latest_mask]
        start_rows = df_sorted[start_mask][group_cols + [value_col]].rename(columns={value_col: "_window_start_value"})
        merged = latest_rows.merge(start_rows, on=group_cols, how="left")

        latest_values = pd.to_numeric(merged[value_col], errors="coerce")
        start_values = pd.to_numeric(merged["_window_start_value"], errors="coerce")
        merged["daily_return_pct"] = ((latest_values / start_values) - 1.0) * 100.0
        invalid = start_values.isna() | latest_values.isna() | (start_values <= 0)
        merged.loc[invalid, "daily_return_pct"] = 0.0
        merged["daily_return_pct"] = merged["daily_return_pct"].fillna(0.0)
        if "change_percent" in merged.columns:
            merged = merged.drop(columns=["change_percent"])
        return merged.drop(columns=["_window_start_value"], errors="ignore")
