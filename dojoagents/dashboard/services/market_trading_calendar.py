from __future__ import annotations

import exchange_calendars as xcals

# Public market codes. `sh` is accepted as a legacy alias for `cn`.
MARKET_EXCHANGE_CALENDARS: dict[str, str] = {
    "us": "XNYS",
    "cn": "XSHG",
    "hk": "XHKG",
}

_MARKET_ALIASES: dict[str, str] = {
    "sh": "cn",
}

DEFAULT_MARKETS: tuple[str, ...] = ("us", "cn", "hk")


def canonical_market(market: str) -> str:
    text = str(market or "").strip().lower()
    if not text:
        raise ValueError("market is required")
    return _MARKET_ALIASES.get(text, text)


def trading_days_for_market(market: str, start_date: str, end_date: str) -> list[str]:
    code = canonical_market(market)
    calendar_name = MARKET_EXCHANGE_CALENDARS.get(code)
    if calendar_name is None:
        raise ValueError(f"unsupported market for trading calendar: {market}")

    start = start_date[:10]
    end = end_date[:10]
    if start > end:
        return []

    calendar = xcals.get_calendar(calendar_name)
    sessions = calendar.sessions_in_range(start, end)
    return [session.strftime("%Y-%m-%d") for session in sessions]


def is_trading_day(market: str, date: str) -> bool:
    day = str(date or "").strip()[:10]
    if not day:
        return False
    return day in trading_days_for_market(market, day, day)


def open_markets_on(
    date: str,
    markets: tuple[str, ...] | list[str] = DEFAULT_MARKETS,
) -> list[str]:
    day = str(date or "").strip()[:10]
    if not day:
        return []
    open_markets: list[str] = []
    seen: set[str] = set()
    for market in markets:
        code = canonical_market(market)
        if code in seen:
            continue
        seen.add(code)
        if is_trading_day(code, day):
            open_markets.append(code)
    return open_markets
