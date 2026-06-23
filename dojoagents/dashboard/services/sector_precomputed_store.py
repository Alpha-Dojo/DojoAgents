from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Optional

import pandas as pd
from dojo import Dojo

from dojoagents.config.loader import FinancialDashboardConfig
from dojoagents.dashboard.services.domain_utils import normalize_market_code
from dojoagents.dashboard.services.precompute_sector_daily import (
    CONSTITUENTS_FILE,
    MANIFEST_FILE,
    PRECOMPUTE_DIR,
    SECTOR_DAILY_FILE,
    TICKER_DAILY_FILE,
)

logger = logging.getLogger(__name__)


class SectorPrecomputedStore:
    def __init__(self, data_root: Path | None = None, client: Dojo | None = None) -> None:
        self.data_root = Path(data_root or FinancialDashboardConfig.dashboard_data_root).expanduser().resolve()
        self.dataset_dir = self.data_root / PRECOMPUTE_DIR
        self.client = client or Dojo()
        self._constituents_df: Optional[pd.DataFrame] = None
        self._sector_daily_df: Optional[pd.DataFrame] = None
        self._ticker_daily_df: Optional[pd.DataFrame] = None
        self._manifest: dict[str, Any] | None = None
        self._last_error: str | None = None

    def available(self) -> bool:
        return self.dataset_dir.exists() and (self.dataset_dir / MANIFEST_FILE).exists()

    def load(self) -> None:
        self.reload()

    def reload(self, dataset_dir: Path | None = None) -> None:
        target_dir = Path(dataset_dir).expanduser().resolve() if dataset_dir else self.dataset_dir
        manifest_path = target_dir / MANIFEST_FILE
        if manifest_path.exists():
            try:
                constituents_df = pd.read_parquet(target_dir / CONSTITUENTS_FILE)
                sector_daily_df = pd.read_parquet(target_dir / SECTOR_DAILY_FILE)
                ticker_daily_df = pd.read_parquet(target_dir / TICKER_DAILY_FILE)
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            except Exception as exc:
                self._last_error = f"local_reload_failed: {exc}"
                logger.warning("Failed to reload local sector precomputed snapshot: %s", exc)
            else:
                self.dataset_dir = target_dir
                self._constituents_df = constituents_df
                self._sector_daily_df = sector_daily_df
                self._ticker_daily_df = ticker_daily_df
                self._manifest = manifest
                self._last_error = None
                return
        self.clear_cache()
        self._load_from_sdk()

    def _load_from_sdk(self) -> None:
        try:
            constituents = self.client.sectors.get_precomputed_constituents()
            sector_daily = self.client.sectors.get_precomputed_sector_daily()
            ticker_daily = self.client.sectors.get_precomputed_ticker_daily()
            self._constituents_df = pd.DataFrame(constituents.data or [])
            self._sector_daily_df = pd.DataFrame(sector_daily.data or [])
            self._ticker_daily_df = pd.DataFrame(ticker_daily.data or [])
            self._manifest = {"source": "sdk_fallback"}
            self._last_error = None
        except Exception as exc:
            logger.warning("Failed to load sector precomputed data from SDK: %s", exc)
            self._last_error = f"sdk_reload_failed: {exc}"
            self._constituents_df = pd.DataFrame()
            self._sector_daily_df = pd.DataFrame()
            self._ticker_daily_df = pd.DataFrame()
            self._manifest = None

    def _load_constituents(self) -> pd.DataFrame:
        if self._constituents_df is None:
            self.reload()
        return self._constituents_df if self._constituents_df is not None else pd.DataFrame()

    def _load_sector_daily(self) -> pd.DataFrame:
        if self._sector_daily_df is None:
            self.reload()
        return self._sector_daily_df if self._sector_daily_df is not None else pd.DataFrame()

    def _load_ticker_daily(self) -> pd.DataFrame:
        if self._ticker_daily_df is None:
            self.reload()
        return self._ticker_daily_df if self._ticker_daily_df is not None else pd.DataFrame()

    def manifest(self) -> dict[str, Any] | None:
        return self._manifest

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

        mask = df["level1_id"] == level1_id
        if level2_id:
            mask &= df["level2_id"] == level2_id
        if level3_id:
            mask &= df["level3_id"] == level3_id
        if market:
            mask &= df["market"] == (normalize_market_code(market) or market)

        return df[mask].to_dict(orient="records")

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
        return df[mask].to_dict(orient="records")

    def get_sector_movers(self, date: str) -> list[dict]:
        df = self._load_sector_daily()
        if df.empty:
            return []
        target_date = date or str(df["trade_date"].max())
        return df[df["trade_date"] == target_date].to_dict(orient="records")

    def get_sector_movers_by_window(self, days: int) -> list[dict]:
        df = self._load_sector_daily()
        if df.empty:
            return []

        df_sorted = df.sort_values(by=["scope", "level1_id", "level2_id", "level3_id", "market", "trade_date"])
        if days <= 1:
            latest_date = df_sorted["trade_date"].max()
            return df_sorted[df_sorted["trade_date"] == latest_date].to_dict(orient="records")

        def calc_return(group: pd.DataFrame) -> float:
            if len(group) < 2:
                return float(group.iloc[-1]["daily_return_pct"])
            latest_idx = float(group.iloc[-1]["index_level"])
            past_idx = float(group.iloc[-min(days, len(group))]["index_level"])
            return (latest_idx / past_idx - 1) * 100 if past_idx > 0 else 0.0

        group_cols = ["scope", "level1_id", "level2_id", "level3_id", "market"]
        returns = df_sorted.groupby(group_cols).apply(calc_return).reset_index(name="change_percent")
        latest_rows = df_sorted.groupby(group_cols).tail(1).copy()
        latest_rows = latest_rows.drop(columns=["daily_return_pct", "change_percent"], errors="ignore")
        merged = pd.merge(latest_rows, returns, on=group_cols)
        merged["daily_return_pct"] = merged["change_percent"]
        return merged.to_dict(orient="records")

    def get_ticker_daily(self, date: str, tickers: list[str], market: str | None = None) -> list[dict]:
        df = self._load_ticker_daily()
        if df.empty:
            return []
        mask = (df["trade_date"] == date) & (df["ticker"].isin(tickers))
        if market:
            mask &= df["market"] == (normalize_market_code(market) or market)
        return df[mask].to_dict(orient="records")

    def get_ticker_daily_by_window(self, days: int, tickers: list[str], market: str | None = None) -> list[dict]:
        df = self._load_ticker_daily()
        if df.empty:
            return []

        mask = df["ticker"].isin(tickers)
        if market:
            mask &= df["market"] == (normalize_market_code(market) or market)
        df_sorted = df[mask].sort_values(by=["market", "ticker", "trade_date"])

        if days <= 1:
            latest_date = df_sorted["trade_date"].max()
            return df_sorted[df_sorted["trade_date"] == latest_date].to_dict(orient="records")

        def calc_return(group: pd.DataFrame) -> float:
            if len(group) < 2:
                return float(group.iloc[-1]["daily_return_pct"])
            latest_idx = float(group.iloc[-1]["close"])
            past_idx = float(group.iloc[-min(days, len(group))]["close"])
            return (latest_idx / past_idx - 1) * 100 if past_idx > 0 else 0.0

        group_cols = ["market", "ticker"]
        returns = df_sorted.groupby(group_cols).apply(calc_return).reset_index(name="change_percent")
        latest_rows = df_sorted.groupby(group_cols).tail(1).copy()
        latest_rows = latest_rows.drop(columns=["daily_return_pct", "change_percent"], errors="ignore")
        merged = pd.merge(latest_rows, returns, on=group_cols)
        merged["daily_return_pct"] = merged["change_percent"]
        return merged.to_dict(orient="records")

    def clear_cache(self) -> None:
        self._constituents_df = None
        self._sector_daily_df = None
        self._ticker_daily_df = None
        self._manifest = None
