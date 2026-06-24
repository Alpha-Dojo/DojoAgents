from __future__ import annotations

from dataclasses import dataclass
import asyncio
from typing import Any, Dict, Optional

from dojo.client.async_client import AsyncDojo

from dojoagents.logging import LOGGER
from dojoagents.dashboard.schemas.stock_kline import StockKlineResponse, StockKlineBar
from dojoagents.dashboard.schemas.benchmark import (
    DojoMeshBenchmarksResponse,
    MarketBenchmarks,
    BenchmarkCard,
    BilingualText,
    BenchmarkKline,
)
from dojoagents.dashboard.services.dojo_data_gateway import DojoDataGateway
from dojoagents.dashboard.services.domain_utils import normalize_market_code

MARKETS = ("sh", "hk", "us")
DEFAULT_BENCHMARKS = {
    "sh": "000001.SS",
    "hk": "^HSI",
    "us": "^SPX",
}
BENCHMARK_EN: dict[str, str] = {
    "^SPX": "S&P 500 Index",
    "^NDX": "Nasdaq 100",
    "^IXIC": "Nasdaq Composite",
    "^DJI": "Dow Jones",
    "^HSI": "Hang Seng Index",
    "000001.SS": "SSE Composite Index",
    "000300.SS": "CSI 300 Index",
    "000905.SS": "CSI 500 Index",
}
DEFAULT_LOOKBACK_DAYS = 400


@dataclass(frozen=True)
class BenchmarkMeta:
    symbol: str
    market: str
    name: BilingualText
    sort_order: int = 0
    is_default: bool = False


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


def _display_name(row: dict[str, Any], symbol: str) -> BilingualText:
    name_zh = str(row.get("name_zh") or row.get("name_alias") or row.get("name") or symbol).strip()
    name_en = str(row.get("name_en") or row.get("name") or BENCHMARK_EN.get(symbol) or name_zh).strip()
    return BilingualText(zh=name_zh, en=name_en)


def _parse_metadata_row(row: dict[str, Any]) -> Optional[BenchmarkMeta]:
    symbol = str(row.get("symbol") or row.get("ticker") or "").strip()
    market = normalize_market_code(row.get("market"))
    if not symbol or not market:
        return None
    sort_order = int(row.get("sort_order") or 0)
    is_default = bool(row.get("is_default") or sort_order == 0)
    return BenchmarkMeta(
        symbol=symbol,
        market=market,
        name=_display_name(row, symbol),
        sort_order=sort_order,
        is_default=is_default,
    )


def _fallback_catalog() -> dict[str, list[BenchmarkMeta]]:
    catalog = {market: [] for market in MARKETS}
    for market, symbol in DEFAULT_BENCHMARKS.items():
        catalog[market].append(
            BenchmarkMeta(
                symbol=symbol,
                market=market,
                name=BilingualText(zh=symbol, en=BENCHMARK_EN.get(symbol, symbol)),
                sort_order=0,
                is_default=True,
            )
        )
    return catalog


def _window_change_percent(bars: list[StockKlineBar], days: int) -> float:
    if not bars:
        return 0.0
    if days <= 1 and len(bars) >= 2:
        base = bars[-2].close
        latest = bars[-1].close
    else:
        window = min(max(days, 1), len(bars) - 1) if len(bars) > 1 else 0
        base = bars[-1 - window].close if window > 0 else bars[0].close
        latest = bars[-1].close
    if base <= 0:
        return 0.0
    return (latest / base - 1.0) * 100.0


