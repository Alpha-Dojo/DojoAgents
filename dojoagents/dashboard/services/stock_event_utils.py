from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional

STOCK_EVENT_DEFAULT_PAGE_SIZE = 20


def extract_event_date(row: dict) -> str:
    """Normalize event date to YYYY-MM-DD for sorting and dedupe."""
    for key in (
        "notice_date",
        "event_date",
        "remind_date",
        "pub_date",
        "public_date",
        "date",
    ):
        raw = row.get(key)
        if raw is None:
            continue
        text = str(raw).strip()
        if not text:
            continue
        if "T" in text:
            text = text.split("T", 1)[0]
        elif " " in text:
            text = text.split(" ", 1)[0]
        try:
            return datetime.strptime(text[:10], "%Y-%m-%d").date().isoformat()
        except ValueError:
            return text[:10]
    return ""


def event_row_key(row: dict) -> str:
    for key in ("id", "event_id", "remind_id", "reminder_id", "notice_id"):
        value = row.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()

    date = extract_event_date(row)
    event_type = str(row.get("event_type") or row.get("type") or row.get("type_name") or row.get("event_type_name") or "").strip()
    title = str(row.get("level1_content") or row.get("title") or row.get("content") or row.get("event_content") or "").strip()
    return f"{date}|{event_type}|{title}"


def sort_event_rows(rows: List[dict]) -> List[dict]:
    return sorted(
        rows,
        key=lambda row: (
            extract_event_date(row),
            event_row_key(row),
        ),
        reverse=True,
    )


def merge_event_rows(existing: List[dict], incoming: List[dict]) -> List[dict]:
    by_key: Dict[str, dict] = {}
    for row in existing:
        key = event_row_key(row)
        if key:
            by_key[key] = row
    for row in incoming:
        key = event_row_key(row)
        if key:
            by_key[key] = row
    return sort_event_rows(list(by_key.values()))


def trim_event_rows(rows: List[dict], limit: int) -> List[dict]:
    if limit <= 0 or len(rows) <= limit:
        return rows
    return rows[:limit]


def latest_event_date(rows: List[dict]) -> Optional[str]:
    sorted_rows = sort_event_rows(rows)
    if not sorted_rows:
        return None
    return extract_event_date(sorted_rows[0]) or None


def normalize_remote_events(payload: object) -> List[dict]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict):
        for key in ("data", "items", "list", "records", "rows"):
            nested = payload.get(key)
            if isinstance(nested, list):
                return [row for row in nested if isinstance(row, dict)]
    return []
