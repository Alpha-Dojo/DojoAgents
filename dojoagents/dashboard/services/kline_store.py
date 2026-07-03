from __future__ import annotations
import asyncio
from dojoagents.logging import LOGGER

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
)
from dojoagents.dashboard.services.dojo_data_gateway import DojoDataGateway
from dojoagents.dashboard.services.kline_bar_utils import (
    DATA_START_DATE,
    KLINE_LIMIT,
    KLINE_MAX_LIMIT,
    normalize_datetime,
    resolve_kline_limit_for_elapsed_days,
    resolve_tail_limit,
)


def _to_float(value: object, default: float = 0.0) -> float:
    if value is None:
        return default
    return float(value)


def parse_kline_bar(row: dict, *, default_symbol: str = "") -> Optional[StockKlineBar]:
    if not isinstance(row, dict):
        return None
    bar_time = normalize_datetime(row.get("date") or row.get("bar_time") or row.get("datetime"))
    symbol = str(row.get("symbol") or row.get("ticker") or default_symbol or "").strip()
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


def _prepare_kline_df(df: pd.DataFrame, *, symbol: str) -> pd.DataFrame:
    if df.empty:
        return df
    prepared = df.copy()
    time_col = "bar_time" if "bar_time" in prepared.columns else "date" if "date" in prepared.columns else None
    if time_col is None:
        return prepared.iloc[0:0].copy()
    prepared["bar_time"] = prepared[time_col].map(
        lambda value: normalize_datetime(value) or str(value).strip()[:10]
    )
    if "symbol" not in prepared.columns:
        prepared["symbol"] = symbol
    else:
        prepared["symbol"] = prepared["symbol"].fillna(symbol).astype(str).str.strip().str.upper()
        prepared.loc[prepared["symbol"] == "", "symbol"] = symbol
    prepared = prepared[prepared["bar_time"].astype(str).str.len() >= 10]
    return prepared


