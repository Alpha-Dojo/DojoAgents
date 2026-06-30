from __future__ import annotations

import math
from datetime import date
from typing import Any, Iterable, Optional, TypeVar

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


def finite_float(value: Any, default: float = 0.0) -> float:
    if value is None:
        return default
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    if not math.isfinite(parsed):
        return default
    return parsed


def finite_optional_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(parsed):
        return None
    return parsed


def sanitize_mapping(mapping: dict[str, Any]) -> dict[str, Any]:
    sanitized: dict[str, Any] = {}
    for key, value in mapping.items():
        if isinstance(value, float) and not math.isfinite(value):
            sanitized[key] = None
        else:
            sanitized[key] = value
    return sanitized


def sanitize_records(df: Any) -> list[dict[str, Any]]:
    if df is None or getattr(df, "empty", False):
        return []
    records = df.to_dict(orient="records")
    return [sanitize_mapping(record) for record in records]


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
