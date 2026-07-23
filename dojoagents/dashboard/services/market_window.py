from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Literal

from dojoagents.dashboard.services.domain_utils import validate_date_range

MarketWindowMode = Literal["days", "date_range"]

MAX_MARKET_WINDOW_DAYS = 90
MAX_MARKET_DATE_RANGE_CALENDAR_DAYS = 126


@dataclass(frozen=True)
class MarketAnalysisWindow:
    mode: MarketWindowMode
    days: int = 1
    start_date: str | None = None
    end_date: str | None = None
    resolved_start: str | None = None
    resolved_end: str | None = None

    def cache_key(self) -> tuple[str, ...]:
        if self.mode == "date_range":
            return ("date_range", self.start_date or "", self.end_date or "")
        return ("days", str(self.days))

    def with_resolved_bounds(self, *, start: str | None, end: str | None) -> MarketAnalysisWindow:
        return MarketAnalysisWindow(
            mode=self.mode,
            days=self.days,
            start_date=self.start_date,
            end_date=self.end_date,
            resolved_start=start,
            resolved_end=end,
        )


def resolve_market_analysis_window(
    *,
    days: int | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    default_days: int = 1,
) -> MarketAnalysisWindow:
    """Resolve a relative (days) or absolute (start/end) market analysis window."""
    normalized_start = str(start_date or "").strip() or None
    normalized_end = str(end_date or "").strip() or None
    validate_date_range(normalized_start, normalized_end)

    if normalized_start and normalized_end:
        start = date.fromisoformat(normalized_start)
        end = date.fromisoformat(normalized_end)
        span = (end - start).days + 1
        if span > MAX_MARKET_DATE_RANGE_CALENDAR_DAYS:
            raise ValueError(f"Date range spans {span} calendar days; maximum is {MAX_MARKET_DATE_RANGE_CALENDAR_DAYS}.")
        return MarketAnalysisWindow(
            mode="date_range",
            days=0,
            start_date=normalized_start,
            end_date=normalized_end,
        )

    resolved_days = int(days if days is not None else default_days)
    if resolved_days < 0 or resolved_days > MAX_MARKET_WINDOW_DAYS:
        raise ValueError(f"days must be between 0 and {MAX_MARKET_WINDOW_DAYS}")
    return MarketAnalysisWindow(mode="days", days=resolved_days)


def resolve_window_bounds_from_trade_dates(
    window: MarketAnalysisWindow,
    trade_dates: list[str],
) -> MarketAnalysisWindow:
    """Fill resolved_start/end from available trade dates inside the requested window."""
    normalized = sorted({str(item)[:10] for item in trade_dates if str(item or "").strip()})
    if not normalized:
        if window.mode == "date_range":
            raise ValueError(f"No trading data available between {window.start_date} and {window.end_date}.")
        return window

    if window.mode == "date_range":
        assert window.start_date and window.end_date
        in_range = [item for item in normalized if window.start_date <= item <= window.end_date]
        if not in_range:
            raise ValueError(f"No trading data available between {window.start_date} and {window.end_date}.")
        return window.with_resolved_bounds(start=in_range[0], end=in_range[-1])

    if window.days <= 1:
        resolved_end = normalized[-1]
        return window.with_resolved_bounds(start=resolved_end, end=resolved_end)

    start_index = max(0, len(normalized) - window.days)
    return window.with_resolved_bounds(start=normalized[start_index], end=normalized[-1])
