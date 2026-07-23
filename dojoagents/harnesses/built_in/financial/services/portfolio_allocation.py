from __future__ import annotations

import math
from typing import Dict, Iterable, List, Optional

from dojoagents.harnesses.built_in.financial.services.kline_bar_utils import extract_bar_time
from dojoagents.harnesses.built_in.financial.services.kline_store import KlineStore
from dojoagents.harnesses.built_in.financial.services.stock_store import StockStore

MARKETS = ("us", "sh", "hk")


def normalize_shares(market: str, raw_shares: float) -> int:
    if not math.isfinite(raw_shares) or raw_shares <= 0:
        return 0
    if market == "us":
        return int(math.floor(raw_shares))
    if raw_shares < 50:
        return 0
    if raw_shares < 100:
        return 100
    return int(round(raw_shares / 100) * 100)


async def lookup_open_price(
    kline_store: KlineStore,
    ticker: str,
    date_str: str,
) -> Optional[float]:
    rows = (await kline_store.get_or_fetch_kline(ticker)).bars
    if not rows:
        return None

    target = date_str[:10]
    exact: Optional[float] = None
    nearest_after: Optional[tuple[str, float]] = None
    nearest_before: Optional[tuple[str, float]] = None

    for row in rows:
        bar_time = extract_bar_time(row)[:10]
        if not bar_time:
            continue
        try:
            open_price = float(row.get("open") or 0)
        except (TypeError, ValueError):
            continue
        if open_price <= 0:
            continue
        if bar_time == target:
            exact = open_price
            break
        if bar_time > target:
            if nearest_after is None or bar_time < nearest_after[0]:
                nearest_after = (bar_time, open_price)
        elif bar_time < target:
            if nearest_before is None or bar_time > nearest_before[0]:
                nearest_before = (bar_time, open_price)

    if exact is not None:
        return exact
    if nearest_before is not None:
        return nearest_before[1]
    if nearest_after is not None:
        return nearest_after[1]
    return None


def resolve_cost_date(
    holding_row: dict,
    config: Optional[dict],
) -> Optional[str]:
    for field in ("open_date", "cost_date"):
        holding_value = holding_row.get(field)
        if isinstance(holding_value, str) and holding_value.strip():
            return holding_value.strip()[:10]
    if not isinstance(config, dict):
        return None
    for key in ("start_date", "cost_date"):
        value = config.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()[:10]
    return None


def holding_uses_default_open_date(holding_row: dict) -> bool:
    for field in ("open_date", "cost_date"):
        value = holding_row.get(field)
        if isinstance(value, str) and value.strip():
            return False
    return True


async def allocate_market_cap_weighted(
    stock_store: StockStore,
    holdings: Iterable[dict],
    market: str,
    capital: float,
    *,
    skip_manual: bool = True,
) -> Dict[str, int]:
    if capital <= 0:
        return {}

    eligible: List[dict] = []
    for row in holdings:
        if not isinstance(row, dict):
            continue
        if str(row.get("market")) != market:
            continue
        if skip_manual and bool(row.get("manual_shares")):
            continue
        ticker = str(row.get("ticker") or "")
        if not ticker:
            continue
        stock = stock_store.get(market, ticker)
        quote = stock.stock_quote if stock else None
        if quote is None or quote.last_price <= 0:
            continue
        market_cap = float(quote.market_cap or 0)
        if market_cap <= 0:
            continue
        eligible.append(
            {
                "ticker": ticker,
                "market": market,
                "market_cap": market_cap,
                "price": float(quote.last_price),
            }
        )

    if not eligible:
        return {}

    if len(eligible) == 1:
        item = eligible[0]
        shares = normalize_shares(market, capital / item["price"])
        return {item["ticker"]: shares}

    total_cap = sum(item["market_cap"] for item in eligible)
    preliminary: Dict[str, int] = {}
    for item in eligible:
        target_value = capital * (item["market_cap"] / total_cap)
        preliminary[item["ticker"]] = normalize_shares(market, target_value / item["price"])

    total_spent = sum(preliminary[item["ticker"]] * item["price"] for item in eligible if preliminary.get(item["ticker"], 0) > 0)
    if total_spent <= capital or total_spent <= 0:
        return preliminary

    scale = capital / total_spent
    scaled: Dict[str, int] = {}
    for item in eligible:
        ticker = item["ticker"]
        raw = preliminary.get(ticker, 0) * scale
        scaled[ticker] = normalize_shares(market, raw)
    return scaled


async def initial_shares_for_new_holding(
    stock_store: StockStore,
    holdings: Iterable[dict],
    market: str,
    ticker: str,
    capital: float,
) -> int:
    rows = [row for row in holdings if isinstance(row, dict) and str(row.get("market")) == market]
    prospective = [*rows, {"ticker": ticker, "market": market, "manual_shares": False}]
    allocated = await allocate_market_cap_weighted(
        stock_store,
        prospective,
        market,
        capital,
        skip_manual=False,
    )
    return allocated.get(ticker, 0)
