from __future__ import annotations
from dojoagents.logging import LOGGER

import asyncio
from typing import Dict, Optional

from dojo.client.async_client import AsyncDojo

from dojoagents.dashboard.schemas.stock_kline import StockKlineResponse, StockKlineBar
from dojoagents.dashboard.schemas.benchmark import DojoMeshBenchmarksResponse, MarketBenchmarks, BenchmarkCard, BilingualText, BenchmarkKline
from dojoagents.dashboard.services.dojo_data_gateway import DojoDataGateway


def parse_benchmark_bar(row: object, symbol: str) -> Optional[StockKlineBar]:
    if isinstance(row, (list, tuple)):
        if len(row) < 5:
            return None
        row = {
            "bar_time": row[0],
            "open": row[1],
            "high": row[2],
            "low": row[3],
            "close": row[4],
            "vol": row[5] if len(row) > 5 else 0.0,
            "amount": row[6] if len(row) > 6 else 0.0,
        }
    if not isinstance(row, dict):
        return None
    bar_time = str(row.get("date") or row.get("bar_time") or "").strip()
    if not bar_time:
        return None

    return StockKlineBar(
        symbol=symbol,
        kline_t=str(row.get("kline_t") or "1D"),
        bar_time=bar_time,
        open=float(row.get("open") or 0.0),
        high=float(row.get("high") or 0.0),
        low=float(row.get("low") or 0.0),
        close=float(row.get("close") or 0.0),
        vol=float(row.get("vol") or row.get("volume") or 0.0),
        amount=float(row.get("amount") or 0.0),
        change_p=float(row.get("change_p") or row.get("change_percent") or 0.0),
        tr=0.0,
        adj_factor_cum=1.0,
        dividends=0.0,
        splits=0.0,
    )


class BenchmarkStore:
    def __init__(self, client: AsyncDojo):
        self.client = client
        gateway_method = getattr(type(client), "benchmark_klines", None)
        self.gateway = client if callable(gateway_method) else DojoDataGateway(client)
        self.cached: Optional[DojoMeshBenchmarksResponse] = None
        self._kline_cache: Dict[str, StockKlineResponse] = {}
        self._inflight: Dict[str, asyncio.Task[Optional[StockKlineResponse]]] = {}

    async def get_kline(self, symbol: str, limit: int = 252) -> Optional[StockKlineResponse]:
        cache_key = f"{symbol}:{limit}"
        cached = self._kline_cache.get(cache_key)
        if cached is not None:
            return cached
        inflight = self._inflight.get(cache_key)
        if inflight is not None:
            return await inflight

        task = asyncio.create_task(self._fetch_kline(symbol, limit))
        self._inflight[cache_key] = task
        try:
            result = await task
            if result is not None:
                self._kline_cache[cache_key] = result
            return result
        finally:
            self._inflight.pop(cache_key, None)

    async def _fetch_kline(self, symbol: str, limit: int) -> Optional[StockKlineResponse]:
        try:
            resp = await self.gateway.benchmark_klines(symbol, limit=limit)
            rows = resp.data
            if not rows:
                return None

            bars = []
            for row in rows:
                bar = parse_benchmark_bar(row, symbol)
                if bar is not None:
                    bars.append(bar)

            bars.sort(key=lambda b: b.bar_time)
            as_of = bars[-1].bar_time if bars else None
            return StockKlineResponse(symbol=symbol, as_of=as_of, bars=bars)
        except Exception as e:
            LOGGER.info(f"Failed to fetch benchmark kline for {symbol}: {e}")
            return None

    async def load(self) -> None:
        markets = {"us": [("SPY", "SPDR S&P 500"), ("QQQ", "Invesco QQQ")], "sh": [("000001.SH", "SSE Composite Index")], "hk": [("HSI", "Hang Seng Index")]}

        response = DojoMeshBenchmarksResponse(markets={})
        latest_as_of = None

        async def fetch_market_symbol(market: str, sym: str, name_en: str):
            kline_resp = await self.get_kline(sym, limit=30)
            if not kline_resp or not kline_resp.bars:
                return None
            last_bar = kline_resp.bars[-1]
            klines = [BenchmarkKline(datetime=b.bar_time, close=b.close) for b in kline_resp.bars]
            card = BenchmarkCard(market=market, symbol=sym, name=BilingualText(zh=name_en, en=name_en), price=last_bar.close, change_percent=last_bar.change_p, kline=klines)
            return market, sym, kline_resp.as_of, card

        tasks = []
        for market, symbols in markets.items():
            for sym, name_en in symbols:
                tasks.append(fetch_market_symbol(market, sym, name_en))

        results = await asyncio.gather(*tasks)

        market_cards_map: Dict[str, list] = {m: [] for m in markets.keys()}
        for res in results:
            if res:
                m, sym, as_of, card = res
                market_cards_map[m].append(card)
                if not latest_as_of or (as_of and as_of > latest_as_of):
                    latest_as_of = as_of

        for market, symbols in markets.items():
            if market_cards_map[market]:
                default_symbol = symbols[0][0] if symbols else ""
                response.markets[market] = MarketBenchmarks(default_benchmark=default_symbol, benchmarks=market_cards_map[market])

        response.as_of = latest_as_of
        self.cached = response

    async def get_benchmarks(self) -> DojoMeshBenchmarksResponse:
        if not self.cached:
            await self.load()
        return self.cached or DojoMeshBenchmarksResponse(markets={})
