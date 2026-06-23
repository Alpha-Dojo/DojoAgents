from __future__ import annotations

from datetime import date
from typing import Iterable, Optional, TypeVar

T = TypeVar("T")

MARKET_ALIAS_TO_INTERNAL = {
    "cn": "sh",
    "sh": "sh",
    "hk": "hk",
    "us": "us",
}
MARKET_INTERNAL_TO_NATIVE = {
    "sh": "cn",
    "hk": "hk",
    "us": "us",
}


def normalize_market_code(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    return MARKET_ALIAS_TO_INTERNAL.get(value.strip().lower())


def to_native_market_code(value: Optional[str]) -> Optional[str]:
    normalized = normalize_market_code(value)
    if normalized is None:
        return None
    return MARKET_INTERNAL_TO_NATIVE.get(normalized, normalized)


def validate_date_range(start_date: Optional[str], end_date: Optional[str]) -> None:
    if bool(start_date) != bool(end_date):
        raise ValueError("start_date and end_date must be used together")
    if not start_date or not end_date:
        return
    start = date.fromisoformat(start_date)
    end = date.fromisoformat(end_date)
    if start > end:
        raise ValueError("start_date must not be later than end_date")


def filter_date_rows(
    rows: Iterable[T],
    *,
    start_date: Optional[str],
    end_date: Optional[str],
    extract_date,
) -> list[T]:
    if not start_date or not end_date:
        return list(rows)
    start = date.fromisoformat(start_date)
    end = date.fromisoformat(end_date)
    results: list[T] = []
    for row in rows:
        raw = extract_date(row)
        if not raw:
            continue
        try:
            current = date.fromisoformat(str(raw)[:10])
        except ValueError:
            continue
        if start <= current <= end:
            results.append(row)
    return results
