from __future__ import annotations
from typing import Dict, Optional

from dojoagents.dashboard.schemas.stock_news import CoreTickerNewsResponse
from dojoagents.dashboard.services.dojo_data_gateway import DojoDataGateway
from dojoagents.dashboard.services.stock_news_utils import (
    latest_news_publish_date,
    prepare_news_rows,
)


class StockNewsStore:
    def __init__(self, source):
        self.gateway = source if callable(getattr(source, "stock_news", None)) else DojoDataGateway(source)
        self.cache: Dict[str, CoreTickerNewsResponse] = {}

    async def _fetch(self, symbol: str, market_code: str, page_size: int) -> CoreTickerNewsResponse:
        response = await self.gateway.stock_news(market_code, symbol, page=1, page_size=page_size)
        valid_rows = [row for row in response.data if isinstance(row, dict)]
        rows = prepare_news_rows(valid_rows, page_size)
        return CoreTickerNewsResponse(
            ticker=symbol,
            market=market_code,
            as_of=latest_news_publish_date(rows),
            source=response.source,
            stale=response.stale,
            items=rows,
        )

    async def get_for_ticker(self, ticker: str, market: Optional[str] = None, page_size: int = 20) -> CoreTickerNewsResponse:
        symbol = ticker.strip().upper()
        market_code = (market or "us").strip().lower()
        cache_key = f"{market_code}:{symbol}:{page_size}"

        cached = self.cache.get(cache_key)
        if cached is not None:
            return cached
        inflight = self._inflight.get(cache_key)
        if inflight is not None:
            return await inflight

        self.cache[cache_key] = await self._fetch(ticker, market or "us", page_size)
        return self.cache[cache_key]
