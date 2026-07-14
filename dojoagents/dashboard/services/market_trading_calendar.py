from __future__ import annotations

import exchange_calendars as xcals

MARKET_EXCHANGE_CALENDARS: dict[str, str] = {
    "us": "XNYS",
    "sh": "XSHG",
    "hk": "XHKG",
}


def trading_days_for_market(market: str, start_date: str, end_date: str) -> list[str]:
    calendar_name = MARKET_EXCHANGE_CALENDARS.get(market)
    if calendar_name is None:
        raise ValueError(f"unsupported market for trading calendar: {market}")

    start = start_date[:10]
    end = end_date[:10]
    if start > end:
        return []

    calendar = xcals.get_calendar(calendar_name)
    sessions = calendar.sessions_in_range(start, end)
    return [session.strftime("%Y-%m-%d") for session in sessions]
