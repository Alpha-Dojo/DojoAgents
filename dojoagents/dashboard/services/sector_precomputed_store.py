from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional
import pandas as pd
from dojoagents.config.loader import FinancialDashboardConfig

logger = logging.getLogger(__name__)


class SectorPrecomputedStore:
    def __init__(self, data_root: Path | None = None) -> None:
        self.data_root = data_root or FinancialDashboardConfig.dashboard_data_root
        self.precompute_dir = self.data_root / "datasets" / "dojo_sector_precomputed"

        self.constituents_path = self.precompute_dir / "constituents.parquet"
        self.sector_daily_path = self.precompute_dir / "sector_daily.parquet"
        self.ticker_daily_path = self.precompute_dir / "ticker_daily.parquet"

        self._constituents_df: Optional[pd.DataFrame] = None
        self._sector_daily_df: Optional[pd.DataFrame] = None
        self._ticker_daily_df: Optional[pd.DataFrame] = None

    def _load_constituents(self) -> pd.DataFrame:
        if self._constituents_df is None:
            if not self.constituents_path.exists():
                logger.warning(f"Missing {self.constituents_path}")
                return pd.DataFrame()
            self._constituents_df = pd.read_parquet(self.constituents_path)
        return self._constituents_df

    def _load_sector_daily(self) -> pd.DataFrame:
        if self._sector_daily_df is None:
            if not self.sector_daily_path.exists():
                logger.warning(f"Missing {self.sector_daily_path}")
                return pd.DataFrame()
            self._sector_daily_df = pd.read_parquet(self.sector_daily_path)
        return self._sector_daily_df

    def _load_ticker_daily(self) -> pd.DataFrame:
        if self._ticker_daily_df is None:
            if not self.ticker_daily_path.exists():
                logger.warning(f"Missing {self.ticker_daily_path}")
                return pd.DataFrame()
            self._ticker_daily_df = pd.read_parquet(self.ticker_daily_path)
        return self._ticker_daily_df

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
            mask &= df["market"] == market

        filtered = df[mask]
        return filtered.to_dict(orient="records")

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
            mask &= df["market"] == market

        filtered = df[mask]
        return filtered.to_dict(orient="records")

    def get_sector_movers(self, date: str) -> list[dict]:
        df = self._load_sector_daily()
        if df.empty:
            return []
        if date is None:
            # use max trade_date
            date = df["trade_date"].max()
        mask = df["trade_date"] == date
        return df[mask].to_dict(orient="records")

    def get_sector_movers_by_window(self, days: int) -> list[dict]:
        df = self._load_sector_daily()
        if df.empty:
            return []

        # Calculate N-day return for each sector
        # For each scope, level1_id, level2_id, level3_id, market: get latest index_level / index_level (days ago)
        df_sorted = df.sort_values(by=["scope", "level1_id", "level2_id", "level3_id", "market", "trade_date"])

        if days <= 1:
            # Just return the latest day's daily_return_pct
            latest_date = df_sorted["trade_date"].max()
            mask = df_sorted["trade_date"] == latest_date
            return df_sorted[mask].to_dict(orient="records")

        def calc_return(group):
            if len(group) < 2:
                return group.iloc[-1]["daily_return_pct"]
            latest_idx = group.iloc[-1]["index_level"]
            past_idx = group.iloc[-min(days, len(group))]["index_level"]
            ret = (latest_idx / past_idx - 1) * 100 if past_idx > 0 else 0
            return ret

        returns = df_sorted.groupby(["scope", "level1_id", "level2_id", "level3_id", "market"]).apply(calc_return).reset_index(name="change_percent")
        # merge with latest row to get member_count, etc.
        latest_rows = df_sorted.groupby(["scope", "level1_id", "level2_id", "level3_id", "market"]).tail(1).copy()

        # Drop the daily_return_pct and add change_percent
        latest_rows = latest_rows.drop(columns=["daily_return_pct", "change_percent"], errors="ignore")
        merged = pd.merge(latest_rows, returns, on=["scope", "level1_id", "level2_id", "level3_id", "market"])
        merged["daily_return_pct"] = merged["change_percent"]
        return merged.to_dict(orient="records")

    def get_ticker_daily(self, date: str, tickers: list[str]) -> list[dict]:
        df = self._load_ticker_daily()
        if df.empty:
            return []
        mask = (df["trade_date"] == date) & (df["ticker"].isin(tickers))
        return df[mask].to_dict(orient="records")

    def get_ticker_daily_by_window(self, days: int, tickers: list[str]) -> list[dict]:
        df = self._load_ticker_daily()
        if df.empty:
            return []

        mask = df["ticker"].isin(tickers)
        df_filtered = df[mask]
        df_sorted = df_filtered.sort_values(by=["ticker", "trade_date"])

        if days <= 1:
            latest_date = df_sorted["trade_date"].max()
            mask = df_sorted["trade_date"] == latest_date
            return df_sorted[mask].to_dict(orient="records")

        def calc_return(group):
            if len(group) < 2:
                return group.iloc[-1]["daily_return_pct"]
            latest_idx = group.iloc[-1]["close"]
            past_idx = group.iloc[-min(days, len(group))]["close"]
            ret = (latest_idx / past_idx - 1) * 100 if past_idx > 0 else 0
            return ret

        returns = df_sorted.groupby(["ticker"]).apply(calc_return).reset_index(name="change_percent")
        latest_rows = df_sorted.groupby(["ticker"]).tail(1).copy()
        latest_rows = latest_rows.drop(columns=["daily_return_pct", "change_percent"], errors="ignore")
        merged = pd.merge(latest_rows, returns, on=["ticker"])
        merged["daily_return_pct"] = merged["change_percent"]
        return merged.to_dict(orient="records")

    def clear_cache(self) -> None:
        self._constituents_df = None
        self._sector_daily_df = None
        self._ticker_daily_df = None
