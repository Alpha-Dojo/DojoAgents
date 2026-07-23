"""Fetch and normalize market-dynamics events from the Dojo SDK."""

from __future__ import annotations

import asyncio
import json
import math
from datetime import date, datetime, timedelta
from typing import Any

from dojo.client.async_client import AsyncDojo

from dojoagents.harnesses.built_in.financial.contracts.domain_api import (
    MarketDynamicsEvent,
    MarketDynamicsResponse,
    MarketDynamicsSectorImpact,
    MarketDynamicsSummary,
)
from dojoagents.harnesses.built_in.financial.contracts.dojo_mesh import BilingualText
from dojoagents.logging import LOGGER

# Full normalized catalog (SDK offline ignores start/end; we filter here).
_events_cache: list[MarketDynamicsEvent] | None = None
_events_cache_lock = asyncio.Lock()
_SDK_FETCH_LIMIT = 10000


def clear_market_dynamics_cache() -> None:
    """Drop the in-process event catalog (e.g. after offline data refresh)."""
    global _events_cache
    _events_cache = None


def _parse_maybe_json(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    if isinstance(value, str):
        text = value.strip()
        if not text or text.lower() in {"nan", "none", "null"}:
            return None
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return value
    return value


def _bilingual(value: Any) -> BilingualText:
    if isinstance(value, dict):
        return BilingualText(
            zh=str(value.get("zh") or ""),
            en=str(value.get("en") or ""),
        )
    if isinstance(value, str) and value:
        return BilingualText(zh=value, en=value)
    return BilingualText()


def _calendar_date(event_time: str) -> str:
    stamp = str(event_time or "").strip()
    if not stamp:
        return ""
    try:
        parsed = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
        return parsed.date().isoformat()
    except ValueError:
        return stamp[:10] if len(stamp) >= 10 else stamp


def _make_event_id(event_time: str, index: int) -> str:
    date = _calendar_date(event_time) or "unknown"
    safe_time = "".join(ch if ch.isalnum() else "-" for ch in str(event_time))[:32]
    return f"{date}__{safe_time}__{index}"


def _normalize_impact(raw: Any) -> MarketDynamicsSectorImpact | None:
    if not isinstance(raw, dict):
        return None
    sector_id = str(raw.get("sector_id") or "").strip()
    if not sector_id:
        return None
    markets = raw.get("affected_markets") or []
    if not isinstance(markets, list):
        markets = []
    return MarketDynamicsSectorImpact(
        sector_id=sector_id,
        sector_name=_bilingual(raw.get("sector_name")),
        affected_markets=[str(m).strip().lower() for m in markets if str(m).strip()],
        direction=str(raw.get("direction") or "Divergent"),
        reason=str(raw.get("reason") or ""),
    )


def normalize_market_dynamics_row(row: dict[str, Any], index: int) -> MarketDynamicsEvent | None:
    event_time = str(row.get("event_time") or "").strip()
    summary_raw = _parse_maybe_json(row.get("event_summary"))
    if not isinstance(summary_raw, dict):
        return None

    impacts_raw = _parse_maybe_json(row.get("sector_impacts")) or []
    if not isinstance(impacts_raw, list):
        impacts_raw = []
    impacts = [impact for impact in (_normalize_impact(item) for item in impacts_raw) if impact]

    category = str(summary_raw.get("category") or "market_structure")
    surprise = str(summary_raw.get("surprise") or "expected")
    trading_date = _calendar_date(event_time)

    return MarketDynamicsEvent(
        id=_make_event_id(event_time, index),
        event_time=event_time,
        trading_date=trading_date,
        event_summary=MarketDynamicsSummary(
            headline=_bilingual(summary_raw.get("headline")),
            content=_bilingual(summary_raw.get("content")),
            source=_bilingual(summary_raw.get("source")),
            category=category,
            surprise=surprise,
        ),
        sector_impacts=impacts,
    )


def _unwrap_payload(payload: Any) -> tuple[list[Any], int | None]:
    if isinstance(payload, dict):
        data = payload.get("data")
        total = payload.get("total_num")
        if isinstance(data, list):
            return data, int(total) if isinstance(total, int) else len(data)
        return [], 0
    data = getattr(payload, "data", None)
    total = getattr(payload, "total_num", None)
    if isinstance(data, list):
        return data, int(total) if isinstance(total, int) else len(data)
    return [], 0


def _normalize_date_bound(value: str | None) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    return text[:10]


def _trading_dates(events: list[MarketDynamicsEvent]) -> list[str]:
    dates = sorted({event.trading_date for event in events if event.trading_date})
    return dates


def filter_events_by_date_window(
    events: list[MarketDynamicsEvent],
    *,
    start_date: str | None = None,
    end_date: str | None = None,
) -> tuple[list[MarketDynamicsEvent], bool, bool]:
    """Return events in [start_date, end_date] plus has_more_before/after flags."""
    start = _normalize_date_bound(start_date)
    end = _normalize_date_bound(end_date)
    if not start and not end:
        return list(events), False, False

    filtered: list[MarketDynamicsEvent] = []
    has_more_before = False
    has_more_after = False
    for event in events:
        day = event.trading_date or _calendar_date(event.event_time)
        if not day:
            continue
        if start and day < start:
            has_more_before = True
            continue
        if end and day > end:
            has_more_after = True
            continue
        filtered.append(event)
    return filtered, has_more_before, has_more_after


async def _load_catalog(client: AsyncDojo) -> list[MarketDynamicsEvent]:
    global _events_cache
    if _events_cache is not None:
        return _events_cache

    async with _events_cache_lock:
        if _events_cache is not None:
            return _events_cache

        try:
            payload = await client.analysis.get_market_dynamics(limit=_SDK_FETCH_LIMIT)
        except Exception:
            LOGGER.exception("Failed to fetch market dynamics from Dojo SDK")
            raise

        rows, _total = _unwrap_payload(payload)
        events: list[MarketDynamicsEvent] = []
        for index, row in enumerate(rows):
            if not isinstance(row, dict):
                continue
            event = normalize_market_dynamics_row(row, index)
            if event is not None:
                events.append(event)

        events.sort(key=lambda item: (item.trading_date, item.event_time, item.id))
        _events_cache = events
        LOGGER.debug("Cached %s market dynamics events", len(events))
        return events


def _default_latest_window(
    trading_dates: list[str],
    *,
    span_days: int = 14,
) -> tuple[str, str]:
    if not trading_dates:
        return "", ""
    end = trading_dates[-1]
    try:
        end_d = date.fromisoformat(end)
        start = (end_d - timedelta(days=span_days)).isoformat()
    except ValueError:
        start = trading_dates[0]
    return start, end


async def build_market_dynamics(
    client: AsyncDojo,
    *,
    limit: int = 5000,
    start_date: str | None = None,
    end_date: str | None = None,
) -> MarketDynamicsResponse:
    catalog = await _load_catalog(client)
    trading_dates = _trading_dates(catalog)
    dataset_start = trading_dates[0] if trading_dates else ""
    dataset_end = trading_dates[-1] if trading_dates else ""

    start = _normalize_date_bound(start_date)
    end = _normalize_date_bound(end_date)
    if not start and not end:
        start, end = _default_latest_window(trading_dates)

    windowed, has_more_before, has_more_after = filter_events_by_date_window(
        catalog,
        start_date=start or None,
        end_date=end or None,
    )

    # Optional safety cap when callers request an unbounded dump.
    if limit > 0 and len(windowed) > limit:
        windowed = windowed[-limit:]
        has_more_before = True

    window_start = ""
    window_end = ""
    if windowed:
        window_start = windowed[0].trading_date or _calendar_date(windowed[0].event_time)
        window_end = windowed[-1].trading_date or _calendar_date(windowed[-1].event_time)
    else:
        window_start = start
        window_end = end

    return MarketDynamicsResponse(
        total_num=len(catalog),
        events=windowed,
        window_start=window_start,
        window_end=window_end,
        dataset_start=dataset_start,
        dataset_end=dataset_end,
        has_more_before=has_more_before,
        has_more_after=has_more_after,
        trading_dates=trading_dates,
    )
