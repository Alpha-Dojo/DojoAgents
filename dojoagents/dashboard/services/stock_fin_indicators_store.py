from __future__ import annotations

import asyncio
from typing import Optional

from dojoagents.dashboard.schemas.stock_fin_indicators import CoreTickerFinIndicatorsResponse
from dojoagents.dashboard.services.dojo_data_gateway import DojoDataGateway
from dojoagents.dashboard.services.fin_indicators_utils import (
    latest_report_date,
    report_type_for_market,
    trim_fin_rows,
)


class StockFinIndicatorsStore:
    def __init__(self, source):
        self.gateway = source if callable(getattr(source, "stock_financial_indicators", None)) else DojoDataGateway(source)
        self.cache: dict[str, CoreTickerFinIndicatorsResponse] = {}
        self._inflight: dict[str, asyncio.Task[CoreTickerFinIndicatorsResponse]] = {}
        self._refresh_keys: set[str] = set()
        self._refresh_lock = asyncio.Lock()

    async def _fetch(
        self,
        symbol: str,
        market_code: str,
        limit: int,
    ) -> CoreTickerFinIndicatorsResponse:
        report_type = report_type_for_market(market_code)
        response = await self.gateway.stock_financial_indicators(
            market_code,
            symbol,
            report_type=report_type,
            limit=limit,
        )
        valid_rows = [row for row in response.data if isinstance(row, dict)]
        rows = trim_fin_rows(valid_rows, limit)
        return CoreTickerFinIndicatorsResponse(
            ticker=symbol,
            market=market_code,
            report_type=report_type,
            as_of=latest_report_date(rows),
            source=response.source,
            stale=response.stale,
            items=rows,
        )

    async def _schedule_refresh(self, cache_key: str, symbol: str, market_code: str, limit: int) -> None:
        async with self._refresh_lock:
            if cache_key in self._refresh_keys:
                return
            self._refresh_keys.add(cache_key)
        try:
            self.cache[cache_key] = await self._fetch(symbol, market_code, limit)
        finally:
            async with self._refresh_lock:
                self._refresh_keys.discard(cache_key)

    async def get_for_ticker(self, ticker: str, market: Optional[str] = None, limit: int = 20) -> CoreTickerFinIndicatorsResponse:
        symbol = ticker.strip().upper()
        market_code = (market or "us").strip().lower()
        cache_key = f"{market_code}:{symbol}:{limit}"
        cached = self.cache.get(cache_key)
        if cached is not None:
            asyncio.create_task(self._schedule_refresh(cache_key, symbol, market_code, limit))
            return cached
        inflight = self._inflight.get(cache_key)
        if inflight is not None:
            return await inflight

        task = asyncio.create_task(self._fetch(symbol, market_code, limit))
        self._inflight[cache_key] = task
        try:
            result = await task
            self.cache[cache_key] = result
            return result
        except Exception as exc:
            raise ValueError(f"Failed to fetch fin indicators for {symbol}: {exc}") from exc
        finally:
            self._inflight.pop(cache_key, None)
