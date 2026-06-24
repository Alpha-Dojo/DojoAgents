from __future__ import annotations

import math
from typing import Any


def compute_log_returns(rows: list[dict[str, Any]], *, max_abs_return: float = 0.5) -> dict[str, float]:
    accepted_close: float | None = None
    result: dict[str, float] = {}
    for row in sorted(rows, key=lambda item: str(item.get("date") or item.get("bar_time") or "")):
        day = str(row.get("date") or row.get("bar_time") or "")[:10]
        try:
            close = float(row.get("close") or 0)
            volume = float(row.get("volume") or row.get("vol") or 0)
        except (TypeError, ValueError):
            continue
        if not day or close <= 0 or volume <= 0:
            continue
        if accepted_close is None:
            accepted_close = close
            continue
        value = math.log(close / accepted_close)
        if not math.isfinite(value) or abs(value) > max_abs_return:
            continue
        result[day] = value
        accepted_close = close
    return result


def compute_weighted_sector_metrics(members: list[dict[str, Any]]) -> dict[str, Any]:
    valid_returns = []
    valid_pe = []
    for member in members:
        try:
            cap = float(member.get("market_cap") or 0)
            log_return = float(member.get("log_return") or 0)
            pe = float(member.get("pe") or 0)
        except (TypeError, ValueError):
            continue
        if cap <= 0:
            continue
        if math.isfinite(log_return):
            valid_returns.append((cap, log_return))
        if pe > 0 and math.isfinite(pe):
            valid_pe.append((cap, pe))

    def weighted(rows: list[tuple[float, float]]) -> float | None:
        total = sum(weight for weight, _ in rows)
        if total <= 0:
            return None
        return sum(weight * value for weight, value in rows) / total

    return {
        "weighted_log_return": weighted(valid_returns),
        "weighted_pe": weighted(valid_pe),
        "return_member_count": len(valid_returns),
        "pe_member_count": len(valid_pe),
    }


def merge_daily_rows(existing: list[dict[str, Any]], incoming: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_date = {str(row.get("date")): dict(row) for row in [*existing, *incoming] if isinstance(row, dict) and row.get("date")}
    return [by_date[day] for day in sorted(by_date)]
