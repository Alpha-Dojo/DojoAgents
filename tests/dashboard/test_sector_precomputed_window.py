from __future__ import annotations

import pandas as pd
import pytest

from dojoagents.dashboard.services.market_window import MarketAnalysisWindow
from dojoagents.dashboard.services.sector_precomputed_store import SectorPrecomputedStore


def test_compute_date_range_frame_compounds_in_window_daily_returns() -> None:
    df = pd.DataFrame(
        [
            {"scope": "L3", "level1_id": "1", "level2_id": "1", "level3_id": "1", "market": "us", "trade_date": "2026-01-02", "index_level": 100.0, "daily_return_pct": 1.0},
            {"scope": "L3", "level1_id": "1", "level2_id": "1", "level3_id": "1", "market": "us", "trade_date": "2026-01-03", "index_level": 110.0, "daily_return_pct": 10.0},
            {"scope": "L3", "level1_id": "1", "level2_id": "1", "level3_id": "1", "market": "us", "trade_date": "2026-01-06", "index_level": 121.0, "daily_return_pct": 10.0},
        ]
    )
    frame = SectorPrecomputedStore._compute_date_range_frame(
        df,
        group_cols=["scope", "level1_id", "level2_id", "level3_id", "market"],
        value_col="index_level",
        start_date="2026-01-02",
        end_date="2026-01-06",
    )
    assert len(frame) == 1
    # Compound all three session returns — not last/first index (which would be 21%).
    assert frame.iloc[0]["daily_return_pct"] == pytest.approx(22.21)


def test_get_sector_movers_window_frame_for_window_date_range() -> None:
    store = SectorPrecomputedStore()
    store._sector_daily_df = pd.DataFrame(
        [
            {
                "scope": "L3",
                "level1_id": "1",
                "level2_id": "1",
                "level3_id": "1",
                "market": "us",
                "trade_date": "2026-01-02",
                "index_level": 100.0,
                "daily_return_pct": 10.0,
                "total_market_cap": 100.0,
                "member_count": 2,
            },
            {
                "scope": "L3",
                "level1_id": "1",
                "level2_id": "1",
                "level3_id": "1",
                "market": "us",
                "trade_date": "2026-01-06",
                "index_level": 120.0,
                "daily_return_pct": 9.090909,
                "total_market_cap": 100.0,
                "member_count": 2,
            },
        ]
    )
    window = store.resolve_window_bounds(MarketAnalysisWindow(mode="date_range", start_date="2026-01-02", end_date="2026-01-06"))
    frame = store.get_sector_movers_window_frame_for_window(window)
    assert len(frame) == 1
    assert frame.iloc[0]["daily_return_pct"] == pytest.approx(20.0, rel=1e-3)
    assert window.resolved_start == "2026-01-02"
    assert window.resolved_end == "2026-01-06"


def test_compute_window_frame_compounds_n_session_daily_returns() -> None:
    df = pd.DataFrame(
        [
            {"scope": "L3", "level1_id": "1", "level2_id": "1", "level3_id": "1", "market": "us", "trade_date": "2026-01-02", "index_level": 100.0, "daily_return_pct": 10.0},
            {"scope": "L3", "level1_id": "1", "level2_id": "1", "level3_id": "1", "market": "us", "trade_date": "2026-01-03", "index_level": 110.0, "daily_return_pct": 10.0},
            {"scope": "L3", "level1_id": "1", "level2_id": "1", "level3_id": "1", "market": "us", "trade_date": "2026-01-06", "index_level": 121.0, "daily_return_pct": 10.0},
        ]
    )
    frame = SectorPrecomputedStore._compute_window_frame(
        df,
        group_cols=["scope", "level1_id", "level2_id", "level3_id", "market"],
        value_col="index_level",
        days=3,
    )
    assert len(frame) == 1
    assert frame.iloc[0]["daily_return_pct"] == pytest.approx(33.1)


def test_get_sector_movers_window_frame_as_of_ignores_later_sessions() -> None:
    store = SectorPrecomputedStore()
    store._sector_daily_df = pd.DataFrame(
        [
            {
                "scope": "L3",
                "level1_id": "1",
                "level2_id": "1",
                "level3_id": "1",
                "market": "us",
                "trade_date": "2026-01-02",
                "index_level": 100.0,
                "daily_return_pct": 10.0,
                "total_market_cap": 100.0,
                "member_count": 2,
            },
            {
                "scope": "L3",
                "level1_id": "1",
                "level2_id": "1",
                "level3_id": "1",
                "market": "us",
                "trade_date": "2026-01-06",
                "index_level": 110.0,
                "daily_return_pct": 10.0,
                "total_market_cap": 100.0,
                "member_count": 2,
            },
            {
                "scope": "L3",
                "level1_id": "1",
                "level2_id": "1",
                "level3_id": "1",
                "market": "us",
                "trade_date": "2026-01-07",
                "index_level": 121.0,
                "daily_return_pct": 10.0,
                "total_market_cap": 100.0,
                "member_count": 2,
            },
        ]
    )
    store._ticker_daily_df = pd.DataFrame(
        [
            {"market": "us", "ticker": "AAA", "trade_date": "2026-01-02"},
            {"market": "us", "ticker": "AAA", "trade_date": "2026-01-06"},
            {"market": "us", "ticker": "AAA", "trade_date": "2026-01-07"},
        ]
    )
    window = store.resolve_window_bounds(MarketAnalysisWindow(mode="as_of", days=2, as_of="2026-01-06"))
    frame = store.get_sector_movers_window_frame_for_window(window)
    assert window.resolved_start == "2026-01-02"
    assert window.resolved_end == "2026-01-06"
    assert len(frame) == 1
    assert frame.iloc[0]["daily_return_pct"] == pytest.approx(21.0)
