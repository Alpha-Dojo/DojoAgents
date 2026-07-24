from __future__ import annotations

import math

import pandas as pd
import pytest

from dojoagents.dashboard.jobs.precompute.sector_alpha_factors import (
    RESEARCH_ONLY_LEAKAGE_RISK,
    SECTOR_ALPHA_FACTORS_COLUMNS,
    compute_cap_hhi_by_sector,
    compute_sector_alpha_factors_frame,
    factor_dictionary,
    rank_to_inv_score,
)


def test_rank_to_inv_score_and_leakage_flags() -> None:
    assert rank_to_inv_score(1, 5) == pytest.approx(100.0)
    assert rank_to_inv_score(5, 5) == pytest.approx(0.0)
    assert "s_mom_ret_5d" in RESEARCH_ONLY_LEAKAGE_RISK
    names = {row["name"] for row in factor_dictionary()}
    assert "s_mom_ret_5d" in names
    assert "s_struct_leader_conc" in names
    assert "m_struct_hhi_cap" in names


def test_cap_hhi_and_alpha_frame_with_structure() -> None:
    constituents = pd.DataFrame(
        [
            {
                "level1_id": "1",
                "level2_id": "2",
                "level3_id": "A",
                "market": "us",
                "ticker": "AAA",
                "role": "primary",
                "market_cap": 70.0,
                "pe": 10.0,
            },
            {
                "level1_id": "1",
                "level2_id": "2",
                "level3_id": "A",
                "market": "us",
                "ticker": "BBB",
                "role": "primary",
                "market_cap": 30.0,
                "pe": 12.0,
            },
        ]
    )
    hhi = compute_cap_hhi_by_sector(constituents)
    assert float(hhi.iloc[0]["m_struct_hhi_cap"]) == pytest.approx(0.7**2 + 0.3**2)

    theme = pd.DataFrame(
        [
            {
                "trade_date": "2026-07-20",
                "market": "us",
                "scope": "L3",
                "level1_id": "1",
                "level2_id": "2",
                "level3_id": "A",
                "link_key": "theme-a",
                "eligible_count": 2,
                "row_status": "ok",
                "breadth_score": 55.0,
                "advancers_pct": 50.0,
                "volume_expansion_pct": 40.0,
                "new_highs_pct": 10.0,
                "return_5d_pct": 2.0,
                "return_10d_pct": 3.0,
                "return_20d_pct": 5.0,
                "risk_adjusted_5d": 0.4,
                "risk_adjusted_10d": 0.5,
                "risk_adjusted_20d": 0.6,
                "volatility_20d_pct": 12.0,
                "up_streak_days": 2,
                "down_streak_days": 0,
                "relative_strength_5d": 1.0,
                "relative_strength_10d": 1.5,
                "relative_strength_20d": 2.0,
                "rs_rank_5d": 1,
                "rs_rank_universe_size": 2,
                "rotation_score": 1.2,
                "confirmation_score": 100.0,
                "industry_revenue_yoy_pct": 12.0,
                "industry_revenue_accel_pp": 1.0,
                "revenue_improvers_pct": 60.0,
                "industry_net_profit_yoy_pct": 15.0,
                "profit_improvers_pct": 55.0,
                "industry_net_margin_pct": 8.0,
                "industry_net_margin_change_pp": 0.5,
                "stage_hint": "expanding",
            }
        ]
    )
    horizon = pd.DataFrame(
        [
            {
                "trade_date": "2026-07-20",
                "market": "us",
                "scope": "L3",
                "level1_id": "1",
                "level2_id": "2",
                "level3_id": "A",
                "link_key": "theme-a",
                "return_60d_pct": 10.0,
                "return_120d_pct": 20.0,
                "return_252d_pct": 30.0,
                "relative_strength_60d": 4.0,
                "relative_strength_120d": 5.0,
                "relative_strength_252d": 6.0,
                "risk_adjusted_60d": 0.7,
                "risk_adjusted_120d": 0.8,
                "risk_adjusted_252d": 0.9,
                "volatility_60d_pct": 15.0,
                "volatility_120d_pct": 18.0,
                "volatility_252d_pct": 20.0,
                "max_drawdown_60d_pct": -8.0,
                "max_drawdown_120d_pct": -12.0,
                "max_drawdown_252d_pct": -20.0,
                "weighted_pe": 22.0,
                "pe_percentile_cross_section": 40.0,
                "pe_percentile_trailing_252d": 30.0,
                "industry_revenue_yoy_pct": 12.0,
                "industry_net_profit_yoy_pct": 15.0,
                "industry_net_margin_pct": 8.0,
                "revenue_yoy_avg_4q_pct": 11.0,
                "revenue_yoy_positive_streak": 3,
                "stage_hint": "expanding",
                "row_status": "ok",
            }
        ]
    )
    ticker_daily = pd.DataFrame(
        [
            {
                "market": "us",
                "ticker": "AAA",
                "trade_date": "2026-07-20",
                "close": 10.0,
                "daily_return_pct": 3.0,
                "cumulative_return_pct": 3.0,
            },
            {
                "market": "us",
                "ticker": "BBB",
                "trade_date": "2026-07-20",
                "close": 20.0,
                "daily_return_pct": -1.0,
                "cumulative_return_pct": -1.0,
            },
        ]
    )
    sector_daily = pd.DataFrame(
        [
            {
                "trade_date": "2026-07-20",
                "scope": "L3",
                "market": "us",
                "level1_id": "1",
                "level2_id": "2",
                "level3_id": "A",
                "member_count": 2,
                "member_count_with_return": 2,
                "total_market_cap": 100.0,
                "effective_weight_sum": 1.0,
                "weighted_pe": 22.0,
                "index_level": 100.0,
                "daily_return_pct": 1.8,
            }
        ]
    )

    frame = compute_sector_alpha_factors_frame(
        theme_state_daily=theme,
        sector_horizon_metrics=horizon,
        constituents=constituents,
        ticker_daily=ticker_daily,
        sector_daily=sector_daily,
    )
    assert list(frame.columns) == SECTOR_ALPHA_FACTORS_COLUMNS
    assert len(frame) == 1
    row = frame.iloc[0]
    assert float(row["s_brd_breadth"]) == pytest.approx(55.0)
    assert float(row["s_mom_ret_5d"]) == pytest.approx(2.0)
    assert float(row["m_val_pe_cheap_cs"]) == pytest.approx(60.0)
    assert float(row["m_qual_stage_score"]) == pytest.approx(1.0)
    assert float(row["m_struct_hhi_cap"]) == pytest.approx(0.7**2 + 0.3**2)
    assert math.isfinite(float(row["s_struct_ret_dispersion"]))
    assert math.isfinite(float(row["s_struct_leader_conc"]))
