from __future__ import annotations

import math

import pandas as pd
import pytest

from dojoagents.dashboard.services.precompute_ticker_alpha_factors import (
    RESEARCH_ONLY_LEAKAGE_RISK,
    TICKER_ALPHA_FACTORS_COLUMNS,
    TICKER_ALPHA_FACTORS_RULE,
    compute_ticker_alpha_factors_frame,
    ticker_factor_dictionary,
)


def test_ticker_factor_dictionary_and_leakage_flags() -> None:
    assert "s_mom_ret_5d" in RESEARCH_ONLY_LEAKAGE_RISK
    assert "s_mom_reversal_1d" in RESEARCH_ONLY_LEAKAGE_RISK
    names = {row["name"] for row in ticker_factor_dictionary()}
    assert "s_rs_vs_sector_20d" in names
    assert "m_rs_vs_sector_60d" in names
    assert "s_val_pe_cheap_cs" in names
    assert all(row["name"] in TICKER_ALPHA_FACTORS_COLUMNS for row in ticker_factor_dictionary())


def test_compute_ticker_alpha_factors_frame_basic() -> None:
    dates = [f"2026-07-{d:02d}" for d in range(1, 26)]
    rows = []
    close_a = 100.0
    close_b = 50.0
    for i, d in enumerate(dates):
        # AAA drifts up ~1%/day; BBB drifts down ~0.5%/day
        ret_a = 1.0
        ret_b = -0.5
        close_a *= 1.0 + ret_a / 100.0
        close_b *= 1.0 + ret_b / 100.0
        rows.append(
            {
                "market": "us",
                "ticker": "AAA",
                "trade_date": d,
                "close": close_a,
                "daily_return_pct": ret_a,
                "cumulative_return_pct": (close_a / 100.0 - 1.0) * 100.0,
            }
        )
        rows.append(
            {
                "market": "us",
                "ticker": "BBB",
                "trade_date": d,
                "close": close_b,
                "daily_return_pct": ret_b,
                "cumulative_return_pct": (close_b / 50.0 - 1.0) * 100.0,
            }
        )
    ticker_daily = pd.DataFrame(rows)
    constituents = pd.DataFrame(
        [
            {
                "market": "us",
                "ticker": "AAA",
                "level1_id": "1",
                "level2_id": "2",
                "level3_id": "A",
                "role": "primary",
                "market_cap": 80.0,
                "pe": 10.0,
            },
            {
                "market": "us",
                "ticker": "BBB",
                "level1_id": "1",
                "level2_id": "2",
                "level3_id": "A",
                "role": "primary",
                "market_cap": 20.0,
                "pe": 30.0,
            },
        ]
    )
    benchmark = pd.DataFrame(
        [{"market": "us", "trade_date": d, "daily_return_pct": 0.2, "close": 100.0 + i} for i, d in enumerate(dates)]
    )
    sector_rows = []
    sec_close = 100.0
    for d in dates:
        sec_close *= 1.005
        sector_rows.append(
            {
                "trade_date": d,
                "market": "us",
                "scope": "L3",
                "level1_id": "1",
                "level2_id": "2",
                "level3_id": "A",
                "daily_return_pct": 0.5,
                "close": sec_close,
            }
        )
    sector_daily = pd.DataFrame(sector_rows)

    out = compute_ticker_alpha_factors_frame(
        ticker_daily=ticker_daily,
        constituents=constituents,
        benchmark_daily=benchmark,
        sector_daily=sector_daily,
    )
    assert list(out.columns) == TICKER_ALPHA_FACTORS_COLUMNS
    assert not out.duplicated(subset=["trade_date", "market", "ticker"]).any()
    assert set(out["factor_rule"].unique()) == {TICKER_ALPHA_FACTORS_RULE}

    last = out[out["trade_date"] == dates[-1]].set_index("ticker")
    assert last.loc["AAA", "row_status"] == "ok"
    assert last.loc["AAA", "s_mom_ret_5d"] == pytest.approx(((1.01**5) - 1.0) * 100.0, rel=1e-3)
    assert last.loc["AAA", "s_mom_reversal_1d"] == pytest.approx(-1.0)
    assert last.loc["AAA", "s_mom_up_streak"] == pytest.approx(25.0)
    assert last.loc["BBB", "s_mom_down_streak"] == pytest.approx(25.0)
    assert float(last.loc["AAA", "s_rs_20d"]) > float(last.loc["BBB", "s_rs_20d"])
    assert float(last.loc["AAA", "s_rs_vs_sector_20d"]) > float(last.loc["BBB", "s_rs_vs_sector_20d"])
    # Lower PE → higher cheap score
    assert float(last.loc["AAA", "s_val_pe_cheap_cs"]) > float(last.loc["BBB", "s_val_pe_cheap_cs"])
    assert math.isfinite(float(last.loc["AAA", "s_size_log_cap"]))
    # 25 days < mid min_periods for 60d → NaN expected
    assert pd.isna(last.loc["AAA", "m_mom_ret_60d"])
