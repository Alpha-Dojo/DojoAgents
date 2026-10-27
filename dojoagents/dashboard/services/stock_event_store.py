from __future__ import annotations
import anyio
import time
from typing import Dict, Optional
from weakref import WeakValueDictionary

from dojoagents.dashboard.schemas.stock_event import CoreTickerEventsResponse
from dojoagents.dashboard.services.dojo_data_gateway import DojoDataGateway
from dojoagents.dashboard.services.stock_event_utils import (
    latest_event_date,
    sort_event_rows,
    trim_event_rows,
)


class StockEventStore:
    def __init__(self, source):
        self.gateway = source if callable(getattr(source, "stock_events", None)) else DojoDataGateway(source)
        self.cache: Dict[str, CoreTickerEventsResponse] = {}
        self._cache_expires_at: Dict[str, float] = {}
        self._fetch_locks: WeakValueDictionary[str, anyio.Lock] = WeakValueDictionary()
        self._refresh_keys = set()

    async def _fetch(self, symbol: str, market_code: str, page_size: int) -> CoreTickerEventsResponse:
        response = await self.gateway.stock_events(market_code, symbol, page=1, page_size=page_size)
        valid_rows = [row for row in response.data if isinstance(row, dict)]
        rows = trim_event_rows(sort_event_rows(valid_rows), page_size)
        return CoreTickerEventsResponse(
            ticker=symbol,
            market=market_code,
            as_of=latest_event_date(rows),
            source=response.source,
            stale=response.stale,
            items=rows,
        )

    async def get_for_ticker(self, ticker: str, market: Optional[str] = None, page_size: int = 20) -> CoreTickerEventsResponse:
        symbol = ticker.strip().upper()
        market_code = (market or "us").strip().lower()
        cache_key = f"{market_code}:{symbol}:{page_size}"

        cached = self.cache.get(cache_key)
        if cached is not None and time.monotonic() < self._cache_expires_at.get(cache_key, 0.0):
            return cached
        self.cache.pop(cache_key, None)
        self._cache_expires_at.pop(cache_key, None)
        lock = self._fetch_locks.setdefault(cache_key, anyio.Lock())
        async with lock:
            cached = self.cache.get(cache_key)
            if cached is not None and time.monotonic() < self._cache_expires_at.get(cache_key, 0.0):
                return cached
            result = await self._fetch(symbol, market_code, page_size)
            self.cache[cache_key] = result
            self._cache_expires_at[cache_key] = time.monotonic() + 120.0
            return result
