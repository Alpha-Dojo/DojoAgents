from __future__ import annotations

import math

import pytest

from dojoagents.dashboard.services.sector_performance_cache import SectorPerformanceCache
from dojoagents.dashboard.services.sector_performance_precompute import (
    compute_log_returns,
    compute_weighted_sector_metrics,
    merge_daily_rows,
)


@pytest.mark.asyncio
async def test_sector_cache_hit_does_not_recompute(tmp_path) -> None:
    cache = SectorPerformanceCache(tmp_path, schema_version=2)
    key = "L3/1/2/3/us"
    await cache.put(
        key,
        {"points": [{"date": "2026-06-20", "value": 101}]},
        as_of="2026-06-20",
        source="computed",
    )
    called = False

    async def compute():
        nonlocal called
        called = True
        return {"points": []}

    result = await cache.get_or_compute(key, compute)

    assert result["payload"]["points"][0]["value"] == 101
    assert result["as_of"] == "2026-06-20"
    assert result["source"] == "dashboard_cache"
    assert called is False


def test_log_returns_filter_no_trade_and_extreme_moves() -> None:
    rows = [
        {"date": "2026-06-17", "close": 100, "volume": 10},
        {"date": "2026-06-18", "close": 110, "volume": 10},
        {"date": "2026-06-19", "close": 200, "volume": 10},
        {"date": "2026-06-20", "close": 210, "volume": 0},
        {"date": "2026-06-21", "close": 121, "volume": 10},
    ]

    returns = compute_log_returns(rows, max_abs_return=0.5)

    assert list(returns) == ["2026-06-18", "2026-06-21"]
    assert returns["2026-06-18"] == pytest.approx(math.log(1.1))


def test_weighted_metrics_keep_negative_pe_member_out_of_pe_only() -> None:
    metrics = compute_weighted_sector_metrics(
        [
            {"market_cap": 100, "pe": 10, "log_return": 0.01},
            {"market_cap": 300, "pe": -5, "log_return": 0.03},
            {"market_cap": 0, "pe": 20, "log_return": 9},
        ]
    )

    assert metrics["weighted_log_return"] == pytest.approx(0.025)
    assert metrics["weighted_pe"] == pytest.approx(10)
    assert metrics["return_member_count"] == 2
    assert metrics["pe_member_count"] == 1


def test_incremental_merge_replaces_same_day_and_sorts() -> None:
    merged = merge_daily_rows(
        [{"date": "2026-06-20", "value": 100}],
        [
            {"date": "2026-06-19", "value": 99},
            {"date": "2026-06-20", "value": 101},
        ],
    )

    assert merged == [
        {"date": "2026-06-19", "value": 99},
        {"date": "2026-06-20", "value": 101},
    ]
