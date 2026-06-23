from __future__ import annotations

import re
from datetime import datetime
from difflib import SequenceMatcher
from typing import List

STOCK_NEWS_DEFAULT_PAGE_SIZE = 20
STOCK_NEWS_TITLE_SIMILARITY_THRESHOLD = 0.82

_TITLE_STRIP_RE = re.compile(r"[\s，。！？、；：\"'“”‘’【】\[\]()（）《》—–\-…·!?,.;:\"'\"]+")


def extract_news_publish_datetime(row: dict) -> str:
    for key in ("publish_date", "pub_date", "published_at", "date"):
        raw = row.get(key)
        if raw is None:
            continue
        text = str(raw).strip()
        if text:
            return text
    return ""


def extract_news_publish_date(row: dict) -> str:
    text = extract_news_publish_datetime(row)
    if not text:
        return ""
    if "T" in text:
        return text.split("T", 1)[0]
    if len(text) >= 10 and text[4] == "-" and text[7] == "-":
        return text[:10]
    for fmt in ("%b %d, %Y", "%B %d, %Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(text.strip(), fmt).date().isoformat()
        except ValueError:
            continue
    if " " in text:
        head = text.split(" ", 1)[0]
        if len(head) == 10 and head[4] == "-" and head[7] == "-":
            return head
    return text[:10]


def news_row_key(row: dict) -> str:
    for key in ("id", "news_id"):
        value = row.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()

    date = extract_news_publish_date(row)
    title = str(row.get("title") or "").strip()
    return f"{date}|{title}"


def _sort_datetime_key(text: str) -> str:
    if not text:
        return ""
    normalized = text.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(normalized).isoformat()
    except ValueError:
        return text


def sort_news_rows(rows: List[dict]) -> List[dict]:
    return sorted(
        rows,
        key=lambda row: (
            _sort_datetime_key(extract_news_publish_datetime(row)),
            news_row_key(row),
        ),
        reverse=True,
    )


def merge_news_rows(existing: List[dict], incoming: List[dict]) -> List[dict]:
    by_key: dict[str, dict] = {}
    for row in existing:
        key = news_row_key(row)
        if key:
            by_key[key] = row
    for row in incoming:
        key = news_row_key(row)
        if key:
            by_key[key] = row
    return sort_news_rows(list(by_key.values()))


def trim_news_rows(rows: List[dict], limit: int) -> List[dict]:
    if limit <= 0 or len(rows) <= limit:
        return rows
    return rows[:limit]


def latest_news_publish_date(rows: List[dict]) -> str | None:
    sorted_rows = sort_news_rows(rows)
    if not sorted_rows:
        return None
    return extract_news_publish_date(sorted_rows[0]) or None


def normalize_remote_news(payload: object) -> List[dict]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict):
        for key in ("data", "items", "list", "records", "rows"):
            nested = payload.get(key)
            if isinstance(nested, list):
                return [row for row in nested if isinstance(row, dict)]
    return []


def normalize_news_title(title: str) -> str:
    text = str(title or "").strip().lower()
    text = _TITLE_STRIP_RE.sub("", text)
    return text


def titles_similar(
    left: str,
    right: str,
    *,
    threshold: float = STOCK_NEWS_TITLE_SIMILARITY_THRESHOLD,
) -> bool:
    normalized_left = normalize_news_title(left)
    normalized_right = normalize_news_title(right)
    if not normalized_left or not normalized_right:
        return False
    if normalized_left == normalized_right:
        return True
    if len(normalized_left) >= 8 and len(normalized_right) >= 8:
        if normalized_left in normalized_right or normalized_right in normalized_left:
            return True
    return SequenceMatcher(None, normalized_left, normalized_right).ratio() >= threshold


def filter_similar_news_rows(
    rows: List[dict],
    *,
    threshold: float = STOCK_NEWS_TITLE_SIMILARITY_THRESHOLD,
) -> List[dict]:
    """Keep the newest row when multiple headlines are near-duplicates."""
    kept: List[dict] = []
    for row in sort_news_rows(rows):
        title = str(row.get("title") or "").strip()
        if not title:
            continue
        if any(titles_similar(title, str(existing.get("title") or ""), threshold=threshold) for existing in kept):
            continue
        kept.append(row)
    return kept


def prepare_news_rows(rows: List[dict], limit: int) -> List[dict]:
    return trim_news_rows(filter_similar_news_rows(rows), limit)
