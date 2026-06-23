from __future__ import annotations

import asyncio
from typing import Optional

from dojoagents.dashboard.schemas.stock_income import CoreTickerIncomeResponse
from dojoagents.dashboard.services.dojo_core_income import build_income_distributions
from dojoagents.dashboard.services.dojo_data_gateway import DojoDataGateway


class StockIncomeStore:
    def __init__(self, source):
        self.gateway = source if callable(getattr(source, "stock_income", None)) else DojoDataGateway(source)
        self.cache: dict[str, CoreTickerIncomeResponse] = {}
        self._inflight: dict[str, asyncio.Task[CoreTickerIncomeResponse]] = {}
        self._refresh_keys: set[str] = set()
        self._refresh_lock = asyncio.Lock()

    async def _fetch(
        self,
        symbol: str,
        market_code: str,
        page_size: int,
    ) -> CoreTickerIncomeResponse:
        response = await self.gateway.stock_income(
            market_code,
            symbol,
            page=1,
            page_size=page_size,
        )
        valid_rows = [row for row in response.data if isinstance(row, dict)]
        report_date, distributions = build_income_distributions(valid_rows)
        return CoreTickerIncomeResponse(
            ticker=symbol,
            market=market_code,
            report_date=report_date,
            source=response.source,
            stale=response.stale,
            distributions=distributions,
        )

    async def _schedule_refresh(self, cache_key: str, symbol: str, market_code: str, page_size: int) -> None:
        async with self._refresh_lock:
            if cache_key in self._refresh_keys:
                return
            self._refresh_keys.add(cache_key)
        try:
            self.cache[cache_key] = await self._fetch(symbol, market_code, page_size)
        finally:
            async with self._refresh_lock:
                self._refresh_keys.discard(cache_key)

    async def get_for_ticker(self, ticker: str, market: Optional[str] = None, page_size: int = 100) -> CoreTickerIncomeResponse:
        symbol = ticker.strip().upper()
        market_code = (market or "us").strip().lower()
        cache_key = f"{market_code}:{symbol}:{page_size}"
        cached = self.cache.get(cache_key)
        if cached is not None:
            asyncio.create_task(self._schedule_refresh(cache_key, symbol, market_code, page_size))
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
            raise ValueError(f"Failed to fetch income for {symbol}: {exc}") from exc
        finally:
            self._inflight.pop(cache_key, None)
