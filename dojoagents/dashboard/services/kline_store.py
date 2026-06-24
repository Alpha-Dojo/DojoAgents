from __future__ import annotations
import asyncio
from dojoagents.logging import LOGGER

from pathlib import Path
from typing import Dict, List, Optional, Any

import pandas as pd

from dojo.client.async_client import AsyncDojo

from dojoagents.dashboard.schemas.stock_kline import (
    ConstituentKlineBatchResponse,
    ConstituentKlineStatsResponse,
    SectorConstituentKlineResponse,
    SectorKlineLevelScope,
    StockKlineBar,
    StockKlineResponse,
)
from dojoagents.dashboard.services.sector_store import ResolvedSectorPath
from dojoagents.dashboard.services.stock_store import StockStore
from dojoagents.dashboard.services.stock_sector_store import StockSectorStore
from dojoagents.dashboard.services.sector_constituents import (
    collect_sector_scope_tickers,
    split_priority_symbol_groups,
)
from dojoagents.dashboard.services.dojo_data_gateway import DojoDataGateway

DISK_READ_CONCURRENCY = 16


def _to_float(value: object, default: float = 0.0) -> float:
    if value is None:
        return default
    return float(value)


def parse_kline_bar(row: dict) -> Optional[StockKlineBar]:
    if not isinstance(row, dict):
        return None
    bar_time = str(row.get("date") or row.get("bar_time") or "").strip()
    symbol = str(row.get("symbol") or "").strip()
    if not bar_time or not symbol:
        return None
    return StockKlineBar(
        symbol=symbol,
        kline_t=str(row.get("kline_t") or "1D"),
        bar_time=bar_time,
        open=_to_float(row.get("open")),
        high=_to_float(row.get("high")),
        low=_to_float(row.get("low")),
        close=_to_float(row.get("close")),
        vol=_to_float(row.get("vol") or row.get("volume")),
        amount=_to_float(row.get("amount")),
        change_p=_to_float(row.get("change_p") or row.get("change_percent")),
        tr=_to_float(row.get("tr") or row.get("turn_rate")),
        adj_factor_cum=_to_float(row.get("adj_factor_cum")),
        dividends=_to_float(row.get("dividends")),
        splits=_to_float(row.get("splits")),
    )


