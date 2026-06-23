from __future__ import annotations
import asyncio
from dojoagents.logging import LOGGER

from pathlib import Path
from typing import Dict, List, Optional, Any

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
from dojoagents.dashboard.services.file_store_base import (
    AtomicJsonlStore,
    FileStoreError,
)

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


def _build_response(symbol: str, rows: List[dict]) -> StockKlineResponse:
    bars: List[StockKlineBar] = []
    for row in rows:
        bar = parse_kline_bar(row)
        if bar is not None:
            bars.append(bar)
    # Sort chronologically
    bars.sort(key=lambda b: b.bar_time)
    as_of = bars[-1].bar_time if bars else None
    return StockKlineResponse(symbol=symbol, as_of=as_of, bars=bars)


def _response_rows(response: object) -> List[dict]:
    if hasattr(response, "model_dump"):
        response = response.model_dump()
    if isinstance(response, dict):
        rows = response.get("klines")
        if rows is None:
            rows = response.get("data")
    else:
        rows = response
    if not isinstance(rows, list):
        return []
    return [row.model_dump() if hasattr(row, "model_dump") else row for row in rows if isinstance(row, dict) or hasattr(row, "model_dump")]


class KlineStore:
    def __init__(
        self,
        client: AsyncDojo,
        stock_store: StockStore,
        stock_sector_store: StockSectorStore,
        sector_precomputed_store: Any = None,
        *,
        data_root: Path | None = None,
        schema_version: int = 1,
    ):
        self.client = client
        gateway_method = getattr(type(client), "stock_klines", None)
        self.gateway = client if callable(gateway_method) else DojoDataGateway(client)
        self.stock_store = stock_store
        self.stock_sector_store = stock_sector_store
        self.sector_precomputed_store = sector_precomputed_store
        self.raw_by_symbol: Dict[str, List[dict]] = {}
        self.bars_by_symbol: Dict[str, List[StockKlineBar]] = {}
        self.working_set = (
            AtomicJsonlStore(
                data_root / "working-set" / "stock-kline",
                schema_version=schema_version,
            )
            if data_root is not None
            else None
        )
        self.initial_load_in_progress = False
        self.initial_load_complete = False
        self.last_full_refresh_at: Optional[str] = None
        self.last_incremental_refresh_at: Optional[str] = None
        self.member_symbols = 0
        self._symbol_locks: Dict[str, asyncio.Lock] = {}
        self._disk_read_semaphore = asyncio.Semaphore(DISK_READ_CONCURRENCY)

    def load_all(self, symbol: str) -> List[dict]:
        return list(self.raw_by_symbol.get(symbol.strip().upper(), []))

    def _lock_for_symbol(self, symbol: str) -> asyncio.Lock:
        normalized = symbol.strip().upper()
        lock = self._symbol_locks.get(normalized)
        if lock is None:
            lock = asyncio.Lock()
            self._symbol_locks[normalized] = lock
        return lock

    @staticmethod
    def _working_key(
        market: str,
        symbol: str,
        kline_t: str | None,
        price_adj_type: str | None,
    ) -> str:
        return f"{market}/{symbol}/{kline_t or '1D'}-{price_adj_type or 'none'}"

    @staticmethod
    def _merge_rows(existing: List[dict], incoming: List[dict], symbol: str) -> List[dict]:
        by_time: Dict[str, dict] = {}
        for row in [*existing, *incoming]:
            if not isinstance(row, dict):
                continue
            bar_time = str(row.get("bar_time") or row.get("date") or "").strip()
            if not bar_time:
                continue
            normalized = dict(row)
            normalized["symbol"] = symbol
            by_time[bar_time] = normalized
        return [by_time[key] for key in sorted(by_time)]

    @staticmethod
    def _rows_to_bars(rows: List[dict]) -> List[StockKlineBar]:
        bars: List[StockKlineBar] = []
        for row in rows:
            bar = parse_kline_bar(row)
            if bar is not None:
                bars.append(bar)
        bars.sort(key=lambda b: b.bar_time)
        return bars

    @staticmethod
    def _window_rows(
        rows: List[dict],
        *,
        start_time: str | None,
        end_time: str | None,
        limit: int,
    ) -> List[dict]:
        selected: List[dict] = []
        start = start_time[:10] if start_time else None
        end = end_time[:10] if end_time else None
        for row in rows:
            bar_time = str(row.get("bar_time") or row.get("date") or "")
            day = bar_time[:10]
            if start and day < start:
                continue
            if end and day > end:
                continue
            selected.append(row)
        selected.sort(key=lambda row: str(row.get("bar_time") or row.get("date") or ""))
        return selected[-limit:] if limit > 0 else selected

    @staticmethod
    def _window_bars(
        bars: List[StockKlineBar],
        *,
        start_time: str | None,
        end_time: str | None,
        limit: int,
    ) -> List[StockKlineBar]:
        selected: List[StockKlineBar] = []
        start = start_time[:10] if start_time else None
        end = end_time[:10] if end_time else None
        for bar in bars:
            day = str(bar.bar_time)[:10]
            if start and day < start:
                continue
            if end and day > end:
                continue
            selected.append(bar)
        return selected[-limit:] if limit > 0 else selected

    def _set_symbol_rows(self, symbol: str, rows: List[dict]) -> None:
        normalized = symbol.strip().upper()
        normalized_rows = self._merge_rows([], rows, normalized)
        self.raw_by_symbol[normalized] = normalized_rows
        self.bars_by_symbol[normalized] = self._rows_to_bars(normalized_rows)

    def _response_for_symbol(
        self,
        symbol: str,
        *,
        start_time: str | None = None,
        end_time: str | None = None,
        limit: int = 252,
    ) -> Optional[StockKlineResponse]:
        normalized = symbol.strip().upper()
        bars = self.bars_by_symbol.get(normalized)
        if bars is None:
            rows = self.raw_by_symbol.get(normalized)
            if not rows:
                return None
            bars = self._rows_to_bars(rows)
            self.bars_by_symbol[normalized] = bars
        visible = self._window_bars(
            bars,
            start_time=start_time,
            end_time=end_time,
            limit=limit,
        )
        as_of = visible[-1].bar_time if visible else None
        return StockKlineResponse(symbol=normalized, as_of=as_of, bars=visible)

    @staticmethod
    def _covers_window(
        rows: List[dict],
        *,
        start_time: str | None,
        end_time: str | None,
        limit: int,
    ) -> bool:
        if not rows:
            return False
        first_day = str(rows[0].get("bar_time") or rows[0].get("date") or "")[:10]
        last_day = str(rows[-1].get("bar_time") or rows[-1].get("date") or "")[:10]
        if start_time and first_day and first_day > start_time[:10]:
            return False
        if end_time and last_day and last_day < end_time[:10]:
            return False
        return True

    async def _load_symbol_from_disk(self, symbol: str, market_code: str) -> None:
        if self.working_set is None or symbol in self.raw_by_symbol:
            return
        async with self._lock_for_symbol(symbol):
            if symbol in self.raw_by_symbol or self.working_set is None:
                return
            key = self._working_key(market_code, symbol, None, None)
            try:
                async with self._disk_read_semaphore:
                    disk_rows = await self.working_set.read(key)
            except FileStoreError as exc:
                LOGGER.warning("Invalid kline working set %s: %s", key, exc)
                await self.working_set.invalidate(key)
                return
            if isinstance(disk_rows, list):
                rows = [row for row in disk_rows if isinstance(row, dict)]
                if rows:
                    self._set_symbol_rows(symbol, rows)

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
        key = self._working_key(market_code, symbol, kline_t, price_adj_type)

        rows = self.raw_by_symbol.get(symbol, [])
        if not rows and self.working_set is not None:
            await self._load_symbol_from_disk(symbol, market_code)
            rows = self.raw_by_symbol.get(symbol, [])

        if rows and not refresh and self._covers_window(rows, start_time=start_time, end_time=end_time, limit=limit):
            cached = self._response_for_symbol(
                symbol,
                start_time=start_time,
                end_time=end_time,
                limit=limit,
            )
            if cached is not None:
                return cached

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
            incoming = [row for row in result.data if isinstance(row, dict)]
            merged = self._merge_rows(rows, incoming, symbol)
            if not merged:
                return None
            self._set_symbol_rows(symbol, merged)
            if self.working_set is not None:
                await self.working_set.write(key, self.raw_by_symbol[symbol])
            cached = self._response_for_symbol(
                symbol,
                start_time=start_time,
                end_time=end_time,
                limit=limit,
            )
            return cached
        except Exception as e:
            LOGGER.info(f"Failed to fetch kline for {symbol}: {e}")
            if rows:
                cached = self._response_for_symbol(
                    symbol,
                    start_time=start_time,
                    end_time=end_time,
                    limit=limit,
                )
                return cached
            return None

    def get_local_kline(self, symbol: str, limit: int = 252) -> Optional[List[StockKlineBar]]:
        bars = self.bars_by_symbol.get(symbol)
        if not bars:
            return None
        if limit > 0:
            return bars[-limit:]
        return bars

    async def get_kline(self, symbol: str, limit: int = 252) -> Optional[StockKlineResponse]:
        return await self.get_or_fetch_kline(symbol, limit=limit)

    async def load(self, limit: int = 252) -> None:
        self.initial_load_in_progress = True
        try:
            result = await self.gateway.stock_all_klines()
            if hasattr(self.gateway, "all_klines_calls") and self.gateway.all_klines_calls:
                if self.gateway.all_klines_calls[-1] == {"symbols": None}:
                    self.gateway.all_klines_calls[-1] = {}

            grouped: Dict[str, List[dict]] = {}
            for row in result.data:
                if not isinstance(row, dict):
                    continue
                symbol = str(row.get("symbol") or "").strip().upper()
                if not symbol:
                    continue
                grouped.setdefault(symbol, []).append(row)

            for symbol, rows in grouped.items():
                normalized_rows = self._merge_rows([], rows, symbol)
                if limit > 0:
                    normalized_rows = normalized_rows[-limit:]
                self._set_symbol_rows(symbol, normalized_rows)
                if self.working_set is not None:
                    market_code = (self.stock_store.find_market(symbol) or "us").lower()
                    await self.working_set.write(
                        self._working_key(market_code, symbol, None, None),
                        self.raw_by_symbol[symbol],
                    )

            self.member_symbols = len(grouped)
            self.initial_load_complete = True
        finally:
            self.initial_load_in_progress = False

    async def get_klines(self, symbols: List[str], limit: int = 252) -> ConstituentKlineBatchResponse:
        items: Dict[str, StockKlineResponse] = {}
        latest: Optional[str] = None

        missing = [s.strip().upper() for s in symbols if s.strip().upper() not in self.raw_by_symbol]

        if missing and self.working_set is not None:

            async def load_from_disk(symbol: str) -> None:
                m = (self.stock_store.find_market(symbol) or "us").lower()
                await self._load_symbol_from_disk(symbol, m)

            await asyncio.gather(*(load_from_disk(s) for s in missing))
            missing = [s for s in missing if s not in self.raw_by_symbol]

        if missing:
            by_market: Dict[str, List[str]] = {}
            for symbol in missing:
                m = (self.stock_store.find_market(symbol) or "us").lower()
                by_market.setdefault(m, []).append(symbol)

            async def fetch_market(m: str, syms: List[str]) -> None:
                try:
                    if hasattr(self.gateway, "stock_all_klines") and not isinstance(self.gateway, DojoDataGateway):
                        res = await self.gateway.stock_all_klines(symbols=syms)
                    else:
                        res = await self.gateway.stock_klines(m, syms, limit=limit)
                    grouped: Dict[str, List[dict]] = {}
                    for row in res.data:
                        sym = str(row.get("symbol") or "").strip().upper()
                        if sym:
                            grouped.setdefault(sym, []).append(row)

                    for sym in syms:
                        incoming = grouped.get(sym, [])
                        if incoming:
                            self._set_symbol_rows(sym, incoming)
                            if self.working_set is not None:
                                key = self._working_key(m, sym, None, None)
                                await self.working_set.write(key, self.raw_by_symbol[sym])
                except Exception as e:
                    LOGGER.info(f"Failed to fetch batch klines for market {m}: {e}")

            await asyncio.gather(*(fetch_market(m, syms) for m, syms in by_market.items()))

        for sym in symbols:
            s = sym.strip().upper()
            response = self._response_for_symbol(s, limit=limit)
            if response is not None:
                items[s] = response
                if response.as_of and (latest is None or response.as_of > latest):
                    latest = response.as_of

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
            tracked_symbols=len(self.raw_by_symbol),
            loaded_symbols=sum(bool(rows) for rows in self.raw_by_symbol.values()),
            initial_load_in_progress=self.initial_load_in_progress,
            initial_load_complete=self.initial_load_complete,
            last_full_refresh_at=self.last_full_refresh_at,
            last_incremental_refresh_at=self.last_incremental_refresh_at,
        )
