from __future__ import annotations

from typing import Optional

from dojoagents.harnesses.built_in.financial.services.domain_utils import normalize_market_code
from dojoagents.harnesses.built_in.financial.services.kline_bar_utils import (
    ashare_kline_symbol_candidates,
    infer_ashare_kline_suffix,
)


def resolve_ticker_symbol(
    stock_store,
    ticker: str,
    market: Optional[str],
) -> tuple[str, Optional[str]]:
    """Map user ticker input to canonical stock_store symbol (e.g. 0700 + hk -> 0700.HK)."""
    raw = ticker.strip().upper()
    internal_market = normalize_market_code(market)
    if not raw:
        return raw, internal_market

    if stock_store is not None:
        stock = stock_store.resolve(raw, market=internal_market)
        if stock is not None:
            resolved_market = normalize_market_code(stock.market) or internal_market
            return stock.ticker.strip().upper(), resolved_market

        candidates: list[str] = []
        if internal_market == "hk" and "." not in raw:
            candidates.append(f"{raw}.HK")
        if "." not in raw:
            candidates.extend(ashare_kline_symbol_candidates(raw))
        for candidate in candidates:
            stock = stock_store.resolve(candidate, market=internal_market)
            if stock is not None:
                resolved_market = normalize_market_code(stock.market) or internal_market
                return stock.ticker.strip().upper(), resolved_market
            lookup_market = internal_market or "sh"
            if infer_ashare_kline_suffix(raw) is not None:
                lookup_market = "sh"
            stock = stock_store.get(lookup_market, candidate)
            if stock is not None:
                return stock.ticker.strip().upper(), lookup_market

        if internal_market is None:
            for candidate in (raw, *candidates):
                found_market = stock_store.find_market(candidate)
                if not found_market:
                    continue
                stock = stock_store.get(found_market, candidate)
                if stock is not None:
                    return stock.ticker.strip().upper(), normalize_market_code(found_market)

    if internal_market == "hk" and "." not in raw:
        return f"{raw}.HK", internal_market
    ashare_suffix = infer_ashare_kline_suffix(raw)
    if ashare_suffix is not None and (internal_market in {None, "sh"}):
        return f"{raw}{ashare_suffix}", internal_market or "sh"
    return raw, internal_market
