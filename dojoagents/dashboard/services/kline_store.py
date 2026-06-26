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
        price_adj_type: str | None = None,
        limit: int = 252,
        refresh: bool = False,
    ) -> Optional[StockKlineResponse]:
        symbol = symbol.strip().upper()
        cache_key = f"{symbol}_{kline_t}_{start_time}_{end_time}_{price_adj_type}_{limit}"

        if not refresh and cache_key in self._cache:
            return self._cache[cache_key]

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

            result = await self.gateway.stock_klines([symbol], **kwargs)
            df = result.data
        except Exception as e:
            LOGGER.exception("Failed to fetch kline for %s: %s", symbol, e)
            raise e

        df = df.sort_values(by="bar_time")

        start = start_time[:10] if start_time else None
        end = end_time[:10] if end_time else None

        if start:
            df = df[df["bar_time"] >= start]
        if end:
            df = df[df["bar_time"] <= end]

        if limit > 0:
            df = df.tail(limit)

        bars = [b for row in df.to_dict(orient="records") if (b := parse_kline_bar(row)) is not None]
        if not bars:
            return None
        as_of = bars[-1].bar_time
        response = StockKlineResponse(symbol=symbol, as_of=as_of, bars=bars)

        if len(self._cache) >= self._cache_limit:
            self._cache.pop(next(iter(self._cache)))
        self._cache[cache_key] = response

        return response

    async def get_kline(self, symbol: str, limit: int = 252) -> Optional[StockKlineResponse]:
        return await self.get_or_fetch_kline(symbol, limit=limit)

    async def load(self, limit: int = 252) -> None:
        self.initial_load_in_progress = True
        try:
            result = await self.gateway.stock_all_klines()
            df = result.data
            if df.empty:
                return
            df["symbol"] = df["symbol"].astype(str).str.strip().str.upper()
            df = df[df["symbol"] != ""]
            df = df.sort_values(by=["symbol", "bar_time"]).drop_duplicates(subset=["symbol", "bar_time"], keep="last")

            if limit > 0:
                df = df.groupby("symbol").tail(limit).reset_index(drop=True)

            self.member_symbols = df["symbol"].nunique()
            self._cache.clear()
            self.initial_load_complete = True
        finally:
            self.initial_load_in_progress = False

    async def get_klines(self, symbols: List[str], limit: int = 252) -> ConstituentKlineBatchResponse:
        items: Dict[str, StockKlineResponse] = {}
        latest: Optional[str] = None

        canonical_symbols = [s.strip().upper() for s in symbols]

        missing_cache = [s for s in canonical_symbols if f"{s}_None_None_None_{None}_{limit}" not in self._cache]
        results = await self.gateway.stock_klines(canonical_symbols, limit=limit)
        df_all = results.data

        # Build each symbol's response from the single batched gateway result to avoid per-symbol fetches.
        async def build_response(s: str) -> None:
            if s in missing_cache:
                df_sym = df_all[df_all["symbol"] == s] if not df_all.empty else pd.DataFrame()

                if not df_sym.empty:
                    df_sym = df_sym.sort_values(by="bar_time")
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
