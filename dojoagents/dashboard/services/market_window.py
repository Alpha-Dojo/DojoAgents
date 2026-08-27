from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date
from typing import Iterable, Literal

from dojoagents.dashboard.services.domain_utils import validate_date_range

MarketWindowMode = Literal["days", "date_range", "as_of"]

MAX_MARKET_WINDOW_DAYS = 90
MAX_MARKET_DATE_RANGE_CALENDAR_DAYS = 126

WINDOW_MODE_HELP = (
    "Window — pick ONE mode: "
    "(A) `days` alone = latest N trading sessions (default 1, max 90); "
    "(B) `as_of` + optional `days` = last N trading sessions with last session ≤ as_of "
    "(non-trading as_of falls back to the previous trade date; days defaults to 1); "
    "(C) `start_date` + `end_date` (YYYY-MM-DD, both required, max 126 calendar days). "
    "`as_of` cannot be combined with start_date/end_date. "
    "All modes compound each in-window session `daily_return` "
    "(1d = that session's daily_return; date_range compounds every trade session in the range). "
    "Response `window_start`/`window_end` echo the actual first/last trade dates used."
)


@dataclass(frozen=True)
class MarketAnalysisWindow:
    mode: MarketWindowMode
    days: int = 1
    as_of: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    resolved_start: str | None = None
    resolved_end: str | None = None

    def cache_key(self) -> tuple[str, ...]:
        if self.mode == "date_range":
            return ("date_range", self.start_date or "", self.end_date or "")
        if self.mode == "as_of":
            return ("as_of", self.as_of or "", str(self.days))
        return ("days", str(self.days))

    def with_resolved_bounds(self, *, start: str | None, end: str | None) -> MarketAnalysisWindow:
        return MarketAnalysisWindow(
            mode=self.mode,
            days=self.days,
            as_of=self.as_of,
            start_date=self.start_date,
            end_date=self.end_date,
            resolved_start=start,
            resolved_end=end,
        )


def _normalize_iso_date(value: str | None, *, field: str) -> str | None:
    text = str(value or "").strip() or None
    if text is None:
        return None
    try:
        date.fromisoformat(text)
    except ValueError as exc:
        raise ValueError(f"{field} must be YYYY-MM-DD") from exc
    return text


def compound_return_pct(daily_return_pcts: Iterable[float]) -> float:
    """Compound percent daily returns into one percent total return."""
    factor = 1.0
    for raw in daily_return_pcts:
        value = float(raw)
        if not math.isfinite(value):
            return 0.0
        factor *= 1.0 + value / 100.0
        if not math.isfinite(factor) or factor <= 0:
            return 0.0
    return (factor - 1.0) * 100.0


def resolve_market_analysis_window(
    *,
    days: int | None = None,
    as_of: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    default_days: int = 1,
    max_calendar_days: int = MAX_MARKET_DATE_RANGE_CALENDAR_DAYS,
) -> MarketAnalysisWindow:
    """Resolve latest-N, as_of+days, or calendar start/end windows.

    Session count for (A)/(B) is `days` when provided, else `default_days`.
    """
    normalized_start = str(start_date or "").strip() or None
    normalized_end = str(end_date or "").strip() or None
    normalized_as_of = _normalize_iso_date(as_of, field="as_of")
    validate_date_range(normalized_start, normalized_end)

    if normalized_as_of and (normalized_start or normalized_end):
        raise ValueError("as_of cannot be combined with start_date/end_date")

    if normalized_start and normalized_end:
        start = date.fromisoformat(normalized_start)
        end = date.fromisoformat(normalized_end)
        span = (end - start).days + 1
        if span > max_calendar_days:
            raise ValueError(f"Date range spans {span} calendar days; maximum is {max_calendar_days}.")
        return MarketAnalysisWindow(
            mode="date_range",
            days=0,
            start_date=normalized_start,
            end_date=normalized_end,
        )

    resolved_days = int(days) if days is not None else int(default_days)
    if resolved_days < 0 or resolved_days > MAX_MARKET_WINDOW_DAYS:
        raise ValueError(f"days must be between 0 and {MAX_MARKET_WINDOW_DAYS}")
    if normalized_as_of:
        return MarketAnalysisWindow(mode="as_of", days=resolved_days, as_of=normalized_as_of)
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
        if window.mode == "as_of":
            raise ValueError(f"No trading data available on or before {window.as_of}.")
        return window

    if window.mode == "date_range":
        assert window.start_date and window.end_date
        in_range = [item for item in normalized if window.start_date <= item <= window.end_date]
        if not in_range:
            raise ValueError(f"No trading data available between {window.start_date} and {window.end_date}.")
        return window.with_resolved_bounds(start=in_range[0], end=in_range[-1])

    eligible = normalized
    if window.mode == "as_of":
        assert window.as_of
        eligible = [item for item in normalized if item <= window.as_of]
        if not eligible:
            raise ValueError(f"No trading data available on or before {window.as_of}.")

    sessions = window.days if window.days > 1 else 1
    if sessions <= 1:
        resolved_end = eligible[-1]
        return window.with_resolved_bounds(start=resolved_end, end=resolved_end)

    start_index = max(0, len(eligible) - sessions)
    return window.with_resolved_bounds(start=eligible[start_index], end=eligible[-1])
