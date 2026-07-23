from __future__ import annotations

import math

import pandas as pd

from dojoagents.dashboard.services.sector_precomputed_store import SectorPrecomputedStore


def test_compute_window_frame_replaces_invalid_daily_return_pct_with_zero() -> None:
    frame = pd.DataFrame(
        [
            {
                "scope": "L3",
                "level1_id": "1",
                "level2_id": "2",
                "level3_id": "3",
                "market": "us",
                "trade_date": "2026-06-01",
                "index_level": 100.0,
            },
            {
                "scope": "L3",
                "level1_id": "1",
                "level2_id": "2",
                "level3_id": "3",
                "market": "us",
                "trade_date": "2026-06-02",
                "index_level": 100.0,
            },
            {
                "scope": "L3",
                "level1_id": "1",
                "level2_id": "2",
                "level3_id": "3",
                "market": "us",
                "trade_date": "2026-06-03",
                "index_level": float("nan"),
            },
        ]
    )

    result = SectorPrecomputedStore._compute_window_frame(
        frame,
        group_cols=["scope", "level1_id", "level2_id", "level3_id", "market"],
        value_col="index_level",
        days=2,
    )

    assert len(result) == 1
    change = float(result.iloc[0]["daily_return_pct"])
    assert math.isfinite(change)
    assert change == 0.0
