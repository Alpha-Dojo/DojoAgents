from __future__ import annotations

from typing import Any, List, Optional

AGGREGATE_ITEM_NAMES = frozenset({"总计", "合计"})


def is_aggregate_item_name(value: Any) -> bool:
    name = str(value or "").strip()
    return name in AGGREGATE_ITEM_NAMES


def parse_report_date(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def latest_report_date(rows: List[dict[str, Any]]) -> Optional[str]:
    dates = [parse_report_date(row.get("report_date")) for row in rows]
    valid = [date for date in dates if date]
    return max(valid) if valid else None


def filter_income_rows(rows: List[dict[str, Any]]) -> List[dict[str, Any]]:
    return [row for row in rows if isinstance(row, dict) and not is_aggregate_item_name(row.get("item_name"))]


def income_rows_signature(rows: List[dict[str, Any]]) -> tuple[Optional[str], int]:
    return latest_report_date(rows), len(rows)
