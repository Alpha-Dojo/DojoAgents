from __future__ import annotations

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
        # K-line persistence and the indexed DataFrame are owned by DojoSDK.
        # Keep data_root in the signature for caller compatibility only.
        del data_root
        self._cache: Dict[str, StockKlineResponse] = {}
        self._cache_limit = 2000
        self._in_memory_updates: dict[str, pd.DataFrame] = {}
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
        prepared: bool = False,
    ) -> Optional[StockKlineResponse]:
        if frame.empty:
            return None
        working = frame if prepared else _prepare_kline_df(frame, symbol=symbol)
        if working.empty:
            return None
        if "symbol" in working.columns:
            working = working[working["symbol"].astype(str).str.upper() == symbol]
        if working.empty:
            return None
        filter_start = (start_time or min_bar_time or "")[:10]
        filter_end = (end_time or "")[:10]
        if filter_start:
            working = working[working["bar_time"] >= filter_start]
        if filter_end:
            working = working[working["bar_time"] <= filter_end]
        # Enforce oldest-first before tail(): unsorted upstream rows would otherwise
        # truncate/display the wrong bars (e.g. Jul 28 left of Jul 27 on the chart).
        working = working.sort_values("bar_time").drop_duplicates(
            subset=["bar_time"],
            keep="last",
        )
        if limit > 0:
            working = working.tail(limit)
        bars = [bar for row in working.to_dict(orient="records") if (bar := parse_kline_bar(row, default_symbol=symbol)) is not None]
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

        return self._cache_response(
            cache_key,
            symbol,
            df,
            start_time=start_time,
            end_time=end_time,
            min_bar_time=min_bar_time,
            limit=(max(0, int(limit)) if limit is not None else resolved_limit),
        )

    async def get_kline(self, symbol: str, limit: int | None = None) -> Optional[StockKlineResponse]:
        return await self.get_or_fetch_kline(symbol, limit=limit)

    async def load(self, limit: int | None = None) -> None:
        del limit
        self.initial_load_in_progress = True
        try:
            self.initial_load_complete = True
        finally:
            self.initial_load_in_progress = False

    async def get_klines(
        self,
        symbols: List[str],
        limit: int | None = None,
        *,
        market: str | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
        price_adj_type: str | None = None,
        refresh: bool = False,
    ) -> ConstituentKlineBatchResponse:
        del refresh  # DojoSDK owns the source DataFrame and refresh lifecycle.
        resolved_limit = limit if limit is not None else resolve_kline_limit_for_elapsed_days(DATA_START_DATE)
        items: Dict[str, StockKlineResponse] = {}
        latest: Optional[str] = None

        canonical_symbols = [s.strip().upper() for s in symbols]
        if not canonical_symbols:
            return ConstituentKlineBatchResponse(as_of=None, items={})

        window = {
            key: value
            for key, value in {
                "limit": resolved_limit,
                "start_time": start_time,
                "end_time": end_time,
                "price_adj_type": price_adj_type,
            }.items()
            if value is not None
        }
        results = await self._gateway_klines(canonical_symbols, market=market, **window)
        # Prepare the batch frame once, then slice by symbol. Re-running
        # _prepare_kline_df on the full multi-symbol frame per ticker was O(N^2)
        # and blocked the agent event loop (dojo-agent-runs) under GIL.
        prepared = _prepare_kline_df(self._to_frame(results.data), symbol="")
        if prepared.empty or "symbol" not in prepared.columns:
            return ConstituentKlineBatchResponse(as_of=None, items={})

        grouped = {symbol: rows for symbol, rows in prepared.groupby("symbol", sort=False)}
        for symbol in canonical_symbols:
            subset = grouped.get(symbol)
            if subset is None or subset.empty:
                continue
            cache_key = f"{symbol}_None_{start_time}_{end_time}_None_{price_adj_type}_{resolved_limit}"
            response = self._cache_response(
                cache_key,
                symbol,
                subset,
                start_time=start_time,
                end_time=end_time,
                limit=resolved_limit,
                prepared=True,
            )
            if response is not None:
                items[symbol] = response
                if response.as_of and (latest is None or response.as_of > latest):
                    latest = response.as_of

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
