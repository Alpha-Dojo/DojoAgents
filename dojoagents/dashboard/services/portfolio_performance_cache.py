from __future__ import annotations

import hashlib
import json
from typing import Any, Optional

from dojoagents.dashboard.schemas.portfolio import PortfolioPerformanceView


def portfolio_content_fingerprint(raw: dict[str, Any]) -> str:
    payload = {
        "updated_at": raw.get("updated_at"),
        "config": raw.get("config"),
        "orders": raw.get("orders"),
        "candidates": [
            {"ticker": row.get("ticker"), "market": row.get("market")}
            for row in (raw.get("candidates") or [])
            if isinstance(row, dict)
        ],
    }
    blob = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def performance_cache_key(
    *,
    portfolio_id: str,
    fingerprint: str,
    start_date: str,
    benchmark_by_market: dict[str, str],
    market_data_revision: str,
) -> str:
    benchmarks = json.dumps(sorted(benchmark_by_market.items()), sort_keys=True)
    return f"{portfolio_id}:{fingerprint}:{start_date}:{benchmarks}:{market_data_revision}"


class PortfolioPerformanceCache:
    def __init__(self, max_entries: int = 128) -> None:
        self._entries: dict[str, PortfolioPerformanceView] = {}
        self._max_entries = max_entries

    def get(self, key: str) -> Optional[PortfolioPerformanceView]:
        return self._entries.get(key)

    def set(self, key: str, value: PortfolioPerformanceView) -> None:
        if key not in self._entries and len(self._entries) >= self._max_entries:
            oldest = next(iter(self._entries))
            del self._entries[oldest]
        self._entries[key] = value

    def clear(self, portfolio_id: str | None = None) -> None:
        if portfolio_id is None:
            self._entries.clear()
            return
        prefix = f"{portfolio_id}:"
        for key in list(self._entries):
            if key.startswith(prefix):
                del self._entries[key]
