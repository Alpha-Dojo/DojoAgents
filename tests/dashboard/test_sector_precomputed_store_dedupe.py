from __future__ import annotations

import pandas as pd

from dojoagents.harnesses.built_in.financial.services.sector_precomputed_store import (
    SectorPrecomputedStore,
    dedupe_constituent_rows,
)


def test_dedupe_constituent_rows_keeps_first_role() -> None:
    rows = dedupe_constituent_rows(
        [
            {"market": "us", "ticker": "NVDA", "role": "secondary", "level3_id": "chip"},
            {"market": "us", "ticker": "NVDA", "role": "primary", "level3_id": "gpu"},
        ]
    )

    assert len(rows) == 1
    assert rows[0]["role"] == "primary"


def test_get_sector_constituents_dedupes_l1_l2_rollups() -> None:
    store = SectorPrecomputedStore()
    store._constituents_df = pd.DataFrame(
        [
            {
                "level1_id": "tech",
                "level2_id": "semi",
                "level3_id": "gpu",
                "market": "us",
                "ticker": "NVDA",
                "role": "primary",
                "market_cap": 100.0,
                "pe": 30.0,
            },
            {
                "level1_id": "tech",
                "level2_id": "semi",
                "level3_id": "chip",
                "market": "us",
                "ticker": "NVDA",
                "role": "secondary",
                "market_cap": 100.0,
                "pe": 30.0,
            },
            {
                "level1_id": "tech",
                "level2_id": "semi",
                "level3_id": "gpu",
                "market": "us",
                "ticker": "AMD",
                "role": "primary",
                "market_cap": 50.0,
                "pe": 25.0,
            },
        ]
    )

    l2_rows = store.get_sector_constituents("tech", "semi", "", market="us")
    assert len(l2_rows) == 2
    assert {row["ticker"] for row in l2_rows} == {"NVDA", "AMD"}
    nvda_l2 = next(row for row in l2_rows if row["ticker"] == "NVDA")
    assert nvda_l2["role"] == "primary"

    l1_rows = store.get_sector_constituents("tech", "", "", market="us")
    assert len(l1_rows) == 2
    assert {row["ticker"] for row in l1_rows} == {"NVDA", "AMD"}

    l3_rows = store.get_sector_constituents("tech", "semi", "gpu", market="us")
    assert len(l3_rows) == 2
    assert {row["ticker"] for row in l3_rows} == {"NVDA", "AMD"}
