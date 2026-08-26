from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

_DEFAULT_TIMEZONE = "Asia/Shanghai"


def resolve_timezone_iana(metadata: dict[str, Any] | None) -> str:
    if not isinstance(metadata, dict):
        return _DEFAULT_TIMEZONE
    for key in ("timezone_iana", "client_timezone", "timezone"):
        raw = metadata.get(key)
        if not isinstance(raw, str):
            continue
        candidate = raw.strip()
        if not candidate:
            continue
        try:
            ZoneInfo(candidate)
        except ZoneInfoNotFoundError:
            continue
        return candidate
    return _DEFAULT_TIMEZONE


def build_temporal_context_block(
    metadata: dict[str, Any] | None,
    *,
    now: datetime | None = None,
) -> str:
    utc_now = now or datetime.now(timezone.utc)
    if utc_now.tzinfo is None:
        utc_now = utc_now.replace(tzinfo=timezone.utc)
    else:
        utc_now = utc_now.astimezone(timezone.utc)

    tz_name = resolve_timezone_iana(metadata)
    local_now = utc_now.astimezone(ZoneInfo(tz_name))
    today_date = local_now.date()
    today = today_date.isoformat()
    yesterday = (today_date - timedelta(days=1)).isoformat()
    tomorrow = (today_date + timedelta(days=1)).isoformat()
    weekday = local_now.strftime("%A")
    utc_label = utc_now.replace(microsecond=0).isoformat()
    local_label = local_now.replace(microsecond=0).isoformat()

    return (
        "## Temporal context (authoritative — do not guess)\n"
        f"- Server UTC: {utc_label}\n"
        f"- User local: {local_label} ({tz_name})\n"
        f"- Today (user): {today} ({weekday})\n"
        f"- Yesterday (user): {yesterday}\n"
        f"- Tomorrow (user): {tomorrow}\n"
        "- Date-only events are interpreted in the user's timezone.\n"
        "- \"Today\" means the user-local calendar date, not server UTC or model knowledge.\n"
        "- Interpret 最近 / 近期 / recent / latest relative to the dates above.\n"
        "- For web_search on news or events: use topic/entity keywords only; do NOT add a year "
        "to the query unless the user named a specific year.\n"
        "- After reading search results, use Temporal context to judge freshness. If results look "
        "stale, say so and broaden or refine the query — do NOT fix staleness by swapping in a "
        "guessed year."
    )
