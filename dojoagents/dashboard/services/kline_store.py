from __future__ import annotations

import inspect
import logging
import time
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import pandas as pd

from dojo import MaterializationLimitError
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
from dojoagents.dashboard.services.dojo_data_gateway import (
    KLINE_QUERY_FIELDS,
    DojoDataGateway,
)
from dojoagents.dashboard.services.kline_bar_utils import (
    DATA_START_DATE,
    KLINE_LIMIT,
    KLINE_WARM_MAX_SYMBOLS,
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


KLINE_REPO_ID = "AlphaDojo/dojo_stock_kline"
DEFAULT_RESPONSE_CACHE_MAX_ENTRIES = 512
DEFAULT_RESPONSE_CACHE_MAX_BYTES = 64 * 1024 * 1024
DEFAULT_RESPONSE_CACHE_TTL_SECONDS = 5 * 60.0
KLINE_CLOSE_FIELDS = ("symbol", "bar_time", "close")
KLINE_OPEN_FIELDS = ("symbol", "bar_time", "open")
KLINE_OHLC_FIELDS = ("symbol", "bar_time", "open", "high", "low", "close")
KLINE_OHLCV_FIELDS = ("symbol", "bar_time", "open", "high", "low", "close", "vol")
KLINE_ELIGIBILITY_FIELDS = ("symbol", "bar_time", "close", "vol")
KLINE_VOLUME_FIELDS = ("symbol", "bar_time", "vol")


@dataclass(frozen=True)
class KlineResponseCacheKey:
    symbols: tuple[str, ...]
    start_time: str | None
    end_time: str | None
    min_bar_time: str | None
    fields: tuple[str, ...]
    adjust: str
    limit_per_symbol: int
    kline_t: str | None
    market: str | None
    backend: str
    repo_id: str
    resolved_revision: str
    snapshot_token: str


@dataclass(frozen=True)
class _KlineResponseCacheEntry:
    response: StockKlineResponse
    estimated_bytes: int
    expires_at: float
    repo_id: str


class KlineStore:
    def __init__(
        self,
        client: AsyncDojo,
        stock_store: StockStore,
        stock_sector_store: StockSectorStore,
        sector_precomputed_store: Any = None,
        data_root: Path | None = None,
        response_cache_max_entries: int = DEFAULT_RESPONSE_CACHE_MAX_ENTRIES,
        response_cache_max_bytes: int = DEFAULT_RESPONSE_CACHE_MAX_BYTES,
        response_cache_ttl_seconds: float = DEFAULT_RESPONSE_CACHE_TTL_SECONDS,
    ):
        if response_cache_max_entries < 1:
            raise ValueError("response_cache_max_entries must be at least 1")
        if response_cache_max_bytes < 1:
            raise ValueError("response_cache_max_bytes must be at least 1")
        if response_cache_ttl_seconds <= 0:
            raise ValueError("response_cache_ttl_seconds must be greater than 0")
        self.client = client
        gateway_method = getattr(type(client), "stock_klines", None)
        self.gateway = client if callable(gateway_method) else DojoDataGateway(client)
        self.stock_store = stock_store
        self.stock_sector_store = stock_sector_store
        self.sector_precomputed_store = sector_precomputed_store
        # DojoSDK owns K-line snapshots, lazy queries, limits, and adjustment.
        # Keep data_root in the signature for caller compatibility only; this
        # store retains only bounded assembled responses and snapshot metadata.
        del data_root
        self._cache: OrderedDict[KlineResponseCacheKey, _KlineResponseCacheEntry] = OrderedDict()
        self._cache_max_entries = response_cache_max_entries
        self._cache_max_bytes = response_cache_max_bytes
        self._cache_ttl_seconds = response_cache_ttl_seconds
        self._cache_estimated_bytes = 0
        self.snapshot_metadata: dict[str, str] | None = None
        self._active_snapshot_token: str | None = None
        self.initial_load_in_progress = False
        self.initial_load_complete = False
        self.last_full_refresh_at: Optional[str] = None
        self.last_incremental_refresh_at: Optional[str] = None
        self.member_symbols = 0

    def _observe_snapshot(self, snapshot: dict[str, str] | None) -> None:
        if not snapshot:
            return
        token = snapshot.get("snapshot_token")
        if token and self._active_snapshot_token and token != self._active_snapshot_token:
            previous_repo = (self.snapshot_metadata or {}).get("repo_id")
            self.invalidate_repos([previous_repo or KLINE_REPO_ID])
        if token:
            self._active_snapshot_token = token
        self.snapshot_metadata = dict(snapshot)

    @staticmethod
    def _estimate_response_bytes(response: StockKlineResponse) -> int:
        try:
            return len(response.model_dump_json().encode("utf-8"))
        except AttributeError:
            return len(repr(response).encode("utf-8"))

    def _snapshot_identity(self) -> tuple[str, str, str, str]:
        snapshot = self.snapshot_metadata or {}
        return (
            snapshot.get("backend") or "online",
            snapshot.get("repo_id") or KLINE_REPO_ID,
            snapshot.get("resolved_revision") or "online",
            snapshot.get("snapshot_token") or "online",
        )

    def _response_cache_key(
        self,
        symbol: str,
        *,
        market: str | None,
        kline_t: str | None,
        start_time: str | None,
        end_time: str | None,
        min_bar_time: str | None,
        price_adj_type: str | None,
        limit: int,
        fields: Iterable[str] | None = None,
    ) -> KlineResponseCacheKey:
        backend, repo_id, revision, token = self._snapshot_identity()
        return KlineResponseCacheKey(
            symbols=(symbol,),
            start_time=start_time,
            end_time=end_time,
            min_bar_time=min_bar_time,
            fields=tuple(fields or KLINE_QUERY_FIELDS),
            adjust=price_adj_type or "pre",
            limit_per_symbol=limit,
            kline_t=kline_t,
            market=market,
            backend=backend,
            repo_id=repo_id,
            resolved_revision=revision,
            snapshot_token=token,
        )

    def _purge_expired_cache_entries(self, *, now: float | None = None) -> None:
        current = time.monotonic() if now is None else now
        expired = [key for key, entry in self._cache.items() if entry.expires_at <= current]
        for key in expired:
            entry = self._cache.pop(key)
            self._cache_estimated_bytes -= entry.estimated_bytes

    def _cache_get(self, key: KlineResponseCacheKey) -> StockKlineResponse | None:
        now = time.monotonic()
        self._purge_expired_cache_entries(now=now)
        entry = self._cache.get(key)
        if entry is None:
            return None
        self._cache.move_to_end(key)
        return entry.response

    def _cache_put(self, key: KlineResponseCacheKey, response: StockKlineResponse) -> None:
        estimated_bytes = self._estimate_response_bytes(response)
        if estimated_bytes > self._cache_max_bytes:
            return
        self._purge_expired_cache_entries()
        previous = self._cache.pop(key, None)
        if previous is not None:
            self._cache_estimated_bytes -= previous.estimated_bytes
        self._cache[key] = _KlineResponseCacheEntry(
            response=response,
            estimated_bytes=estimated_bytes,
            expires_at=time.monotonic() + self._cache_ttl_seconds,
            repo_id=key.repo_id,
        )
        self._cache_estimated_bytes += estimated_bytes
        while len(self._cache) > self._cache_max_entries or self._cache_estimated_bytes > self._cache_max_bytes:
            _, evicted = self._cache.popitem(last=False)
            self._cache_estimated_bytes -= evicted.estimated_bytes

    def clear_response_cache(self) -> None:
        self._cache.clear()
        self._cache_estimated_bytes = 0

    def invalidate_repos(self, repo_ids: Iterable[str]) -> int:
        targets = {str(repo_id) for repo_id in repo_ids if repo_id}
        if not targets:
            return 0
        target_slugs = {repo_id.rsplit("/", 1)[-1].lower() for repo_id in targets}
        keys = [key for key, entry in self._cache.items() if entry.repo_id in targets or entry.repo_id.rsplit("/", 1)[-1].lower() in target_slugs]
        for key in keys:
            entry = self._cache.pop(key)
            self._cache_estimated_bytes -= entry.estimated_bytes
        active_repo = (self.snapshot_metadata or {}).get("repo_id")
        if active_repo and (active_repo in targets or active_repo.rsplit("/", 1)[-1].lower() in target_slugs):
            self.snapshot_metadata = None
            self._active_snapshot_token = None
        return len(keys)

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
        if market is not None:
            window["market"] = market
        return await method(symbols, **window)

    def _cache_response(
        self,
        cache_key: KlineResponseCacheKey,
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
        self._cache_put(cache_key, response)
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
        fields: Iterable[str] | None = None,
    ) -> Optional[StockKlineResponse]:
        symbol = symbol.strip().upper()
        resolved_limit = resolve_tail_limit(
            start_time=start_time,
            end_time=end_time,
            limit=limit,
        )
        if min_bar_time and not start_time:
            resolved_limit = 0
        query_fields = tuple(dict.fromkeys(str(field).strip() for field in (fields or KLINE_QUERY_FIELDS) if str(field).strip()))
        cache_key = self._response_cache_key(
            symbol,
            market=market,
            kline_t=kline_t,
            start_time=start_time,
            end_time=end_time,
            min_bar_time=min_bar_time,
            price_adj_type=price_adj_type,
            limit=resolved_limit,
            fields=query_fields,
        )

        if not refresh:
            cached = self._cache_get(cache_key)
            if cached is not None:
                return cached

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
            if fields is not None:
                kwargs["fields"] = query_fields

            result = await self._gateway_klines(
                [symbol],
                market=market,
                **kwargs,
            )
            self._observe_snapshot(getattr(result, "snapshot", None))
            cache_key = self._response_cache_key(
                symbol,
                market=market,
                kline_t=kline_t,
                start_time=start_time,
                end_time=end_time,
                min_bar_time=min_bar_time,
                price_adj_type=price_adj_type,
                limit=resolved_limit,
                fields=query_fields,
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
        return await self.get_or_fetch_kline(symbol, limit=limit, fields=KLINE_OHLCV_FIELDS)

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
        fields: Iterable[str] | None = None,
    ) -> ConstituentKlineBatchResponse:
        resolved_limit = limit if limit is not None else resolve_kline_limit_for_elapsed_days(DATA_START_DATE)
        query_fields = tuple(dict.fromkeys(str(field).strip() for field in (fields or KLINE_QUERY_FIELDS) if str(field).strip()))
        items: Dict[str, StockKlineResponse] = {}
        latest: Optional[str] = None

        canonical_symbols = list(dict.fromkeys(s.strip().upper() for s in symbols if s.strip()))
        if not canonical_symbols:
            return ConstituentKlineBatchResponse(as_of=None, items={})

        if not refresh:
            cached_items: dict[str, StockKlineResponse] = {}
            for symbol in canonical_symbols:
                cache_key = self._response_cache_key(
                    symbol,
                    market=market,
                    kline_t=None,
                    start_time=start_time,
                    end_time=end_time,
                    min_bar_time=None,
                    price_adj_type=price_adj_type,
                    limit=resolved_limit,
                    fields=query_fields,
                )
                cached = self._cache_get(cache_key)
                if cached is None:
                    cached_items = {}
                    break
                cached_items[symbol] = cached
            if cached_items:
                latest = max(
                    (response.as_of for response in cached_items.values() if response.as_of),
                    default=None,
                )
                return ConstituentKlineBatchResponse(as_of=latest, items=cached_items)

        window = {
            key: value
            for key, value in {
                "limit": resolved_limit,
                "start_time": start_time,
                "end_time": end_time,
                "price_adj_type": price_adj_type,
                "fields": query_fields if fields is not None else None,
            }.items()
            if value is not None
        }
        results = await self._gateway_klines(canonical_symbols, market=market, **window)
        self._observe_snapshot(getattr(results, "snapshot", None))
        # Prepare the batch frame once, then slice by symbol. Re-running
        # _prepare_kline_df on the full multi-symbol frame per ticker was O(N^2)
        # and blocked the agent event loop (dojo-agent-runs) under GIL.
        prepared = _prepare_kline_df(self._to_frame(results.data), symbol="")
        if LOGGER.isEnabledFor(logging.DEBUG):
            dates = prepared.get("bar_time", pd.Series(dtype=str))
            LOGGER.debug(
                "dojo_kline_normalized market=%s rows=%d symbols=%d min_date=%s max_date=%s refresh=%s",
                market,
                len(prepared),
                prepared["symbol"].nunique() if "symbol" in prepared else 0,
                dates.min() if len(dates) else None,
                dates.max() if len(dates) else None,
                refresh,
            )
        if prepared.empty or "symbol" not in prepared.columns:
            return ConstituentKlineBatchResponse(as_of=None, items={})

        grouped = {symbol: rows for symbol, rows in prepared.groupby("symbol", sort=False)}
        for symbol in canonical_symbols:
            subset = grouped.get(symbol)
            if subset is None or subset.empty:
                continue
            cache_key = self._response_cache_key(
                symbol,
                market=market,
                kline_t=None,
                start_time=start_time,
                end_time=end_time,
                min_bar_time=None,
                price_adj_type=price_adj_type,
                limit=resolved_limit,
                fields=query_fields,
            )
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
            if not symbols:
                continue
            already_requested.update(symbols)
            if len(symbols) > KLINE_WARM_MAX_SYMBOLS:
                LOGGER.info(
                    "Skipped kline cache warm before query: sector=%s level=%s symbols=%d max=%d",
                    path.level3_id,
                    level,
                    len(symbols),
                    KLINE_WARM_MAX_SYMBOLS,
                )
                continue
            try:
                await self.get_klines(symbols, fields=KLINE_OHLCV_FIELDS)
            except MaterializationLimitError as exc:
                LOGGER.warning(
                    "Kline cache warm exceeded materialization limit: sector=%s level=%s symbols=%d: %s",
                    path.level3_id,
                    level,
                    len(symbols),
                    exc,
                )
            except Exception:
                LOGGER.exception(
                    "Kline cache warm failed: sector=%s level=%s symbols=%d",
                    path.level3_id,
                    level,
                    len(symbols),
                )

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
                batch_resp = await self.get_klines(symbols, fields=KLINE_OHLCV_FIELDS)
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
        self._purge_expired_cache_entries()
        cached_symbols = {symbol for key in self._cache for symbol in key.symbols}
        return ConstituentKlineStatsResponse(
            member_symbols=self.member_symbols,
            tracked_symbols=len(cached_symbols),
            loaded_symbols=len(cached_symbols),
            initial_load_in_progress=self.initial_load_in_progress,
            initial_load_complete=self.initial_load_complete,
            last_full_refresh_at=self.last_full_refresh_at,
            last_incremental_refresh_at=self.last_incremental_refresh_at,
        )
