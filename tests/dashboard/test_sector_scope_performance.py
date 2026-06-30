from __future__ import annotations

from types import SimpleNamespace

import pytest

from dojoagents.dashboard.services.precompute_sector_daily import DATA_START_DATE
from dojoagents.dashboard.services.sector_scope_performance import compute_sector_scope_performance


class _FakePrecomputedStore:
    def __init__(self, rows: list[dict]) -> None:
        self._rows = rows

    def get_sector_daily(
        self,
        *,
        scope: str,
        level1_id: str,
        level2_id: str,
        level3_id: str,
        market: str | None = None,
    ) -> list[dict]:
        result = []
        for row in self._rows:
            if row["scope"] != scope or row["level1_id"] != level1_id:
                continue
            if scope in ("L2", "L3") and row["level2_id"] != level2_id:
                continue
            if scope == "L3" and row["level3_id"] != level3_id:
                continue
            if market is not None and row["market"] != market:
                continue
            result.append(row)
        return result

    def get_sector_constituents(
        self,
        *,
        level1_id: str,
        level2_id: str,
        level3_id: str,
        market: str | None = None,
    ) -> list[dict]:
        del level1_id, level2_id, level3_id, market
        return []


class _StubStockStore:
    def find_market(self, ticker: str) -> str | None:
        del ticker
        return None

    def get(self, market: str, ticker: str):
        del market, ticker
        return None


class _StubKlineStore:
    async def get_klines(self, symbols: list[str]):
        del symbols
        return SimpleNamespace(items={})


@pytest.mark.asyncio
async def test_compute_sector_scope_performance_anchors_at_data_start_date() -> None:
    path = SimpleNamespace(level1_id="1", level2_id="2", level3_id="6")
    store = _FakePrecomputedStore(
        [
            {
                "scope": "L3",
                "level1_id": "1",
                "level2_id": "2",
                "level3_id": "6",
                "market": "us",
                "trade_date": "2024-12-30",
                "index_level": 90.0,
                "member_count": 40,
            },
            {
                "scope": "L3",
                "level1_id": "1",
                "level2_id": "2",
                "level3_id": "6",
                "market": "us",
                "trade_date": "2025-01-02",
                "index_level": 100.0,
                "member_count": 46,
            },
            {
                "scope": "L3",
                "level1_id": "1",
                "level2_id": "2",
                "level3_id": "6",
                "market": "us",
                "trade_date": "2026-06-21",
                "index_level": 112.5,
                "member_count": 47,
            },
            {
                "scope": "L3",
                "level1_id": "1",
                "level2_id": "2",
                "level3_id": "6",
                "market": "sh",
                "trade_date": "2025-01-02",
                "index_level": 100.0,
                "member_count": 148,
            },
            {
                "scope": "L3",
                "level1_id": "1",
                "level2_id": "2",
                "level3_id": "6",
                "market": "sh",
                "trade_date": "2026-06-21",
                "index_level": 105.0,
                "member_count": 148,
            },
        ]
    )

    response = await compute_sector_scope_performance(
        _StubStockStore(),
        _StubKlineStore(),
        store,
        path,
        scope="L3",
    )

    assert response.window_start == DATA_START_DATE
    assert response.series_by_market["us"][0].date == "2025-01-02"
    assert response.members_by_market["us"] == 47
    assert response.members_by_market["sh"] == 148
    assert response.series_by_market["us"][-1].value == 112.5
    assert response.series_by_market["us"][-1].date == "2026-06-21"
