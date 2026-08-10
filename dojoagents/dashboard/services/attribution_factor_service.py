"""Fetch attribution factors from Dojo SDK and apply local filters."""

from __future__ import annotations

import json
import math
import re
from datetime import datetime
from typing import Any, Literal

from dojo.client.async_client import AsyncDojo

from dojoagents.dashboard.schemas.domain_api import (
    SectorAttributionFactorEvidence,
    SectorAttributionFactorItem,
    SectorAttributionFactorsResponse,
)
from dojoagents.logging import LOGGER

LocaleCode = Literal["zh", "en"]
_SECTOR_REF_RE = re.compile(r"^\d+/\d+/\d+$")


def canonical_attribution_sector_ref(row: dict[str, Any]) -> str | None:
    """Return the canonical L1/L2/L3 path from an attribution-factor row."""
    for key in ("sector_ref", "sector_id"):
        value = _optional_str(row.get(key))
        if value is not None and _SECTOR_REF_RE.fullmatch(value):
            return value
    return None


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


def _normalize_market(market: str) -> str:
    code = str(market or "").strip().lower()
    if code == "sh":
        return "cn"
    if code not in {"cn", "hk", "us"}:
        raise ValueError("market must be one of: cn, hk, us (sh maps to cn)")
    return code


def _normalize_date_bound(value: str) -> str:
    text = str(value or "").strip()
    if len(text) < 10:
        raise ValueError("dates must be YYYY-MM-DD")
    return text[:10]


def _calendar_day(event_time: Any) -> str | None:
    stamp = str(event_time or "").strip()
    if not stamp or stamp.lower() in {"nan", "none", "null", "nat"}:
        return None
    try:
        parsed = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
        return parsed.date().isoformat()
    except ValueError:
        return stamp[:10] if len(stamp) >= 10 else None


def _locale_text(value: Any, locale: LocaleCode) -> str:
    parsed = _parse_maybe_json(value)
    if isinstance(parsed, dict):
        primary = str(parsed.get(locale) or "").strip()
        if primary:
            return primary
        other = "en" if locale == "zh" else "zh"
        return str(parsed.get(other) or "").strip()
    if isinstance(parsed, str):
        return parsed.strip()
    return ""


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none", "null"}:
        return None
    return text


def _string_list(value: Any) -> list[str]:
    parsed = _parse_maybe_json(value)
    if not isinstance(parsed, list):
        return []
    return [str(item).strip() for item in parsed if str(item).strip()]


def _evidence_list(value: Any) -> list[SectorAttributionFactorEvidence]:
    parsed = _parse_maybe_json(value)
    if not isinstance(parsed, list):
        return []
    items: list[SectorAttributionFactorEvidence] = []
    for raw in parsed:
        if not isinstance(raw, dict):
            continue
        quote = str(raw.get("quote") or "").strip()
        if not quote:
            continue
        items.append(
            SectorAttributionFactorEvidence(
                quote=quote,
                url=_optional_str(raw.get("url")),
                title=_optional_str(raw.get("title")),
            )
        )
    return items


def _unwrap_payload(payload: Any) -> list[Any]:
    if isinstance(payload, dict):
        data = payload.get("data")
        return data if isinstance(data, list) else []
    data = getattr(payload, "data", None)
    return data if isinstance(data, list) else []


def normalize_attribution_factor_row(
    row: dict[str, Any],
    *,
    locale: LocaleCode,
) -> SectorAttributionFactorItem | None:
    event_time = _optional_str(row.get("event_time"))
    if event_time is None or _calendar_day(event_time) is None:
        return None
    sector_id = canonical_attribution_sector_ref(row)
    market = str(row.get("market") or "").strip().lower()
    if not sector_id or not market:
        return None
    claim = _locale_text(row.get("claim"), locale)
    if not claim:
        return None
    return SectorAttributionFactorItem(
        event_time=event_time,
        claim=claim,
        mechanism=_locale_text(row.get("mechanism"), locale),
        sector_id=sector_id,
        market=market,
        factor_topic=str(row.get("factor_topic") or "").strip(),
        role=str(row.get("role") or "explains_move").strip() or "explains_move",
        price_direction=_optional_str(row.get("price_direction")),
        importance=_optional_str(row.get("importance")),
        stance=_optional_str(row.get("stance")),
        affected_tickers=_string_list(row.get("affected_tickers")),
        evidence=_evidence_list(row.get("evidence")),
    )


def filter_attribution_factor_rows(
    rows: list[dict[str, Any]],
    *,
    sector_id: str,
    start_date: str,
    end_date: str,
    locale: LocaleCode,
    limit: int | None = None,
) -> list[SectorAttributionFactorItem]:
    """Exact sector_id + event_time calendar-day window; drop empty event_time."""
    target = str(sector_id or "").strip()
    start = _normalize_date_bound(start_date)
    end = _normalize_date_bound(end_date)
    if start > end:
        raise ValueError("start_date must be <= end_date")

    items: list[SectorAttributionFactorItem] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        if canonical_attribution_sector_ref(row) != target:
            continue
        day = _calendar_day(row.get("event_time"))
        if day is None or day < start or day > end:
            continue
        item = normalize_attribution_factor_row(row, locale=locale)
        if item is not None:
            items.append(item)

    items.sort(key=lambda item: item.event_time, reverse=True)
    if limit is not None and limit > 0:
        return items[:limit]
    return items


async def build_sector_attribution_factors(
    client: AsyncDojo,
    *,
    market: str,
    sector_id: str,
    start_date: str,
    end_date: str,
    locale: LocaleCode = "zh",
    limit: int | None = None,
) -> SectorAttributionFactorsResponse:
    market_code = _normalize_market(market)
    sector = str(sector_id or "").strip()
    if not sector:
        raise ValueError("sector_id is required")
    if locale not in {"zh", "en"}:
        raise ValueError("locale must be zh or en")

    start = _normalize_date_bound(start_date)
    end = _normalize_date_bound(end_date)

    try:
        # Do not pass limit: SDK time filters are no-ops; fetch market slice then filter locally.
        payload = await client.analysis.get_attribution_factor(market=market_code)
    except Exception:
        LOGGER.exception("Failed to fetch attribution factors from Dojo SDK")
        raise

    rows = [row for row in _unwrap_payload(payload) if isinstance(row, dict)]
    items = filter_attribution_factor_rows(
        rows,
        sector_id=sector,
        start_date=start,
        end_date=end,
        locale=locale,
        limit=limit,
    )
    return SectorAttributionFactorsResponse(
        market=market_code,
        sector_id=sector,
        locale=locale,
        start_date=start,
        end_date=end,
        total_num=len(items),
        items=items,
    )
