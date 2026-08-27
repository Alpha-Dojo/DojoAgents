from __future__ import annotations

from types import SimpleNamespace

import pytest

from dojoagents.dashboard.services.domain_api import build_sector_return_curve_v1
from dojoagents.dashboard.services.sector_store import ResolvedSectorPath


@pytest.mark.asyncio
async def test_build_sector_return_curve_rebases_nav_and_clips_window() -> None:
    path = ResolvedSectorPath(
        level1_id="1",
        level2_id="2",
        level3_id="3",
        level1_zh="",
        level1_en="",
        level2_zh="",
        level2_en="",
        level3_zh="",
        level3_en="",
    )
    store = SimpleNamespace(
        get_sector_daily=lambda **_kwargs: [
            {
                "trade_date": "2026-01-01",
                "index_level": 100.0,
                "daily_return_pct": 0.0,
                "total_market_cap": 1e10,
                "weighted_pe": 20.0,
                "member_count": 10,
            },
            {
                "trade_date": "2026-01-02",
                "index_level": 110.0,
                "daily_return_pct": 10.0,
                "total_market_cap": 1.1e10,
                "weighted_pe": 21.0,
                "member_count": 10,
            },
            {
                "trade_date": "2026-01-03",
                "index_level": 121.0,
                "daily_return_pct": 10.0,
                "total_market_cap": 1.2e10,
                "weighted_pe": 22.0,
                "member_count": 11,
            },
            {
                "trade_date": "2026-01-10",
                "index_level": 130.0,
                "daily_return_pct": 7.0,
                "total_market_cap": 1.3e10,
                "weighted_pe": 23.0,
                "member_count": 11,
            },
        ]
    )
    registry = SimpleNamespace(
        sector_store=SimpleNamespace(find_resolved_path=lambda *_a, **_k: path),
        sector_precomputed_store=store,
    )

    result = await build_sector_return_curve_v1(
        registry,
        level1_id="1",
        level2_id="2",
        level3_id="3",
        market="us",
        start_date="2026-01-02",
        end_date="2026-01-03",
        scope="L3",
    )

    assert result.market == "us"
    assert result.window_start == "2026-01-02"
    assert result.window_end == "2026-01-03"
    assert result.cumulative_return_pct == pytest.approx(21.0)
    assert [point.date for point in result.points] == ["2026-01-02", "2026-01-03"]
    assert result.points[0].nav == pytest.approx(1.0)
    assert result.points[1].nav == pytest.approx(1.1)
    assert result.points[1].daily_return_pct == pytest.approx(10.0)
    assert result.points[1].member_count == 11


@pytest.mark.asyncio
async def test_build_sector_return_curve_as_of_days_compounds_and_falls_back() -> None:
    path = ResolvedSectorPath(
        level1_id="1",
        level2_id="2",
        level3_id="3",
        level1_zh="",
        level1_en="",
        level2_zh="",
        level2_en="",
        level3_zh="",
        level3_en="",
    )
    store = SimpleNamespace(
        get_sector_daily=lambda **_kwargs: [
            {
                "trade_date": "2026-01-02",
                "index_level": 100.0,
                "daily_return_pct": 10.0,
                "total_market_cap": 1e10,
                "weighted_pe": 20.0,
                "member_count": 10,
            },
            {
                "trade_date": "2026-01-05",
                "index_level": 110.0,
                "daily_return_pct": 10.0,
                "total_market_cap": 1.1e10,
                "weighted_pe": 21.0,
                "member_count": 10,
            },
            {
                "trade_date": "2026-01-06",
                "index_level": 121.0,
                "daily_return_pct": 10.0,
                "total_market_cap": 1.2e10,
                "weighted_pe": 22.0,
                "member_count": 11,
            },
        ]
    )
    registry = SimpleNamespace(
        sector_store=SimpleNamespace(find_resolved_path=lambda *_a, **_k: path),
        sector_precomputed_store=store,
    )

    result = await build_sector_return_curve_v1(
        registry,
        level1_id="1",
        level2_id="2",
        level3_id="3",
        market="us",
        as_of="2026-01-04",
        days=2,
        scope="L3",
    )

    assert result.window_mode == "as_of"
    assert result.as_of == "2026-01-04"
    assert result.days == 2
    assert result.window_start == "2026-01-02"
    assert result.window_end == "2026-01-02"
    assert [point.date for point in result.points] == ["2026-01-02"]
    assert result.cumulative_return_pct == pytest.approx(10.0)


@pytest.mark.asyncio
async def test_build_sector_return_curve_as_of_days_compounds_last_sessions() -> None:
    path = ResolvedSectorPath(
        level1_id="1",
        level2_id="2",
        level3_id="3",
        level1_zh="",
        level1_en="",
        level2_zh="",
        level2_en="",
        level3_zh="",
        level3_en="",
    )
    store = SimpleNamespace(
        get_sector_daily=lambda **_kwargs: [
            {
                "trade_date": "2026-01-02",
                "index_level": 100.0,
                "daily_return_pct": 10.0,
                "total_market_cap": 1e10,
                "weighted_pe": 20.0,
                "member_count": 10,
            },
            {
                "trade_date": "2026-01-05",
                "index_level": 110.0,
                "daily_return_pct": 10.0,
                "total_market_cap": 1.1e10,
                "weighted_pe": 21.0,
                "member_count": 10,
            },
            {
                "trade_date": "2026-01-06",
                "index_level": 121.0,
                "daily_return_pct": 10.0,
                "total_market_cap": 1.2e10,
                "weighted_pe": 22.0,
                "member_count": 11,
            },
        ]
    )
    registry = SimpleNamespace(
        sector_store=SimpleNamespace(find_resolved_path=lambda *_a, **_k: path),
        sector_precomputed_store=store,
    )

    result = await build_sector_return_curve_v1(
        registry,
        level1_id="1",
        level2_id="2",
        level3_id="3",
        market="us",
        as_of="2026-01-06",
        days=3,
        scope="L3",
    )

    assert result.window_start == "2026-01-02"
    assert result.window_end == "2026-01-06"
    assert result.cumulative_return_pct == pytest.approx(33.1)
    assert [point.date for point in result.points] == ["2026-01-02", "2026-01-05", "2026-01-06"]


@pytest.mark.asyncio
async def test_build_sector_return_curve_rejects_oversized_window() -> None:
    path = ResolvedSectorPath(
        level1_id="1",
        level2_id="2",
        level3_id="3",
        level1_zh="",
        level1_en="",
        level2_zh="",
        level2_en="",
        level3_zh="",
        level3_en="",
    )
    registry = SimpleNamespace(
        sector_store=SimpleNamespace(find_resolved_path=lambda *_a, **_k: path),
        sector_precomputed_store=SimpleNamespace(get_sector_daily=lambda **_k: []),
    )

    with pytest.raises(ValueError, match="maximum is 400"):
        await build_sector_return_curve_v1(
            registry,
            level1_id="1",
            level2_id="2",
            level3_id="3",
            market="cn",
            start_date="2025-01-01",
            end_date="2026-06-01",
            scope="L3",
        )
