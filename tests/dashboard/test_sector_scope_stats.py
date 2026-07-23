from __future__ import annotations

import pytest

from dojoagents.dashboard.services.sector_scope_stats import _compute_sector_scope_metrics_sync
from dojoagents.dashboard.services.sector_store import ResolvedSectorPath


class _FakePrecomputedStore:
    def __init__(self, rows: list[dict]) -> None:
        self._rows = rows

    def get_sector_daily(
        self,
        scope: str,
        level1_id: str,
        level2_id: str,
        level3_id: str,
        market: str | None = None,
    ) -> list[dict]:
        matched = [row for row in self._rows if row["scope"] == scope and row["level1_id"] == level1_id and row["market"] == market]
        if scope in ("L2", "L3"):
            matched = [row for row in matched if row["level2_id"] == level2_id]
        if scope == "L3":
            matched = [row for row in matched if row["level3_id"] == level3_id]
        return matched


@pytest.mark.parametrize("level", ("L1", "L2", "L3"))
def test_compute_sector_scope_metrics_reads_latest_sector_daily_row(level: str) -> None:
    path = ResolvedSectorPath(
        level1_id="1",
        level2_id="13",
        level3_id="17",
        level1_zh="L1",
        level1_en="L1",
        level2_zh="L2",
        level2_en="L2",
        level3_zh="L3",
        level3_en="L3",
    )
    store = _FakePrecomputedStore(
        [
            {
                "trade_date": "2026-06-18",
                "scope": level,
                "market": "us",
                "level1_id": "1",
                "level2_id": "13" if level in ("L2", "L3") else "",
                "level3_id": "17" if level == "L3" else "",
                "member_count": 10,
                "total_market_cap": 1000.0,
                "weighted_pe": 21.5,
            },
            {
                "trade_date": "2026-06-20",
                "scope": level,
                "market": "us",
                "level1_id": "1",
                "level2_id": "13" if level in ("L2", "L3") else "",
                "level3_id": "17" if level == "L3" else "",
                "member_count": 12,
                "total_market_cap": 1200.0,
                "weighted_pe": 22.1,
            },
        ]
    )

    response = _compute_sector_scope_metrics_sync(store, path)
    stats = response.scopes[level]["us"]
    assert stats.member_count == 12
    assert stats.total_market_cap == 1200.0
    assert stats.weighted_pe == 22.1
