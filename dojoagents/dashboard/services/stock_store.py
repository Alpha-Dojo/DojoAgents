from __future__ import annotations
from dojoagents.logging import LOGGER

import anyio
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from dojo.client.async_client import AsyncDojo

from dojoagents.dashboard.services.market_stats import compute_market_stats
from dojoagents.dashboard.services.stock_quote_filter import stock_passes_ticker_market_cap_min
from dojoagents.dashboard.schemas.market import MarketStats
from dojoagents.dashboard.schemas.stock import Stock, StockQuote
from dojoagents.dashboard.services.dojo_data_gateway import DojoDataGateway
from dojoagents.dashboard.services.domain_utils import normalize_market_code
from dojoagents.utils.async_runtime import gather_ordered

MARKETS = ("sh", "hk", "us")


def parse_quote_item(item: dict, ticker: str) -> StockQuote:
    name = str(item.get("name") or ticker).strip()
    return StockQuote(
        ticker=ticker,
        name=name,
        last_price=float(item.get("last_price") or 0.0),
        pre_close=float(item.get("pre_close") or 0.0),
        open=float(item.get("open") or 0.0),
        high=float(item.get("high") or 0.0),
        low=float(item.get("low") or 0.0),
        change=float(item.get("change") or 0.0),
        change_percent=float(item.get("change_percent") or 0.0),
        volume=int(item.get("volume") or 0),
        amount=float(item.get("amount") or 0.0),
        avg_price=float(item.get("avg_price") or 0.0),
        market_cap=float(item.get("market_cap") or 0.0),
        total_shares=float(item.get("total_shares") or 0.0),
        turn_rate=float(item.get("turn_rate") or 0.0),
        pe=float(item.get("pe") or 0.0),
        pb=float(item.get("pb") or 0.0),
        dividend_yield=float(item.get("dividend_yield") or 0.0),
        quote_time=(str(item.get("quote_time")) if item.get("quote_time") is not None else None),
    )


QUOTE_BATCH_SIZE = 500


def _chunk_tickers(tickers: List[str], size: int) -> List[List[str]]:
    return [tickers[i : i + size] for i in range(0, len(tickers), size)]


async def fetch_quotes_by_market(
    client: AsyncDojo,
    market: str,
    tickers: List[str],
    batch_size: int = QUOTE_BATCH_SIZE,
) -> Dict[str, dict]:
    if not tickers:
        return {}

    quote_map: Dict[str, dict] = {}
    batches = _chunk_tickers(tickers, batch_size)

    async def fetch_batch(batch: List[str]) -> None:
        symbols = ",".join(batch)
        try:
            resp = await client.stocks.quote(symbols=symbols)
            data = resp.get("data", []) if isinstance(resp, dict) else resp
            if data:
                for item in data:
                    if isinstance(item, dict) and item.get("symbol"):
                        quote_map[item["symbol"]] = item
        except Exception as e:
            LOGGER.error(f"[StockStore] batch fetch error for {market}: {e}")

    await gather_ordered([lambda batch=batch: fetch_batch(batch) for batch in batches])
    return quote_map


def quote_lookup_key(market: str, ticker: str) -> str:
    key = ticker.strip().upper()
    if market in {"sh", "cn", "zh"}:
        for suffix in (".SS", ".SH", ".SZ"):
            if key.endswith(suffix):
                return key[: -len(suffix)]
    if market == "hk":
        if key.endswith(".HK"):
            key = key[:-3]
        if key.isdigit():
            return key.zfill(5)
    return key


def quote_time_sort_key(item: dict) -> str:
    """Ordering key for "latest quote" comparisons.

    ``quote_time`` values are ISO-8601 strings, which order lexicographically, so
    a plain string compare is both correct and allocation-free. Missing times sort
    lowest so a real timestamp always wins.
    """
    value = item.get("quote_time")
    return str(value) if value is not None else ""


def collapse_quotes_to_latest(
    rows: list[dict],
    market: str,
    into: Dict[str, dict] | None = None,
) -> Dict[str, dict]:
    """Reduce quote rows to the single latest row per symbol.

    The offline ``current_quote`` snapshot returns a per-symbol *history* (tens of
    rows each), so the raw payload for the US market alone is ~700k rows / >1 GB.
    Folding as we read keeps resident memory proportional to the symbol count
    rather than to symbol count x sessions.
    """
    quote_map: Dict[str, dict] = {} if into is None else into
    for item in rows:
        if not isinstance(item, dict):
            continue
        symbol = item.get("symbol") or item.get("ticker")
        if not symbol:
            continue
        key = quote_lookup_key(market, str(symbol))
        previous = quote_map.get(key)
        if previous is None or quote_time_sort_key(item) >= quote_time_sort_key(previous):
            quote_map[key] = item
    return quote_map


