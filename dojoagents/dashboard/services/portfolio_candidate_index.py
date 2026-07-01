from __future__ import annotations

from typing import Any

from dojoagents.dashboard.services.sector_earnings_index import (
    append_quote_session_point,
    compute_market_index_series,
)

CANDIDATE_INDEX_PREFIX = "__folio_candidate__"


def candidate_index_symbol(market: str) -> str:
    native = {"sh": "cn", "us": "us", "hk": "hk"}.get(market, market)
    return f"{CANDIDATE_INDEX_PREFIX}{native}__"


def parse_candidate_index_symbol(symbol: str) -> str | None:
    if not symbol.startswith(CANDIDATE_INDEX_PREFIX) or not symbol.endswith("__"):
        return None
    native = symbol[len(CANDIDATE_INDEX_PREFIX) : -2]
    return {"cn": "sh", "us": "us", "hk": "hk"}.get(native)


async def build_candidate_index_series_by_market(
    *,
    candidates: list[dict[str, Any]],
    stock_store,
    kline_store,
) -> dict[str, list[dict[str, float]]]:
    by_market: dict[str, set[str]] = {"us": set(), "sh": set(), "hk": set()}
    for row in candidates:
        if not isinstance(row, dict):
            continue
        market = str(row.get("market") or "")
        ticker = str(row.get("ticker") or "").strip()
        if market in by_market and ticker:
            by_market[market].add(ticker)

    result: dict[str, list[dict[str, float]]] = {}
    for market, tickers in by_market.items():
        if not tickers:
            continue
        series = await compute_market_index_series(tickers, stock_store, kline_store)
        if len(series) < 2:
            continue
        series = await append_quote_session_point(series, market, tickers, stock_store, kline_store)
        if len(series) < 2:
            continue
        result[market] = [{"date": day, "value": float(value)} for day, value in series]
    return result
