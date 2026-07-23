from __future__ import annotations

import pandas as pd
import pytest

from dojoagents.harnesses.built_in.financial.services.market_window import MarketAnalysisWindow
from dojoagents.harnesses.built_in.financial.pipelines.precompute_sector_daily import (
    PrecomputeInputSnapshot,
    compute_sector_precomputed_frames,
)
from dojoagents.harnesses.built_in.financial.services.sector_precomputed_store import SectorPrecomputedStore
from dojoagents.harnesses.built_in.financial.services.sector_return_coverage import (
    filter_usable_sector_daily_rows,
    resolve_market_as_of_by_market,
    sector_day_return_coverage_ok,
)


def test_sector_day_return_coverage_rejects_single_micro_cap_session() -> None:
    # XR wearables regression: 1/16 names, ~$2M of $6.6T cap.
    assert not sector_day_return_coverage_ok(
        member_count=16,
        member_count_with_return=1,
        total_market_cap=6_598_121_000_000,
        effective_weight_sum=2_212_076,
    )


def test_sector_day_return_coverage_accepts_broad_session() -> None:
    assert sector_day_return_coverage_ok(
        member_count=16,
        member_count_with_return=15,
        total_market_cap=6_598_121_000_000,
        effective_weight_sum=6_598_120_000_000,
    )


def test_resolve_market_as_of_ignores_trailing_sparse_date() -> None:
    ticker_daily = pd.DataFrame(
        [
            {"market": "us", "ticker": "AAPL", "trade_date": "2026-07-15"},
            {"market": "us", "ticker": "AAPL", "trade_date": "2026-07-16"},
            {"market": "us", "ticker": "META", "trade_date": "2026-07-15"},
            {"market": "us", "ticker": "META", "trade_date": "2026-07-16"},
            {"market": "us", "ticker": "SOBR", "trade_date": "2026-07-15"},
            {"market": "us", "ticker": "SOBR", "trade_date": "2026-07-16"},
            {"market": "us", "ticker": "SOBR", "trade_date": "2026-07-17"},
        ]
    )
    assert resolve_market_as_of_by_market(ticker_daily)["us"] == "2026-07-16"


def test_filter_usable_sector_daily_rows_drops_sparse_prints() -> None:
    df = pd.DataFrame(
        [
            {
                "market": "us",
                "trade_date": "2026-07-16",
                "member_count": 16,
                "member_count_with_return": 15,
                "total_market_cap": 1000.0,
                "effective_weight_sum": 900.0,
                "daily_return_pct": 0.72,
            },
            {
                "market": "us",
                "trade_date": "2026-07-17",
                "member_count": 16,
                "member_count_with_return": 1,
                "total_market_cap": 1000.0,
                "effective_weight_sum": 1.0,
                "daily_return_pct": -23.1,
            },
        ]
    )
    filtered = filter_usable_sector_daily_rows(df)
    assert list(filtered["trade_date"]) == ["2026-07-16"]
    assert float(filtered.iloc[0]["daily_return_pct"]) == pytest.approx(0.72)


def test_movers_window_aligns_to_market_as_of_not_sparse_trailing_bar() -> None:
    store = SectorPrecomputedStore()
    store._sector_daily_df = pd.DataFrame(
        [
            {
                "scope": "L3",
                "level1_id": "1",
                "level2_id": "13",
                "level3_id": "16",
                "market": "us",
                "trade_date": "2026-07-16",
                "index_level": 133.0,
                "daily_return_pct": 0.72,
                "member_count": 16,
                "member_count_with_return": 15,
                "total_market_cap": 1000.0,
                "effective_weight_sum": 900.0,
            },
            {
                "scope": "L3",
                "level1_id": "1",
                "level2_id": "13",
                "level3_id": "16",
                "market": "us",
                "trade_date": "2026-07-17",
                "index_level": 102.0,
                "daily_return_pct": -23.1,
                "member_count": 16,
                "member_count_with_return": 1,
                "total_market_cap": 1000.0,
                "effective_weight_sum": 1.0,
            },
        ]
    )
    store._ticker_daily_df = pd.DataFrame(
        [
            {"market": "us", "ticker": "AAPL", "trade_date": "2026-07-16", "close": 333.0, "daily_return_pct": 1.76},
            {"market": "us", "ticker": "META", "trade_date": "2026-07-16", "close": 664.0, "daily_return_pct": -2.46},
            {"market": "us", "ticker": "SOBR", "trade_date": "2026-07-16", "close": 1.0, "daily_return_pct": -51.69},
            {"market": "us", "ticker": "SOBR", "trade_date": "2026-07-17", "close": 0.77, "daily_return_pct": -23.1},
        ]
    )
    store._rebuild_indexes_locked()

    sector_frame = store.get_sector_movers_window_frame_for_window(
        MarketAnalysisWindow(mode="days", days=1),
    )
    assert len(sector_frame) == 1
    assert sector_frame.iloc[0]["trade_date"] == "2026-07-16"
    assert float(sector_frame.iloc[0]["daily_return_pct"]) == pytest.approx(0.72)

    ticker_frame = store.get_ticker_daily_window_frame_for_window(
        MarketAnalysisWindow(mode="days", days=1),
    )
    assert set(ticker_frame["trade_date"]) == {"2026-07-16"}
    assert "2026-07-17" not in set(ticker_frame["trade_date"])
    aapl = ticker_frame[ticker_frame["ticker"] == "AAPL"].iloc[0]
    assert float(aapl["daily_return_pct"]) == pytest.approx(1.76)


def test_precompute_skips_sparse_sector_day() -> None:
    snapshot = PrecomputeInputSnapshot(
        start_date="2026-07-16",
        end_date="2026-07-17",
        generated_at="2026-07-17T00:00:00+00:00",
        constituents=[
            {
                "level1_id": "1",
                "level2_id": "13",
                "level3_id": "16",
                "market": "us",
                "ticker": "AAPL",
                "role": "secondary",
                "market_cap": 900.0,
                "pe": 20.0,
            },
            {
                "level1_id": "1",
                "level2_id": "13",
                "level3_id": "16",
                "market": "us",
                "ticker": "SOBR",
                "role": "secondary",
                "market_cap": 1.0,
                "pe": None,
            },
        ],
        ticker_daily_rows=[
            {"market": "us", "ticker": "AAPL", "trade_date": "2026-07-15", "close": 100.0},
            {"market": "us", "ticker": "AAPL", "trade_date": "2026-07-16", "close": 101.0},
            {"market": "us", "ticker": "SOBR", "trade_date": "2026-07-15", "close": 1.0},
            {"market": "us", "ticker": "SOBR", "trade_date": "2026-07-16", "close": 0.9},
            {"market": "us", "ticker": "SOBR", "trade_date": "2026-07-17", "close": 0.7},
        ],
        stats={},
    )
    _constituents, _ticker_daily, sector_daily, _manifest = compute_sector_precomputed_frames(snapshot)
    us_l3 = sector_daily[(sector_daily["scope"] == "L3") & (sector_daily["market"] == "us") & (sector_daily["level3_id"] == "16")]
    assert list(us_l3["trade_date"]) == ["2026-07-16"]
    # Cap-weighted: (900*1% + 1*(-10%)) / 901 ≈ 0.9878%
    assert float(us_l3.iloc[0]["daily_return_pct"]) == pytest.approx((900 * 1.0 + 1 * (-10.0)) / 901, abs=1e-3)
