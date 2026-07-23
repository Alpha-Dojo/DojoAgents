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

    async def get_for_ticker(self, ticker: str, market: Optional[str] = None, page_size: int = 100) -> CoreTickerIncomeResponse:
        symbol = ticker.strip().upper()
        market_code = (market or "us").strip().lower()
        cache_key = f"{market_code}:{symbol}:{page_size}"
        cached = self.cache.get(cache_key)
        if cached is not None:
            return cached
        task = self._inflight.get(cache_key)
        if task is None:
            task = asyncio.create_task(self._fetch(symbol, market_code, page_size))
            self._inflight[cache_key] = task
        try:
            result = await task
            self.cache[cache_key] = result
            return result
        finally:
            if self._inflight.get(cache_key) is task:
                self._inflight.pop(cache_key, None)