def attach_quotes(
    stocks: List[Stock],
    quote_map: Dict[str, dict],
    market: str,
) -> List[Stock]:
    loaded: List[Stock] = []
    for stock in stocks:
        quote_item = quote_map.get(quote_lookup_key(market, stock.ticker))
        if quote_item is not None:
            loaded.append(stock.model_copy(update={"stock_quote": parse_quote_item(quote_item, stock.ticker)}))
        else:
            loaded.append(stock)
    return loaded


class StockStore:
    def __init__(self, client: AsyncDojo) -> None:
        self.client = client
        gateway_method = getattr(type(client), "stocks", None)
        self.gateway = client if callable(gateway_method) else DojoDataGateway(client)
        self.by_market: Dict[str, List[Stock]] = {market: [] for market in MARKETS}
        self.by_ticker: Dict[str, Stock] = {}
        self._markets_by_ticker: Dict[str, List[str]] = {}
        self.loaded: bool = False
        self.last_quote_refresh_at: Optional[datetime] = None
        self.quote_as_of: Optional[str] = None
        self.quote_source: str = "sdk_snapshot"
        self.quote_stale: bool = False
        self._quote_refresh_lock = anyio.Lock()

    @staticmethod
    def _key(market: str, ticker: str) -> str:
        return f"{market}:{ticker.strip().upper()}"

    @staticmethod
    def _normalize_ticker(ticker: str) -> str:
        return ticker.strip().upper()

    @classmethod
    def _dedupe_stocks(cls, stocks: List[Stock]) -> List[Stock]:
        """Keep one row per ticker; prefer an entry that already has a quote."""
        ordered: dict[str, Stock] = {}
        for stock in stocks:
            key = cls._normalize_ticker(stock.ticker)
            existing = ordered.get(key)
            if existing is None or stock.stock_quote is not None:
                ordered[key] = stock
        return list(ordered.values())

    async def load(self) -> None:
        self.by_market = {market: [] for market in MARKETS}
        self.by_ticker = {}
        self._markets_by_ticker = {}
        total_loaded = 0
        quote_times: list[str] = []
        quote_sources: list[str] = []
        quote_stale = False

        for market in MARKETS:
            # 1. Fetch stock list
            result = await self.gateway.stocks(market=market)
            candidates = self._dedupe_stocks([Stock(**item) for item in result.data if isinstance(item, dict)])

            if candidates:
                tickers = [s.ticker for s in candidates]
                # Fold each batch into a latest-per-symbol map while streaming.
                # Accumulating the raw payload instead (as this used to do) pins
                # every historical quote row — ~1.5 GB for the US market alone.
                quote_map: Dict[str, dict] = {}
                raw_quote_rows = 0
                chunk_size = 200
                for i in range(0, len(tickers), chunk_size):
                    chunk = tickers[i : i + chunk_size]
                    res = await self.gateway.stock_quotes(market, chunk)
                    quote_sources.append(res.source)
                    quote_stale = quote_stale or res.stale
                    raw_quote_rows += len(res.data)
                    collapse_quotes_to_latest(res.data, market, into=quote_map)
                # Only the retained (latest) rows can carry the market's newest
                # quote time, so the max is unchanged while the list stays small.
                quote_times.extend(
                    str(item["quote_time"]) for item in quote_map.values() if item.get("quote_time") is not None
                )
                stocks = attach_quotes(candidates, quote_map, market)
                matched = sum(1 for stock in stocks if stock.stock_quote is not None)
                unmatched_sample = [self._normalize_ticker(stock.ticker) for stock in stocks if stock.stock_quote is None][:5]
                LOGGER.debug(
                    "[StockStore][%s] quote diagnostic: catalog=%s batches=%s returned_rows=%s "
                    "unique_quote_symbols=%s matched=%s request_sample=%s response_symbol_sample=%s unmatched_sample=%s",
                    market,
                    len(candidates),
                    (len(tickers) + chunk_size - 1) // chunk_size,
                    raw_quote_rows,
                    len(quote_map),
                    matched,
                    [self._normalize_ticker(ticker) for ticker in tickers[:5]],
                    list(quote_map)[:5],
                    unmatched_sample,
                )
            else:
                stocks = []

            self.by_market[market] = stocks
            for stock in stocks:
                normalized_ticker = self._normalize_ticker(stock.ticker)
                self.by_ticker[self._key(market, normalized_ticker)] = stock.model_copy(update={"ticker": normalized_ticker, "market": market})
                markets = self._markets_by_ticker.setdefault(normalized_ticker, [])
                if market not in markets:
                    markets.append(market)

            total_loaded += len(stocks)
            with_quote = sum(1 for stock in stocks if stock.stock_quote is not None)
            if stocks and with_quote == 0:
                LOGGER.error(
                    "[StockStore][%s] loaded %s stocks but 0 quotes — market-cap/sector features will be empty",
                    market,
                    len(stocks),
                )
            elif stocks and with_quote / len(stocks) < 0.1:
                LOGGER.warning(
                    "[StockStore][%s] quote coverage is low: %s/%s",
                    market,
                    with_quote,
                    len(stocks),
                )
            else:
                LOGGER.debug(f"[StockStore][{market}] loaded={len(stocks)} quotes={with_quote}")

        if total_loaded == 0:
            LOGGER.info("Warning: stock preload loaded 0 stocks.")

        self.loaded = True
        self.last_quote_refresh_at = datetime.now(timezone.utc)
        self.quote_as_of = max(quote_times) if quote_times else None
        self.quote_source = "sdk_online" if "sdk_online" in quote_sources else "sdk_snapshot"
        self.quote_stale = quote_stale

    async def refresh_symbols(self, market: str, tickers: List[str]) -> None:
        """Refresh a bounded ticker set from the live client when available."""
        if not tickers or not getattr(self.gateway, "has_live_client", False):
            return
        normalized_market = normalize_market_code(market) or market.strip().lower()
        result = await self.gateway.stock_quotes(normalized_market, tickers)
        quote_map = {
            quote_lookup_key(normalized_market, str(item.get("symbol") or item.get("ticker"))): item
            for item in result.data
            if isinstance(item, dict) and (item.get("symbol") or item.get("ticker"))
        }
        if not quote_map:
            return
        updated: list[Stock] = []
        for stock in self.by_market.get(normalized_market, []):
            item = quote_map.get(quote_lookup_key(normalized_market, stock.ticker))
            current = stock.model_copy(update={"stock_quote": parse_quote_item(item, stock.ticker)}) if item else stock
            updated.append(current)
            self.by_ticker[self._key(normalized_market, current.ticker)] = current
        self.by_market[normalized_market] = updated
        quote_times = [str(item["quote_time"]) for item in quote_map.values() if item.get("quote_time") is not None]
        if quote_times:
            self.quote_as_of = max(quote_times)
        self.quote_source = result.source
        self.quote_stale = result.stale
        self.last_quote_refresh_at = datetime.now(timezone.utc)

    async def refresh_quotes_if_stale(self, *, max_age_seconds: float = 60.0) -> None:
        """Refresh the loaded quote universe at a bounded cadence."""
        if not self.loaded or not getattr(self.gateway, "has_live_client", False):
            return
        now = datetime.now(timezone.utc)
        if self.last_quote_refresh_at is not None:
            age = (now - self.last_quote_refresh_at).total_seconds()
            if age < max(0.0, max_age_seconds):
                return
        async with self._quote_refresh_lock:
            now = datetime.now(timezone.utc)
            if self.last_quote_refresh_at is not None:
                age = (now - self.last_quote_refresh_at).total_seconds()
                if age < max(0.0, max_age_seconds):
                    return
            for market in MARKETS:
                tickers = [stock.ticker for stock in self.by_market.get(market, [])]
                for chunk in _chunk_tickers(tickers, 200):
                    await self.refresh_symbols(market, chunk)

    def get(self, market: str, ticker: str) -> Optional[Stock]:
        normalized_market = normalize_market_code(market) or market.strip().lower()
        return self.by_ticker.get(self._key(normalized_market, self._normalize_ticker(ticker)))

    def markets_for_ticker(self, ticker: str) -> List[str]:
        return list(self._markets_by_ticker.get(self._normalize_ticker(ticker), []))

    def resolve(self, ticker: str, market: str | None = None) -> Optional[Stock]:
        normalized_ticker = self._normalize_ticker(ticker)
        if market is not None:
            return self.get(market, normalized_ticker)
        markets = self._markets_by_ticker.get(normalized_ticker) or []
        if not markets:
            return None
        return self.get(markets[0], normalized_ticker)

    def find_market(self, ticker: str) -> Optional[str]:
        markets = self._markets_by_ticker.get(self._normalize_ticker(ticker)) or []
        return markets[0] if markets else None

    def has_quote(self, ticker: str, market: str | None = None) -> bool:
        stock = self.resolve(ticker, market=market)
        return stock is not None and stock.stock_quote is not None

    def is_ticker_market_cap_eligible(self, ticker: str, market: str | None = None) -> bool:
        stock = self.resolve(ticker, market=market)
        if stock is None:
            return False
        return stock_passes_ticker_market_cap_min(stock)

    def list_market(self, market: str) -> List[Stock]:
        return self.by_market.get(market, [])

    def market_stats(self, market: str) -> MarketStats:
        return compute_market_stats(market, self.list_market(market))

    def all_market_stats(self) -> Dict[str, MarketStats]:
        return {market: self.market_stats(market) for market in MARKETS}

    def stats(self) -> Dict[str, Any]:
        return {
            "loaded": self.loaded,
            "total": sum(len(items) for items in self.by_market.values()),
            "by_market": {market: len(self.by_market[market]) for market in MARKETS},
            "last_quote_refresh_at": (self.last_quote_refresh_at.isoformat() if self.last_quote_refresh_at else None),
            "quote_as_of": self.quote_as_of,
            "quote_source": self.quote_source,
            "quote_stale": self.quote_stale,
        }