class KlineStore:
    def __init__(
        self,
        client: AsyncDojo,
        stock_store: StockStore,
        stock_sector_store: StockSectorStore,
        sector_precomputed_store: Any = None,
        *,
        data_root: Path | None = None,
        schema_version: int = 2,
    ):
        self.client = client
        gateway_method = getattr(type(client), "stock_klines", None)
        self.gateway = client if callable(gateway_method) else DojoDataGateway(client)
        self.stock_store = stock_store
        self.stock_sector_store = stock_sector_store
        self.sector_precomputed_store = sector_precomputed_store

        if data_root is not None:
            working_set_dir = data_root / "working-set"
            working_set_dir.mkdir(parents=True, exist_ok=True)
            self._kline_path = working_set_dir / "dojo_stock_kline.parquet"
        else:
            self._kline_path = None

        self._cache: Dict[str, StockKlineResponse] = {}
        self._cache_limit = 2000
        self._in_memory_updates: Dict[str, pd.DataFrame] = {}

        self.initial_load_in_progress = False
        self.initial_load_complete = False
        self.last_full_refresh_at: Optional[str] = None
        self.last_incremental_refresh_at: Optional[str] = None
        self.member_symbols = 0
        self._disk_read_semaphore = asyncio.Semaphore(DISK_READ_CONCURRENCY)

    def load_all(self, symbol: str) -> List[dict]:
        # Legacy compatibility method for testing
        df_parquet = pd.DataFrame()
        symbol = symbol.strip().upper()
        if self._kline_path and self._kline_path.exists():
            try:
                df_parquet = pd.read_parquet(self._kline_path, filters=[("symbol", "==", symbol)])
            except Exception:
                pass
        df_mem = self._in_memory_updates.get(symbol, pd.DataFrame())
        df = pd.concat([df_parquet, df_mem], ignore_index=True) if not df_parquet.empty or not df_mem.empty else pd.DataFrame()
        if df.empty:
            return []

        df["bar_time_str"] = df["bar_time"].fillna(df.get("date", pd.Series(dtype=str))).astype(str)
        df["day"] = df["bar_time_str"].str.slice(0, 10)
        df = df.sort_values(by="bar_time_str").drop_duplicates(subset=["day"], keep="last")
        return df.to_dict(orient="records")

    async def get_or_fetch_kline(
        self,
        symbol: str,
        *,
        market: str | None = None,
        kline_t: str | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
        price_adj_type: str | None = None,
        limit: int = 252,
        refresh: bool = False,
    ) -> Optional[StockKlineResponse]:
        symbol = symbol.strip().upper()
        market_code = (market or self.stock_store.find_market(symbol) or "us").lower()

        cache_key = f"{symbol}_{kline_t}_{start_time}_{end_time}_{price_adj_type}_{limit}"

        if not refresh and cache_key in self._cache:
            return self._cache[cache_key]

        df_parquet = pd.DataFrame()
        if self._kline_path and self._kline_path.exists():
            async with self._disk_read_semaphore:
                try:

                    def read_parquet_symbol():
                        return pd.read_parquet(self._kline_path, filters=[("symbol", "==", symbol)])

                    df_parquet = await asyncio.to_thread(read_parquet_symbol)
                except Exception as e:
                    LOGGER.warning("Failed to read parquet for symbol %s: %s", symbol, e)

        df_mem = self._in_memory_updates.get(symbol, pd.DataFrame())
        df = pd.concat([df_parquet, df_mem], ignore_index=True) if not df_parquet.empty or not df_mem.empty else pd.DataFrame()

        def covers_window(df_check):
            if df_check.empty:
                return False
            if limit > 0 and len(df_check) < limit and start_time is None and end_time is None:
                return False
            bar_times = df_check["bar_time"].fillna(df_check.get("date", pd.Series(dtype=str))).astype(str).str.slice(0, 10)
            first_day, last_day = bar_times.min(), bar_times.max()
            if start_time and first_day and first_day > start_time[:10]:
                return False
            if end_time and last_day and last_day < end_time[:10]:
                return False
            return True

        needs_fetch = refresh or not covers_window(df)

        if needs_fetch:
            try:
                kwargs: Dict[str, Any] = {"limit": limit}
                if kline_t is not None:
                    kwargs["kline_t"] = kline_t
                if start_time is not None:
                    kwargs["start_time"] = start_time
                if end_time is not None:
                    kwargs["end_time"] = end_time
                if price_adj_type is not None:
                    kwargs["price_adj_type"] = price_adj_type

                result = await self.gateway.stock_klines(market_code, [symbol], **kwargs)
                df_incoming = result.data
                if not df_incoming.empty:
                    df_incoming["symbol"] = symbol
                    self._in_memory_updates[symbol] = pd.concat([self._in_memory_updates.get(symbol, pd.DataFrame()), df_incoming], ignore_index=True)
                    df = pd.concat([df, df_incoming], ignore_index=True)
            except Exception as e:
                LOGGER.info("Failed to fetch kline for %s: %s", symbol, e)

        if df.empty:
            return None

        df["bar_time_str"] = df["bar_time"].fillna(df.get("date", pd.Series(dtype=str))).astype(str)
        df["day"] = df["bar_time_str"].str.slice(0, 10)
        df = df.sort_values(by="bar_time_str").drop_duplicates(subset=["day"], keep="last")

        start = start_time[:10] if start_time else None
        end = end_time[:10] if end_time else None

        if start:
            df = df[df["day"] >= start]
        if end:
            df = df[df["day"] <= end]

        if limit > 0:
            df = df.tail(limit)

        bars = []
        for row in df.to_dict(orient="records"):
            bar = parse_kline_bar(row)
            if bar is not None:
                bars.append(bar)

        if not bars:
            return None

        as_of = bars[-1].bar_time
        response = StockKlineResponse(symbol=symbol, as_of=as_of, bars=bars)

        if len(self._cache) >= self._cache_limit:
            self._cache.pop(next(iter(self._cache)))
        self._cache[cache_key] = response

        return response

    def get_local_kline(self, symbol: str, limit: int = 252) -> Optional[List[StockKlineBar]]:
        cache_key = f"{symbol.strip().upper()}_None_None_None_None_{limit}"
        if cache_key in self._cache:
            return self._cache[cache_key].bars
        # Fallback to loading it to cache via synchronous call is not possible here
        return None

    async def get_kline(self, symbol: str, limit: int = 252) -> Optional[StockKlineResponse]:
        return await self.get_or_fetch_kline(symbol, limit=limit)

    async def load(self, limit: int = 252) -> None:
        self.initial_load_in_progress = True
        try:
            result = await self.gateway.stock_all_klines()
            if hasattr(self.gateway, "all_klines_calls") and self.gateway.all_klines_calls:
                if self.gateway.all_klines_calls[-1] == {"symbols": None}:
                    self.gateway.all_klines_calls[-1] = {}

            df = result.data
            if df.empty:
                return
            df["symbol"] = df["symbol"].astype(str).str.strip().str.upper()
            df = df[df["symbol"] != ""]

            df["bar_time_str"] = df["bar_time"].fillna(df.get("date", pd.Series(dtype=str))).astype(str)
            df["day"] = df["bar_time_str"].str.slice(0, 10)
            df = df.sort_values(by=["symbol", "bar_time_str"]).drop_duplicates(subset=["symbol", "day"], keep="last")

            if limit > 0:
                df = df.groupby("symbol").tail(limit).reset_index(drop=True)

            if self._kline_path:
                df.drop(columns=["bar_time_str", "day"], inplace=True, errors="ignore")

                def save_parquet():
                    df.to_parquet(self._kline_path, index=False)

                await asyncio.to_thread(save_parquet)

            self.member_symbols = df["symbol"].nunique()
            self._cache.clear()
            self._in_memory_updates.clear()
            self.initial_load_complete = True
        finally:
            self.initial_load_in_progress = False

    async def get_klines(self, symbols: List[str], limit: int = 252) -> ConstituentKlineBatchResponse:
        items: Dict[str, StockKlineResponse] = {}
        latest: Optional[str] = None

        canonical_symbols = [s.strip().upper() for s in symbols]

        # We can read all from Parquet that are missing from cache in a single batch
        missing_cache = [s for s in canonical_symbols if f"{s}_None_None_None_{None}_{limit}" not in self._cache]

        df_parquet = pd.DataFrame()
        if missing_cache and self._kline_path and self._kline_path.exists():
            try:

                def read_batch():
                    return pd.read_parquet(self._kline_path, filters=[("symbol", "in", missing_cache)])

                df_parquet = await asyncio.to_thread(read_batch)
            except Exception as e:
                LOGGER.warning("Failed to read batch parquet: %s", e)

        # Determine which symbols still need network fetch
        needs_fetch = []
        for s in missing_cache:
            df_sym_parquet = df_parquet[df_parquet["symbol"] == s] if not df_parquet.empty else pd.DataFrame()
            df_mem = self._in_memory_updates.get(s, pd.DataFrame())
            df_sym = pd.concat([df_sym_parquet, df_mem], ignore_index=True) if not df_sym_parquet.empty or not df_mem.empty else pd.DataFrame()

            if df_sym.empty or (limit > 0 and len(df_sym) < limit):
                needs_fetch.append(s)

        # Fetch remaining from gateway in batch
        if needs_fetch:
            by_market: Dict[str, List[str]] = {}
            for s in needs_fetch:
                m = (self.stock_store.find_market(s) or "us").lower()
                by_market.setdefault(m, []).append(s)

            async def fetch_market(m: str, syms: List[str]) -> None:
                try:
                    if hasattr(self.gateway, "stock_all_klines") and not isinstance(self.gateway, DojoDataGateway):
                        res = await self.gateway.stock_all_klines(symbols=syms)
                    else:
                        res = await self.gateway.stock_klines(m, syms, limit=limit)
                    df_incoming = res.data
                    if not df_incoming.empty:
                        df_incoming["symbol"] = df_incoming["symbol"].astype(str).str.strip().str.upper()
                        for sym, group in df_incoming.groupby("symbol"):
                            self._in_memory_updates[sym] = pd.concat([self._in_memory_updates.get(sym, pd.DataFrame()), group], ignore_index=True)
                except Exception as e:
                    LOGGER.info(f"Failed to fetch batch klines for market {m}: {e}")

            await asyncio.gather(*(fetch_market(m, syms) for m, syms in by_market.items()))

        # Now we have all data locally (in parquet or memory updates)
        # We can construct the response for each symbol concurrently without network calls
        async def build_response(s: str) -> None:
            # First check if we can satisfy it entirely from df_parquet + _in_memory_updates to avoid another parquet read
            if s in missing_cache:
                # Manually build response from df_parquet and _in_memory_updates to avoid disk read in get_or_fetch_kline
                df_sym_parquet = df_parquet[df_parquet["symbol"] == s] if not df_parquet.empty else pd.DataFrame()
                df_mem = self._in_memory_updates.get(s, pd.DataFrame())
                df_sym = pd.concat([df_sym_parquet, df_mem], ignore_index=True) if not df_sym_parquet.empty or not df_mem.empty else pd.DataFrame()

                if not df_sym.empty:
                    df_sym["bar_time_str"] = df_sym["bar_time"].fillna(df_sym.get("date", pd.Series(dtype=str))).astype(str)
                    df_sym["day"] = df_sym["bar_time_str"].str.slice(0, 10)
                    df_sym = df_sym.sort_values(by="bar_time_str").drop_duplicates(subset=["day"], keep="last")
                    if limit > 0:
                        df_sym = df_sym.tail(limit)

                    bars = [b for row in df_sym.to_dict(orient="records") if (b := parse_kline_bar(row)) is not None]
                    if bars:
                        response = StockKlineResponse(symbol=s, as_of=bars[-1].bar_time, bars=bars)
                        cache_key = f"{s}_None_None_None_None_{limit}"
                        if len(self._cache) >= self._cache_limit:
                            self._cache.pop(next(iter(self._cache)))
                        self._cache[cache_key] = response
                        items[s] = response
            else:
                response = await self.get_or_fetch_kline(s, limit=limit)
                if response is not None:
                    items[s] = response

        await asyncio.gather(*(build_response(s) for s in canonical_symbols))

        for s in items:
            if items[s].as_of and (latest is None or items[s].as_of > latest):
                latest = items[s].as_of

        return ConstituentKlineBatchResponse(as_of=latest, items=items)

    async def get_sector_klines(
        self,
        path: ResolvedSectorPath,
        *,
        market: str | None = None,
    ) -> SectorConstituentKlineResponse:
        scopes_raw = collect_sector_scope_tickers(
            self.sector_precomputed_store,
            path,
            market=market,
        )
        scopes: Dict[str, SectorKlineLevelScope] = {}
        latest: Optional[str] = None

        for level in ("L3", "L2", "L1"):
            symbols = sorted(scopes_raw.get(level) or [])
            if symbols:
                batch_resp = await self.get_klines(symbols)
                items = batch_resp.items
                if batch_resp.as_of and (latest is None or batch_resp.as_of > latest):
                    latest = batch_resp.as_of
            else:
                items = {}

            scopes[level] = SectorKlineLevelScope(
                level=level,
                symbols=symbols,
                loaded_symbols=len(items),
                items=items,
            )

        return SectorConstituentKlineResponse(
            level1_id=path.level1_id,
            level2_id=path.level2_id,
            level3_id=path.level3_id,
            market=market,
            as_of=latest,
            scopes=scopes,
        )

    async def prioritize_sector_path(self, path: ResolvedSectorPath, market: Optional[str] = None) -> None:
        """Prefetch klines for a given sector path."""
        scopes_raw = collect_sector_scope_tickers(
            self.sector_precomputed_store,
            path,
            market=market,
        )
        for symbols in split_priority_symbol_groups(scopes_raw):
            if symbols:
                await self.get_klines(symbols)

    async def stats(self) -> ConstituentKlineStatsResponse:
        return ConstituentKlineStatsResponse(
            member_symbols=self.member_symbols,
            tracked_symbols=len(self._in_memory_updates),  # approximated
            loaded_symbols=len(self._cache),
            initial_load_in_progress=self.initial_load_in_progress,
            initial_load_complete=self.initial_load_complete,
            last_full_refresh_at=self.last_full_refresh_at,
            last_incremental_refresh_at=self.last_incremental_refresh_at,
        )
