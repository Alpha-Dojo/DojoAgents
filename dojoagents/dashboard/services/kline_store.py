from __future__ import annotations

import asyncio
import inspect
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from dojo.client.async_client import AsyncDojo

from dojoagents.logging import LOGGER
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
    # KLINE_MAX_LIMIT,
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
    prepared["bar_time"] = prepared[time_col].map(lambda value: normalize_datetime(value) or str(value).strip()[:10])
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
        data_root: Path | None = None,
    ):
        self.client = client
        gateway_method = getattr(type(client), "stock_klines", None)
        self.gateway = client if callable(gateway_method) else DojoDataGateway(client)
        self.stock_store = stock_store
        self.stock_sector_store = stock_sector_store
        self.sector_precomputed_store = sector_precomputed_store
        self.data_root = data_root.expanduser().resolve() if data_root else None
        self._parquet_path = self.data_root / "working-set" / "dojo_stock_kline.parquet" if self.data_root else None
        self._cache: Dict[str, StockKlineResponse] = {}
        self._cache_limit = 2000
        self._in_memory_updates: dict[str, pd.DataFrame] = {}
        self.raw_by_symbol: dict[str, list[dict[str, Any]]] = {}
        self._disk_loaded = False
        self.initial_load_in_progress = False
        self.initial_load_complete = False
        self.last_full_refresh_at: Optional[str] = None
        self.last_incremental_refresh_at: Optional[str] = None
        self.member_symbols = 0

    @staticmethod
    def _to_frame(value: Any) -> pd.DataFrame:
        if isinstance(value, pd.DataFrame):
            return value.copy()
        return pd.DataFrame(value or [])

    async def _gateway_klines(
        self,
        symbols: list[str],
        *,
        market: str | None = None,
        **window: Any,
    ) -> Any:
        method = self.gateway.stock_klines
        parameters = tuple(inspect.signature(method).parameters)
        if parameters and parameters[0] == "market":
            return await method(market, symbols, **window)
        return await method(symbols, **window)

    def _load_disk_once(self) -> None:
        if self._disk_loaded:
            return
        self._disk_loaded = True
        path = self._parquet_path
        if path is None or not path.exists():
            return
        try:
            frame = self._to_frame(pd.read_parquet(path))
        except Exception:
            LOGGER.warning("Ignoring unreadable kline working set: %s", path)
            return
        self._replace_memory(frame)

    def _replace_memory(self, frame: pd.DataFrame) -> None:
        if frame.empty:
            return
        prepared = _prepare_kline_df(frame, symbol="")
        if prepared.empty:
            return
        prepared = prepared.sort_values(["symbol", "bar_time"]).drop_duplicates(
            subset=["symbol", "bar_time"],
            keep="last",
        )
        self._in_memory_updates = {symbol: rows.reset_index(drop=True) for symbol, rows in prepared.groupby("symbol", sort=False)}
        self.raw_by_symbol = {symbol: rows.to_dict(orient="records") for symbol, rows in self._in_memory_updates.items()}
        self.member_symbols = len(self._in_memory_updates)

    def _merge_memory(self, frame: pd.DataFrame) -> None:
        if frame.empty:
            return
        prepared = _prepare_kline_df(frame, symbol="")
        for symbol, rows in prepared.groupby("symbol", sort=False):
            current = self._in_memory_updates.get(symbol)
            merged = rows if current is None or current.empty else pd.concat([current, rows], ignore_index=True)
            merged = merged.sort_values("bar_time").drop_duplicates(
                subset=["bar_time"],
                keep="last",
            )
            self._in_memory_updates[symbol] = merged.reset_index(drop=True)
            self.raw_by_symbol[symbol] = merged.to_dict(orient="records")
        self.member_symbols = len(self._in_memory_updates)

    def _persist_memory(self) -> None:
        path = self._parquet_path
        frames = [frame for frame in self._in_memory_updates.values() if not frame.empty]
        if path is None or not frames:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".parquet.tmp")
        pd.concat(frames, ignore_index=True).to_parquet(temporary, index=False)
        temporary.replace(path)

    def load_all(self, symbol: str) -> list[dict[str, Any]]:
        self._load_disk_once()
        canonical = symbol.strip().upper()
        if canonical in self.raw_by_symbol:
            return list(self.raw_by_symbol[canonical])
        frame = self._in_memory_updates.get(canonical)
        return [] if frame is None else frame.to_dict(orient="records")

    def _memory_frame(self, symbol: str) -> pd.DataFrame:
        rows = self.load_all(symbol)
        return self._to_frame(rows)

    def _cache_response(
        self,
        cache_key: str,
        symbol: str,
        frame: pd.DataFrame,
        *,
        start_time: str | None = None,
        end_time: str | None = None,
        min_bar_time: str | None = None,
        limit: int = 0,
    ) -> Optional[StockKlineResponse]:
        if frame.empty:
            return None
        prepared = _prepare_kline_df(frame, symbol=symbol)
        filter_start = (start_time or min_bar_time or "")[:10]
        filter_end = (end_time or "")[:10]
        if filter_start:
            prepared = prepared[prepared["bar_time"] >= filter_start]
        if filter_end:
            prepared = prepared[prepared["bar_time"] <= filter_end]
        if limit > 0:
            prepared = prepared.tail(limit)
        bars = [bar for row in prepared.to_dict(orient="records") if (bar := parse_kline_bar(row, default_symbol=symbol)) is not None]
        if not bars:
            return None
        response = StockKlineResponse(
            symbol=symbol,
            as_of=bars[-1].bar_time,
            bars=bars,
        )
        if len(self._cache) >= self._cache_limit:
            self._cache.pop(next(iter(self._cache)))
        self._cache[cache_key] = response
        return response

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
        cache_key = f"{symbol}_{kline_t}_{start_time}_{end_time}_{min_bar_time}_{price_adj_type}_{resolved_limit}"

        if not refresh and cache_key in self._cache:
            return self._cache[cache_key]

        self._load_disk_once()
        local_frame = self._memory_frame(symbol)
        try:
            if resolved_limit > 0:
                fetch_limit = resolved_limit
            elif start_time or end_time:
                # Explicit date window: omit SDK limit. A small limit (e.g. 40 for one
                # calendar day) truncates to early bars and drops the requested day.
                fetch_limit = 0
            elif min_bar_time:
                fetch_limit = resolve_kline_limit_for_elapsed_days(
                    min_bar_time or DATA_START_DATE,
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

            result = await self._gateway_klines(
                [symbol],
                market=market,
                **kwargs,
            )
            df = self._to_frame(result.data)
        except Exception as e:
            LOGGER.exception("Failed to fetch kline for %s: %s", symbol, e)
            raise e

        if not df.empty:
            self._merge_memory(df)
            self._persist_memory()
            local_frame = self._memory_frame(symbol)
        return self._cache_response(
            cache_key,
            symbol,
            local_frame,
            start_time=start_time,
            end_time=end_time,
            min_bar_time=min_bar_time,
            limit=(max(0, int(limit)) if limit is not None else resolved_limit),
        )

    async def get_kline(self, symbol: str, limit: int | None = None) -> Optional[StockKlineResponse]:
        return await self.get_or_fetch_kline(symbol, limit=limit)

    async def load(self, limit: int | None = None) -> None:
        # resolved_limit = limit if limit is not None else KLINE_MAX_LIMIT
        self.initial_load_in_progress = True
        try:
            # if hasattr(self.gateway, "warm_kline_index"):
            #     await self.gateway.warm_kline_index()
            # index = getattr(self.gateway, "_kline_symbol_index", None)
            # frames = list((index or {}).values())
            # if frames:
            #     self._replace_memory(pd.concat(frames, ignore_index=True))
            # else:
            # result = await self.gateway.stock_all_klines()
            # df = self._to_frame(result.data)
            # if df.empty:
            #     return
            # df["symbol"] = df["symbol"].astype(str).str.strip().str.upper()
            # df = df[df["symbol"] != ""]
            # df = df.sort_values(by=["symbol", "bar_time"]).drop_duplicates(subset=["symbol", "bar_time"], keep="last")

            # if resolved_limit > 0:
            #     df = df.groupby("symbol").tail(resolved_limit).reset_index(drop=True)
            # self._replace_memory(df)
            # self._persist_memory()
            # self._cache.clear()
            # for symbol, frame in self._in_memory_updates.items():
            #     cache_key = f"{symbol}_None_None_None_None_{resolved_limit}"
            #     self._cache_response(
            #         cache_key,
            #         symbol,
            #         frame,
            #         limit=resolved_limit,
            #     )
            self.initial_load_complete = True
        finally:
            self.initial_load_in_progress = False

    async def get_klines(
        self,
        symbols: List[str],
        limit: int | None = None,
    ) -> ConstituentKlineBatchResponse:
        resolved_limit = limit if limit is not None else resolve_kline_limit_for_elapsed_days(DATA_START_DATE)
        items: Dict[str, StockKlineResponse] = {}
        latest: Optional[str] = None

        canonical_symbols = [s.strip().upper() for s in symbols]

        self._load_disk_once()
        missing_cache = [symbol for symbol in canonical_symbols if self._memory_frame(symbol).empty]
        if missing_cache:
            results = await self._gateway_klines(
                missing_cache,
                limit=resolved_limit,
            )
            self._merge_memory(self._to_frame(results.data))
            self._persist_memory()

        async def build_response(s: str) -> None:
            cache_key = f"{s}_None_None_None_None_{resolved_limit}"
            response = self._cache_response(
                cache_key,
                s,
                self._memory_frame(s),
                limit=resolved_limit,
            )
            if response is not None:
                items[s] = response

        await asyncio.gather(*(build_response(s) for s in canonical_symbols))

        for s in items:
            if items[s].as_of and (latest is None or items[s].as_of > latest):
                latest = items[s].as_of

        return ConstituentKlineBatchResponse(as_of=latest, items=items)

    async def prioritize_sector_path(
        self,
        path: ResolvedSectorPath,
        *,
        market: str | None = None,
    ) -> None:
        scopes = collect_sector_scope_tickers(
            self.sector_precomputed_store,
            path,
            market=market,
        )
        already_requested: set[str] = set()
        for level in ("L3", "L2", "L1"):
            symbols = sorted(set(scopes.get(level) or ()) - already_requested)
            if symbols:
                await self.get_klines(symbols)
                already_requested.update(symbols)

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
            tracked_symbols=len(self._in_memory_updates),
            loaded_symbols=sum(1 for frame in self._in_memory_updates.values() if not frame.empty),
            initial_load_in_progress=self.initial_load_in_progress,
            initial_load_complete=self.initial_load_complete,
            last_full_refresh_at=self.last_full_refresh_at,
            last_incremental_refresh_at=self.last_incremental_refresh_at,
        )
