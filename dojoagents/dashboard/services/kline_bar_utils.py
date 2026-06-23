from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Dict, List, Optional

KLINE_LIMIT = 252


def normalize_datetime(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, (int, float)):
        ts = int(value)
        if ts > 1_000_000_000_000:
            ts //= 1000
        if ts > 0:
            return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")
        return ""

    raw = str(value).strip()
    if not raw:
        return ""
    if len(raw) >= 10 and raw[4] == "-" and raw[7] == "-":
        return raw[:10]
    if len(raw) == 8 and raw.isdigit():
        return f"{raw[:4]}-{raw[4:6]}-{raw[6:8]}"
    if raw.isdigit():
        ts = int(raw)
        if ts > 1_000_000_000_000:
            ts //= 1000
        if ts > 1_000_000_000:
            return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")
    return raw[:10] if len(raw) >= 10 else raw


def extract_bar_time(row: dict) -> str:
    for key in ("bar_time", "datetime", "date", "time", "trade_date", "tradeDate", "timestamp", "ts"):
        if key not in row:
            continue
        normalized = normalize_datetime(row.get(key))
        if normalized:
            return normalized
    return ""


def sort_raw_rows(rows: List[dict]) -> List[dict]:
    return sorted(rows, key=lambda row: extract_bar_time(row))


def trim_rows(rows: List[dict], limit: int = KLINE_LIMIT) -> List[dict]:
    sorted_rows = sort_raw_rows(rows)
    if len(sorted_rows) <= limit:
        return sorted_rows
    return sorted_rows[-limit:]


def merge_rows(existing: List[dict], incoming: List[dict]) -> List[dict]:
    """Merge bars by bar_time; keep full history (no trim)."""
    if not incoming:
        return sort_raw_rows(existing)
    by_time: Dict[str, dict] = {}
    for row in existing:
        bar_time = extract_bar_time(row)
        if bar_time:
            by_time[bar_time] = row
    for row in incoming:
        bar_time = extract_bar_time(row)
        if bar_time:
            by_time[bar_time] = row
    return [by_time[key] for key in sorted(by_time.keys())]


def latest_as_of(rows: List[dict]) -> Optional[str]:
    parsed = [extract_bar_time(row) for row in rows]
    parsed = [item for item in parsed if item]
    if not parsed:
        return None
    return sorted(parsed)[-1][:10]


def compute_incremental_fetch_limit(
    rows: List[dict],
    *,
    reference: Optional[date] = None,
    min_limit: int = 1,
    max_limit: int = KLINE_LIMIT,
) -> int:
    """
    How many daily bars to request on incremental refresh.

    Compare latest stored bar date with today: gap N calendar days -> fetch N bars
    (at least min_limit). Same-day or future-dated latest -> fetch 1 bar to refresh.
    """
    reference = reference or date.today()
    latest = latest_as_of(rows)
    if not latest:
        return min_limit

    try:
        latest_date = date.fromisoformat(latest[:10])
    except ValueError:
        return min_limit

    gap_days = (reference - latest_date).days
    if gap_days <= 0:
        return min_limit
    return min(max_limit, max(min_limit, gap_days))
