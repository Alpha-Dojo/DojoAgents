"""Trading-calendar helpers used by Agent pipeline preflight."""

from __future__ import annotations

import exchange_calendars as xcals

MARKET_EXCHANGE_CALENDARS = {
    "us": "XNYS",
    "cn": "XSHG",
    "hk": "XHKG",
}
DEFAULT_MARKETS = ("us", "cn", "hk")


def canonical_market(market: str) -> str:
    text = str(market or "").strip().lower()
    if not text:
        raise ValueError("market is required")
    return "cn" if text == "sh" else text


def open_markets_on(
    date: str,
    markets: tuple[str, ...] | list[str] = DEFAULT_MARKETS,
) -> list[str]:
    day = str(date or "").strip()[:10]
    if not day:
        return []
    result: list[str] = []
    for raw_market in markets:
        market = canonical_market(raw_market)
        if market in result:
            continue
        calendar_name = MARKET_EXCHANGE_CALENDARS.get(market)
        if calendar_name is None:
            raise ValueError(f"unsupported market for trading calendar: {raw_market}")
        if not xcals.get_calendar(calendar_name).sessions_in_range(day, day).empty:
            result.append(market)
    return result


__all__ = ["DEFAULT_MARKETS", "canonical_market", "open_markets_on"]
