from __future__ import annotations
from dojoagents.logging import LOGGER

import asyncio
from typing import Dict, Optional

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
        self._inflight: Dict[str, asyncio.Task[CoreTickerEventsResponse]] = {}
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
        if cached is not None:
            asyncio.create_task(self._schedule_refresh(symbol, market_code, page_size, cache_key))
            return cached
        inflight = self._inflight.get(cache_key)
        if inflight is not None:
            return await inflight

        task = asyncio.create_task(self._fetch(symbol, market_code, page_size))
        self._inflight[cache_key] = task
        try:
            result = await task
            self.cache[cache_key] = result
            return result
        except Exception as exc:
            raise ValueError(f"Failed to fetch events for {symbol}: {exc}") from exc
        finally:
            self._inflight.pop(cache_key, None)

    async def _schedule_refresh(self, ticker: str, market: Optional[str], page_size: int, cache_key: str):
        if cache_key in self._refresh_keys:
            return
        self._refresh_keys.add(cache_key)
        try:
            self.cache[cache_key] = await self._fetch(ticker, market or "us", page_size)
        except Exception as exc:
            LOGGER.info(f"[StockEventStore] Background refresh failed for {ticker}: {exc}")
        finally:
            self._refresh_keys.discard(cache_key)