class BenchmarkStore:
    def __init__(self, client: AsyncDojo):
        self.client = client
        gateway_method = getattr(type(client), "benchmark_klines", None)
        self.gateway = client if callable(gateway_method) else DojoDataGateway(client)
        self._catalog: dict[str, list[BenchmarkMeta]] = _fallback_catalog()
        self._catalog_loaded = False
        self._response_cache: dict[int, DojoMeshBenchmarksResponse] = {}
        self._kline_cache: Dict[str, StockKlineResponse] = {}
        self._inflight: Dict[str, asyncio.Task[Optional[StockKlineResponse]]] = {}
        self._selected_defaults: dict[str, str | None] = {market: None for market in MARKETS}

    async def load(self) -> None:
        self._catalog = await self._load_catalog()
        self._catalog_loaded = True
        self._response_cache.clear()
        self._selected_defaults = {market: None for market in MARKETS}

    async def _load_catalog(self) -> dict[str, list[BenchmarkMeta]]:
        catalog = {market: [] for market in MARKETS}
        try:
            response = await self.gateway.benchmark_catalog()
            for row in response.data:
                if not isinstance(row, dict):
                    continue
                meta = _parse_metadata_row(row)
                if meta is None:
                    continue
                if bool(row.get("is_active", True)) is False:
                    continue
                catalog[meta.market].append(meta)
        except Exception as exc:
            LOGGER.warning("Failed to load benchmark catalog from SDK, using fallback: %s", exc)
        has_entries = any(catalog[market] for market in MARKETS)
        if not has_entries:
            return _fallback_catalog()
        for market in MARKETS:
            catalog[market].sort(key=lambda item: (0 if item.is_default else 1, item.sort_order, item.symbol))
        return catalog

    def available_symbols(self, market: str | None = None) -> list[str]:
        if market is not None:
            normalized = normalize_market_code(market)
            if normalized is None:
                return []
            return [item.symbol for item in self._catalog.get(normalized, [])]
        symbols = []
        for items in self._catalog.values():
            symbols.extend(item.symbol for item in items)
        return symbols

    def default_symbol(self, market: str) -> str | None:
        normalized = normalize_market_code(market)
        if normalized is None:
            return None
        return self._selected_defaults.get(normalized)

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
            bars = [bar for row in rows if (bar := parse_benchmark_bar(row, symbol)) is not None]
            bars.sort(key=lambda b: b.bar_time)
            as_of = bars[-1].bar_time if bars else None
            return StockKlineResponse(symbol=symbol, as_of=as_of, bars=bars)
        except Exception as exc:
            LOGGER.info("Failed to fetch benchmark kline for %s: %s", symbol, exc)
            return None

    async def _build_card(self, meta: BenchmarkMeta, *, days: int) -> Optional[BenchmarkCard]:
        limit = max(DEFAULT_LOOKBACK_DAYS, days + 5)
        kline_resp = await self.get_kline(meta.symbol, limit=limit)
        if not kline_resp or not kline_resp.bars:
            return None
        bars = kline_resp.bars
        latest = bars[-1]
        return BenchmarkCard(
            market=meta.market,
            symbol=meta.symbol,
            name=meta.name,
            price=round(latest.close, 2),
            change_percent=round(_window_change_percent(bars, days), 2),
            kline=[BenchmarkKline(datetime=bar.bar_time, close=round(bar.close, 2)) for bar in bars],
        )

    async def get_benchmarks(self, *, days: int = 1) -> DojoMeshBenchmarksResponse:
        if not self._catalog_loaded:
            await self.load()
        cached = self._response_cache.get(days)
        if cached is not None:
            return cached

        response = DojoMeshBenchmarksResponse(markets={})
        latest_as_of: str | None = None

        for market in MARKETS:
            cards: list[BenchmarkCard] = []
            for meta in self._catalog.get(market, []):
                card = await self._build_card(meta, days=days)
                if card is None:
                    continue
                cards.append(card)
                if card.kline:
                    as_of = card.kline[-1].datetime
                    latest_as_of = as_of if latest_as_of is None else max(latest_as_of, as_of)
            if not cards:
                self._selected_defaults[market] = None
                continue

            default_symbol = None
            for meta in self._catalog.get(market, []):
                if any(card.symbol == meta.symbol for card in cards):
                    default_symbol = meta.symbol
                    break
            if default_symbol is None:
                default_symbol = cards[0].symbol
            self._selected_defaults[market] = default_symbol
            response.markets[market] = MarketBenchmarks(
                default_benchmark=default_symbol,
                benchmarks=cards,
            )

        response.as_of = latest_as_of
        self._response_cache[days] = response
        return response