class KlineStore:
    def __init__(
        self,
        client: AsyncDojo,
        stock_store: StockStore,
        stock_sector_store: StockSectorStore,
        sector_precomputed_store: Any = None,
    ):
        self.client = client
        gateway_method = getattr(type(client), "stock_klines", None)
        self.gateway = client if callable(gateway_method) else DojoDataGateway(client)
        self.stock_store = stock_store
        self.stock_sector_store = stock_sector_store
        self.sector_precomputed_store = sector_precomputed_store
        self._cache: Dict[str, StockKlineResponse] = {}
        self._cache_limit = 2000
        self.initial_load_in_progress = False
        self.initial_load_complete = False
        self.last_full_refresh_at: Optional[str] = None
        self.last_incremental_refresh_at: Optional[str] = None
        self.member_symbols = 0

    async def get_or_fetch_kline(
        self,
        symbol: str,
        *,
        market: str | None = None,
        kline_t: str | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
        min_bar_time: str | None = None,
        price_adj_type: str | None = None,
        limit: int | None = None,
        refresh: bool = False,
    ) -> Optional[StockKlineResponse]:
        symbol = symbol.strip().upper()
        resolved_limit = resolve_tail_limit(
            start_time=start_time,
            end_time=end_time,
            limit=limit,
        )
        if min_bar_time and not start_time:
            resolved_limit = 0
        cache_key = (
            f"{symbol}_{kline_t}_{start_time}_{end_time}_{min_bar_time}_{price_adj_type}_{resolved_limit}"
        )

        if not refresh and cache_key in self._cache:
            return self._cache[cache_key]

        try:
            if resolved_limit > 0:
                fetch_limit = resolved_limit
            elif start_time or end_time or min_bar_time:
                fetch_limit = resolve_kline_limit_for_elapsed_days(
                    start_time or min_bar_time or DATA_START_DATE,
                    end_date=end_time,
                )
            else:
                fetch_limit = KLINE_LIMIT
            kwargs: Dict[str, Any] = {}
            if fetch_limit > 0:
                kwargs["limit"] = fetch_limit
            if start_time:
                kwargs["start_time"] = start_time
            if end_time:
                kwargs["end_time"] = end_time
            if kline_t is not None:
                kwargs["kline_t"] = kline_t
            if price_adj_type is not None:
                kwargs["price_adj_type"] = price_adj_type

            result = await self.gateway.stock_klines([symbol], **kwargs)
            df = result.data
        except Exception as e:
            LOGGER.exception("Failed to fetch kline for %s: %s", symbol, e)
            raise e

        if df.empty:
            return None

        df = _prepare_kline_df(df, symbol=symbol)

        if df.empty:
            return None

        if not df["bar_time"].is_monotonic_increasing:   # already sorted
            df = df.sort_values("bar_time")

        filter_start = (start_time[:10] if start_time else None) or (
            min_bar_time[:10] if min_bar_time else None
        )
        filter_end = end_time[:10] if end_time else None

        if filter_start:
            df = df[df["bar_time"] >= filter_start]
        if filter_end:
            df = df[df["bar_time"] <= filter_end]

        if resolved_limit > 0 and len(df) > resolved_limit:
            df = df.iloc[-resolved_limit:]

        bars = [
            bar
            for row in df.to_dict(orient="records")
            if (bar := parse_kline_bar(row, default_symbol=symbol)) is not None
        ]
        if not bars:
            return None
        as_of = bars[-1].bar_time
        response = StockKlineResponse(symbol=symbol, as_of=as_of, bars=bars)

        if len(self._cache) >= self._cache_limit:
            self._cache.pop(next(iter(self._cache)))
        self._cache[cache_key] = response

        return response

    async def get_kline(self, symbol: str, limit: int | None = None) -> Optional[StockKlineResponse]:
        return await self.get_or_fetch_kline(symbol, limit=limit)

    async def load(self, limit: int | None = None) -> None:
        resolved_limit = limit if limit is not None else KLINE_MAX_LIMIT
        self.initial_load_in_progress = True
        try:
            if hasattr(self.gateway, "warm_kline_index"):
                await self.gateway.warm_kline_index()
                index = getattr(self.gateway, "_kline_symbol_index", None)
                self.member_symbols = len(index) if index else 0
            else:
                result = await self.gateway.stock_all_klines()
                df = result.data
                if df.empty:
                    return
                df["symbol"] = df["symbol"].astype(str).str.strip().str.upper()
                df = df[df["symbol"] != ""]
                df = df.sort_values(by=["symbol", "bar_time"]).drop_duplicates(
                    subset=["symbol", "bar_time"], keep="last"
                )

                if resolved_limit > 0:
                    df = df.groupby("symbol").tail(resolved_limit).reset_index(drop=True)

                self.member_symbols = df["symbol"].nunique()

            self._cache.clear()
            self.initial_load_complete = True
        finally:
            self.initial_load_in_progress = False

    async def get_klines(
        self,
        symbols: List[str],
        limit: int | None = None,
    ) -> ConstituentKlineBatchResponse:
        resolved_limit = (
            limit
            if limit is not None
            else resolve_kline_limit_for_elapsed_days(DATA_START_DATE)
        )
        items: Dict[str, StockKlineResponse] = {}
        latest: Optional[str] = None

        canonical_symbols = [s.strip().upper() for s in symbols]

        missing_cache = [
            s
            for s in canonical_symbols
            if f"{s}_None_None_None_{None}_{resolved_limit}" not in self._cache
        ]
        results = await self.gateway.stock_klines(canonical_symbols, limit=resolved_limit)
        df_all = results.data

        # Build each symbol's response from the single batched gateway result to avoid per-symbol fetches.
        async def build_response(s: str) -> None:
            if s in missing_cache:
                df_sym = df_all[df_all["symbol"] == s] if not df_all.empty else pd.DataFrame()

                if not df_sym.empty:
                    df_sym = df_sym.sort_values(by="bar_time")
                    if resolved_limit > 0:
                        df_sym = df_sym.tail(resolved_limit)

                    bars = [b for row in df_sym.to_dict(orient="records") if (b := parse_kline_bar(row)) is not None]
                    if bars:
                        response = StockKlineResponse(symbol=s, as_of=bars[-1].bar_time, bars=bars)
                        cache_key = f"{s}_None_None_None_None_{resolved_limit}"
                        if len(self._cache) >= self._cache_limit:
                            self._cache.pop(next(iter(self._cache)))
                        self._cache[cache_key] = response
                        items[s] = response
            else:
                response = await self.get_or_fetch_kline(s, limit=resolved_limit)
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

    async def stats(self) -> ConstituentKlineStatsResponse:
        return ConstituentKlineStatsResponse(
            member_symbols=self.member_symbols,
            tracked_symbols=len(self._cache),
            loaded_symbols=len(self._cache),
            initial_load_in_progress=self.initial_load_in_progress,
            initial_load_complete=self.initial_load_complete,
            last_full_refresh_at=self.last_full_refresh_at,
            last_incremental_refresh_at=self.last_incremental_refresh_at,
        )
