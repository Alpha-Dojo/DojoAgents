from __future__ import annotations
from dojoagents.logging import LOGGER

import asyncio
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from dojo.client.async_client import AsyncDojo

from dojoagents.dashboard.services.market_stats import compute_market_stats
from dojoagents.dashboard.services.stock_quote_filter import stock_passes_ticker_market_cap_min
from dojoagents.dashboard.schemas.market import MarketStats
from dojoagents.dashboard.schemas.stock import Stock, StockQuote
from dojoagents.dashboard.services.dojo_data_gateway import DojoDataGateway
from dojoagents.dashboard.services.domain_utils import normalize_market_code

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

    await asyncio.gather(*(fetch_batch(b) for b in batches))
    return quote_map


def attach_quotes(
    stocks: List[Stock],
    quote_map: Dict[str, dict],
) -> List[Stock]:
    loaded: List[Stock] = []
    for stock in stocks:
        quote_item = quote_map.get(stock.ticker)
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

    @staticmethod
    def _key(market: str, ticker: str) -> str:
        return f"{market}:{ticker.strip().upper()}"

    @staticmethod
    def _normalize_ticker(ticker: str) -> str:
        return ticker.strip().upper()

    async def load(self) -> None:
        self.by_market = {market: [] for market in MARKETS}
        self.by_ticker = {}
        self._markets_by_ticker = {}
        total_loaded = 0

        for market in MARKETS:
            # 1. Fetch stock list
            result = await self.gateway.stocks(market=market)
            candidates = [Stock(**item) for item in result.data if isinstance(item, dict)]

            if candidates:
                tickers = [s.ticker for s in candidates]
                quote_result_data = []
                chunk_size = 200
                for i in range(0, len(tickers), chunk_size):
                    chunk = tickers[i : i + chunk_size]
                    res = await self.gateway.stock_quotes(market, chunk)
                    quote_result_data.extend([item for item in res.data if isinstance(item, dict)])
                quote_map = {str(item.get("symbol") or item.get("ticker")): item for item in quote_result_data if (item.get("symbol") or item.get("ticker"))}
                stocks = attach_quotes(candidates, quote_map)
            else:
                stocks = []

            self.by_market[market] = stocks
            for stock in stocks:
                normalized_ticker = self._normalize_ticker(stock.ticker)
                self.by_ticker[self._key(market, normalized_ticker)] = stock.model_copy(update={"ticker": normalized_ticker, "market": market})
                self._markets_by_ticker.setdefault(normalized_ticker, []).append(market)

            total_loaded += len(stocks)
            LOGGER.debug(f"[StockStore][{market}] loaded={len(stocks)}")

        if total_loaded == 0:
            LOGGER.info("Warning: stock preload loaded 0 stocks.")

        self.loaded = True
        self.last_quote_refresh_at = datetime.now(timezone.utc)

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
        }
