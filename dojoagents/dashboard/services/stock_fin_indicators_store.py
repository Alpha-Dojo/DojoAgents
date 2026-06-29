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

    async def get_for_ticker(self, ticker: str, market: Optional[str] = None, limit: int = 20) -> CoreTickerFinIndicatorsResponse:
        symbol = ticker.strip().upper()
        market_code = (market or "us").strip().lower()
        cache_key = f"{market_code}:{symbol}:{limit}"
        cached = self.cache.get(cache_key)
        if cached is not None:
            return cached
        self.cache[cache_key] = await self._fetch(ticker, market or "us", limit)
        return self.cache[cache_key]
