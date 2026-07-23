from __future__ import annotations

from typing import List, Optional, Tuple, Any

from dojoagents.dashboard.services.market_sector_lead import _stock_bilingual_name
from dojoagents.dashboard.services.sector_constituents import collect_sector_scope_tickers
from dojoagents.dashboard.services.sector_store import SectorStore
from dojoagents.dashboard.services.stock_store import StockStore
from dojoagents.dashboard.schemas.dojo_core import CoreTickerSearchItem
from dojoagents.dashboard.schemas.dojo_mesh import BilingualText
from dojoagents.dashboard.schemas.stock import Stock

MARKETS = ("sh", "hk", "us")
MARKET_ORDER = {"us": 0, "sh": 1, "hk": 2}
DEFAULT_LIMIT = 20
MAX_LIMIT = 50


def _normalize(value: str) -> str:
    return value.strip().casefold()


def _stock_name_fields(stock: Stock) -> Tuple[str, str]:
    names = _stock_bilingual_name(stock)
    return names.zh.strip(), names.en.strip()


def _match_score(stock: Stock, query: str) -> Optional[int]:
    """Lower score ranks higher; None means no match."""
    needle = _normalize(query)
    if not needle:
        return None

    ticker = _normalize(stock.ticker)
    name_zh, name_en = _stock_name_fields(stock)
    haystacks = [ticker, _normalize(name_zh), _normalize(name_en)]

    if any(item == needle for item in haystacks if item):
        return 0
    if ticker.startswith(needle):
        return 1
    if name_zh and _normalize(name_zh).startswith(needle):
        return 2
    if name_en and _normalize(name_en).startswith(needle):
        return 3
    if needle in ticker:
        return 4
    if name_zh and needle in _normalize(name_zh):
        return 5
    if name_en and needle in _normalize(name_en):
        return 6
    return None


def _sector_scope_tickers(
    sector_precomputed_store: Any,
    sector_store: SectorStore,
    *,
    level1_id: str,
    level2_id: str,
    level3_id: str,
    market: Optional[str],
) -> Optional[set[str]]:
    path = sector_store.find_resolved_path(level1_id, level2_id, level3_id)
    if path is None:
        return None
    scopes = collect_sector_scope_tickers(
        sector_precomputed_store,
        path,
        market=market,
    )
    return scopes.get("L3") or set()


def search_core_tickers(
    stock_store: StockStore,
    sector_precomputed_store: Any,
    sector_store: SectorStore,
    query: str,
    *,
    market: Optional[str] = None,
    level1_id: Optional[str] = None,
    level2_id: Optional[str] = None,
    level3_id: Optional[str] = None,
    limit: int = DEFAULT_LIMIT,
    require_market_cap_eligible: bool = True,
) -> List[CoreTickerSearchItem]:
    """Search quoted tickers by ticker symbol or display name (zh/en)."""
    needle = query.strip()
    if not needle:
        return []

    limit = max(1, min(limit, MAX_LIMIT))
    active_markets = (market,) if market in MARKETS else MARKETS

    scope_tickers: Optional[set[str]] = None
    if level1_id and level2_id and level3_id:
        scope_tickers = _sector_scope_tickers(
            sector_precomputed_store,
            sector_store,
            level1_id=level1_id,
            level2_id=level2_id,
            level3_id=level3_id,
            market=market if market in MARKETS else None,
        )
        if scope_tickers is not None and not scope_tickers:
            return []

    # (score, market_order, -market_cap, ticker, item); keep best row per market+ticker.
    best_by_key: dict[tuple[str, str], tuple[int, int, float, str, CoreTickerSearchItem]] = {}
    for market_code in active_markets:
        for stock in stock_store.list_market(market_code):
            if scope_tickers is not None and stock.ticker not in scope_tickers:
                continue
            if require_market_cap_eligible and not stock_store.is_ticker_market_cap_eligible(stock.ticker):
                continue
            quote = stock.stock_quote
            if quote is None:
                continue

            score = _match_score(stock, needle)
            if score is None:
                continue

            names = _stock_bilingual_name(stock)
            ticker = stock.ticker.strip().upper()
            item = CoreTickerSearchItem(
                ticker=ticker,
                market=stock.market,
                name=BilingualText(zh=names.zh, en=names.en),
                market_cap=quote.market_cap,
            )
            row = (
                score,
                MARKET_ORDER.get(stock.market, 99),
                -(quote.market_cap or 0.0),
                ticker,
                item,
            )
            key = (stock.market, ticker)
            prev = best_by_key.get(key)
            if prev is None or row[:4] < prev[:4]:
                best_by_key[key] = row

    ranked = sorted(best_by_key.values(), key=lambda row: (row[0], row[1], row[2], row[3]))
    return [item for _, _, _, _, item in ranked[:limit]]
