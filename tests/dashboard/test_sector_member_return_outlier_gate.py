from __future__ import annotations

import pandas as pd
import pytest

from dojoagents.dashboard.services.kline_segment import (
    MAX_SECTOR_MEMBER_DAILY_RETURN,
    sector_member_daily_return_usable,
)
from dojoagents.dashboard.services.precompute_sector_daily import _build_index_rows
from dojoagents.dashboard.services.sector_store import ResolvedSectorPath


def test_sector_member_daily_return_usable_is_symmetric() -> None:
    assert sector_member_daily_return_usable(0.50) is True
    assert sector_member_daily_return_usable(-0.50) is True
    assert sector_member_daily_return_usable(0.5000001) is False
    assert sector_member_daily_return_usable(-0.5000001) is False
    assert sector_member_daily_return_usable(4.196) is False  # +419.6% as fraction
    assert sector_member_daily_return_usable(float("nan")) is False
    assert MAX_SECTOR_MEMBER_DAILY_RETURN == pytest.approx(0.50)


def _path() -> ResolvedSectorPath:
    return ResolvedSectorPath(
        level1_id="L1",
        level2_id="L2",
        level3_id="L3",
        level1_zh="一级",
        level1_en="Level1",
        level2_zh="二级",
        level2_en="Level2",
        level3_zh="三级",
        level3_en="Level3",
    )


def test_build_index_rows_excludes_extreme_member_day_and_renormalizes() -> None:
    """Constituents unchanged; outlier return omitted; remaining weights re-normalized."""
    members = pd.DataFrame(
        [
            {"market": "us", "ticker": "SONY", "role": "primary", "market_cap": 80.0, "pe": 20.0},
            {"market": "us", "ticker": "FGIWW", "role": "primary", "market_cap": 20.0, "pe": None},
        ]
    )
    # Percent units in precompute pivot; gate converts via /100 at call site.
    returns_pivot = pd.DataFrame(
        {
            ("us", "SONY"): [5.0],
            ("us", "FGIWW"): [419.6],
        },
        index=["2026-07-28"],
    )
    rows = _build_index_rows(
        scope="L3",
        market="us",
        path=_path(),
        members=members,
        returns_pivot=returns_pivot,
    )
    assert len(rows) == 1
    row = rows[0]
    assert row["daily_return_pct"] == pytest.approx(5.0)
    assert row["member_count"] == 2
    assert row["member_count_with_return"] == 1
    assert row["effective_weight_sum"] == pytest.approx(80.0)
    assert row["total_market_cap"] == pytest.approx(100.0)
    assert row["index_level"] == pytest.approx(105.0)


def test_build_index_rows_excludes_extreme_downside_day() -> None:
    members = pd.DataFrame(
        [
            {"market": "us", "ticker": "A", "role": "primary", "market_cap": 90.0, "pe": 10.0},
            {"market": "us", "ticker": "B", "role": "primary", "market_cap": 10.0, "pe": 10.0},
        ]
    )
    returns_pivot = pd.DataFrame(
        {
            ("us", "A"): [2.0],
            ("us", "B"): [-60.0],
        },
        index=["2026-07-28"],
    )
    rows = _build_index_rows(
        scope="L3",
        market="us",
        path=_path(),
        members=members,
        returns_pivot=returns_pivot,
    )
    assert len(rows) == 1
    assert rows[0]["daily_return_pct"] == pytest.approx(2.0)
    assert rows[0]["member_count_with_return"] == 1
    assert rows[0]["effective_weight_sum"] == pytest.approx(90.0)


def test_build_index_rows_keeps_boundary_50_pct() -> None:
    members = pd.DataFrame(
        [
            {"market": "us", "ticker": "A", "role": "primary", "market_cap": 50.0, "pe": 10.0},
            {"market": "us", "ticker": "B", "role": "primary", "market_cap": 50.0, "pe": 10.0},
        ]
    )
    returns_pivot = pd.DataFrame(
        {
            ("us", "A"): [10.0],
            ("us", "B"): [50.0],
        },
        index=["2026-07-28"],
    )
    rows = _build_index_rows(
        scope="L3",
        market="us",
        path=_path(),
        members=members,
        returns_pivot=returns_pivot,
    )
    assert len(rows) == 1
    assert rows[0]["daily_return_pct"] == pytest.approx(30.0)
    assert rows[0]["member_count_with_return"] == 2
