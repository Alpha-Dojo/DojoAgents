from __future__ import annotations

import math

import pandas as pd
import pytest

from dojoagents.dashboard.services.precompute_sector_radar_advice import (
    SECTOR_ADVICE_DAILY_COLUMNS,
    SECTOR_HEALTH_RADAR_COLUMNS,
    compute_sector_radar_advice_frames,
    cross_section_percentile,
    overall_band,
    rank_to_score,
    stance_from_score,
)


def test_cross_section_percentile_and_rank_helpers() -> None:
    pct = cross_section_percentile(pd.Series([10.0, 20.0, 30.0]))
    assert pct.iloc[0] == pytest.approx(0.0)
    assert pct.iloc[1] == pytest.approx(100.0 / 3.0)
    assert pct.iloc[2] == pytest.approx(200.0 / 3.0)
    assert rank_to_score(1, 5) == pytest.approx(100.0)
    assert rank_to_score(5, 5) == pytest.approx(0.0)
    assert stance_from_score(70) == "strong"
    assert stance_from_score(50) == "neutral"
    assert stance_from_score(10) == "weak"
    assert overall_band(72) == "expansion"
    assert overall_band(30) == "cooling"


def test_compute_radar_and_advice_separates_short_mid() -> None:
    theme = pd.DataFrame(
        [
            {
                "trade_date": "2026-07-20",
                "market": "sh",
                "scope": "L3",
                "level1_id": "1",
                "level2_id": "2",
                "level3_id": "A",
                "link_key": "theme-a",
                "eligible_count": 20,
                "row_status": "ok",
                "breadth_score": 80.0,
                "volume_expansion_pct": 60.0,
                "new_highs_pct": 40.0,
                "return_5d_pct": 5.0,
                "return_20d_pct": 12.0,
                "risk_adjusted_20d": 0.8,
                "up_streak_days": 3,
                "down_streak_days": 0,
                "volatility_20d_pct": 15.0,
                "relative_strength_20d": 8.0,
                "rotation_rank": 1,
                "rs_rank_universe_size": 2,
                "confirmation_score": 1.0,
                "industry_revenue_yoy_pct": 5.0,
                "industry_net_profit_yoy_pct": 4.0,
                "revenue_improvers_pct": 55.0,
                "stage_hint": "stable",
                "fin_status": "ok",
            },
            {
                "trade_date": "2026-07-20",
                "market": "sh",
                "scope": "L3",
                "level1_id": "1",
                "level2_id": "2",
                "level3_id": "B",
                "link_key": "theme-b",
                "eligible_count": 20,
                "row_status": "ok",
                "breadth_score": 10.0,
                "volume_expansion_pct": 5.0,
                "new_highs_pct": 0.0,
                "return_5d_pct": -8.0,
                "return_20d_pct": -15.0,
                "risk_adjusted_20d": -1.2,
                "up_streak_days": 0,
                "down_streak_days": 4,
                "volatility_20d_pct": 25.0,
                "relative_strength_20d": -10.0,
                "rotation_rank": 2,
                "rs_rank_universe_size": 2,
                "confirmation_score": 0.0,
                "industry_revenue_yoy_pct": 30.0,
                "industry_net_profit_yoy_pct": 40.0,
                "revenue_improvers_pct": 90.0,
                "stage_hint": "expanding",
                "fin_status": "ok",
            },
        ]
    )
    horizon = pd.DataFrame(
        [
            {
                "trade_date": "2026-07-20",
                "market": "sh",
                "scope": "L3",
                "level1_id": "1",
                "level2_id": "2",
                "level3_id": "A",
                "link_key": "theme-a",
                "pe_percentile_cross_section": 20.0,
                "pe_percentile_trailing_252d": 25.0,
                "relative_strength_60d": 2.0,
                "relative_strength_120d": 3.0,
                "risk_adjusted_60d": 0.2,
                "risk_adjusted_120d": 0.3,
                "max_drawdown_120d_pct": -8.0,
                "return_60d_pct": 5.0,
                "return_120d_pct": 8.0,
                "revenue_yoy_avg_4q_pct": 6.0,
                "industry_revenue_yoy_pct": 5.0,
                "industry_net_profit_yoy_pct": 4.0,
                "fin_status": "ok",
                "row_status": "ok",
                "stage_hint": "stable",
                "fin_quarters_available": 4,
            },
            {
                "trade_date": "2026-07-20",
                "market": "sh",
                "scope": "L3",
                "level1_id": "1",
                "level2_id": "2",
                "level3_id": "B",
                "link_key": "theme-b",
                "pe_percentile_cross_section": 90.0,
                "pe_percentile_trailing_252d": 85.0,
                "relative_strength_60d": 25.0,
                "relative_strength_120d": 40.0,
                "risk_adjusted_60d": 1.1,
                "risk_adjusted_120d": 1.4,
                "max_drawdown_120d_pct": -12.0,
                "return_60d_pct": 30.0,
                "return_120d_pct": 55.0,
                "revenue_yoy_avg_4q_pct": 28.0,
                "industry_revenue_yoy_pct": 30.0,
                "industry_net_profit_yoy_pct": 40.0,
                "fin_status": "ok",
                "row_status": "ok",
                "stage_hint": "expanding",
                "fin_quarters_available": 8,
            },
        ]
    )

    radar_df, advice_df = compute_sector_radar_advice_frames(
        theme_state_daily=theme,
        sector_horizon_metrics=horizon,
    )
    assert list(radar_df.columns) == SECTOR_HEALTH_RADAR_COLUMNS
    assert list(advice_df.columns) == SECTOR_ADVICE_DAILY_COLUMNS
    assert len(radar_df) == 2
    assert len(advice_df) == 2

    by_id = advice_df.set_index("level3_id")
    # Theme A: strong short / weaker mid fundamentals relative to B
    assert float(by_id.loc["A", "short_score"]) > float(by_id.loc["B", "short_score"])
    assert int(by_id.loc["A", "short_rank"]) == 1
    assert int(by_id.loc["B", "short_rank"]) == 2
    # Theme B: stronger mid trend/fundamentals
    assert float(by_id.loc["B", "mid_score"]) > float(by_id.loc["A", "mid_score"])
    assert int(by_id.loc["B", "mid_rank"]) == 1
    assert by_id.loc["B", "panel_mode"] in {"dip_watch", "mixed", "aligned_bullish", "tactical_only"}

    radar = radar_df.set_index("level3_id")
    assert math.isfinite(float(radar.loc["A", "overall_score"]))
    assert radar.loc["A", "score_relative_strength"] >= radar.loc["B", "score_relative_strength"]
    assert radar.loc["B", "score_fundamental_trend"] >= radar.loc["A", "score_fundamental_trend"]
