from __future__ import annotations

import pytest

from dojoagents.harnesses.built_in.financial.services.theme_state_metrics import (
    aggregate_fundamentals_lite,
    breadth_confirmation_multiplier,
    compute_breadth_for_day,
    extract_quarter_metrics,
    rotation_score_frame,
    select_report_period_key,
    stage_hint_revenue_lite,
    streak_days,
    window_return_pct,
)
from dojoagents.harnesses.built_in.financial.services.fin_indicators_utils import (
    comparable_quarter_key,
    natural_comparable_quarter_key,
)


def test_window_return_pct_matches_lookback_semantics() -> None:
    levels = [100.0, 110.0, 121.0, 133.1, 146.41]
    assert window_return_pct(levels, 5) == ((146.41 / 100.0) - 1.0) * 100.0
    assert window_return_pct(levels, 2) == ((146.41 / 133.1) - 1.0) * 100.0
    assert window_return_pct(levels, 6) is None


def test_streak_days() -> None:
    assert streak_days([1.0, 2.0, -1.0, 1.0, 2.0], positive=True) == 2
    assert streak_days([1.0, -1.0, -2.0], positive=False) == 2


def test_breadth_confirmation_multiplier() -> None:
    assert breadth_confirmation_multiplier(None) == 1.0
    assert breadth_confirmation_multiplier(25.0) == 0.5
    assert breadth_confirmation_multiplier(50.0) == 1.0
    assert breadth_confirmation_multiplier(100.0) == 1.5
    assert breadth_confirmation_multiplier(10.0) == 0.5


def test_rotation_score_prefers_20d_rs_and_breadth() -> None:
    import pandas as pd

    # Same cross-section: high 20d RS + strong breadth should outrank high 5d-only spike.
    frame = pd.DataFrame(
        {
            "rs5": [10.0, 1.0],
            "rs10": [1.0, 5.0],
            "rs20": [0.0, 8.0],
            "breadth": [20.0, 80.0],
        }
    )
    scores = rotation_score_frame(
        relative_strength_5d=frame["rs5"],
        relative_strength_10d=frame["rs10"],
        relative_strength_20d=frame["rs20"],
        breadth_score=frame["breadth"],
    )
    assert float(scores.iloc[1]) > float(scores.iloc[0])


def test_breadth_advancers_and_volume() -> None:
    breadth = compute_breadth_for_day(
        member_tickers=["A", "B", "C"],
        day_returns={"A": 1.0, "B": -1.0, "C": 0.0},
        day_volumes={"A": 200.0, "B": 50.0, "C": 100.0},
        avg_volumes={"A": 100.0, "B": 100.0, "C": 100.0},
        day_closes={"A": 12.0, "B": 9.0, "C": 10.0},
        rolling_highs={"A": 12.0, "B": 10.0, "C": 11.0, "A__lookback": 20},
        volume_multiplier=1.5,
    )
    assert breadth["advancers_count"] == 1
    assert breadth["decliners_count"] == 1
    assert breadth["unchanged_count"] == 1
    assert breadth["volume_expansion_count"] == 1  # A only
    assert breadth["new_highs_count"] == 1
    assert breadth["advancers_pct"] == pytest.approx(100.0 / 3.0)


def test_aggregate_fundamentals_lite_and_stage_hint() -> None:
    tickers = {
        f"T{i}": {
            "2026:q1": {"revenue": 130.0, "net_profit": 20.0},
            "2025:q1": {"revenue": 100.0, "net_profit": 10.0},
            "2025:q4": {"revenue": 110.0, "net_profit": 12.0},
            "2024:q4": {"revenue": 100.0, "net_profit": 11.0},
        }
        for i in range(5)
    }
    payload = aggregate_fundamentals_lite(tickers, report_period_key="2026:q1")
    assert payload["fin_status"] == "ok"
    assert payload["fin_sample_count"] == 5
    assert payload["industry_revenue_yoy_pct"] == pytest.approx(30.0)
    assert payload["revenue_improvers_pct"] == pytest.approx(100.0)
    assert payload["stage_hint"] == "expanding"

    assert (
        stage_hint_revenue_lite(
            revenue_yoy_pct=-5.0,
            revenue_accel_pp=-1.0,
            revenue_improvers_pct=40.0,
            fin_coverage_ratio=0.8,
            fin_sample_count=10,
        )
        == "contracting"
    )


def test_apd_fiscal_q2_maps_to_natural_q1() -> None:
    row = {
        "report_period_name": "2026年第二季报",
        "report_date": "2026-03-31 00:00:00",
        "std_report_date": "2026-06-30 00:00:00",
        "fiscal_year_end": "9-30",
        "total_operating_revenue": 3_171_800_000.0,
        "net_profit_attr_parent": 710_400_000.0,
    }
    assert comparable_quarter_key(row) == ("2026", "q2")
    assert natural_comparable_quarter_key(row) == ("2026", "q1")

    mapped = extract_quarter_metrics([row], "us")
    assert "2026:q1" in mapped
    assert "2026:q2" not in mapped
    assert mapped["2026:q1"]["fiscal_quarter_key"] == "2026:q2"


def test_select_report_period_prefers_coverage_over_newest_sparse_quarter() -> None:
    # Sparse early reporters on a newer natural quarter must not starve the theme.
    tickers = {
        "APD": {
            "2026:q1": {"revenue": 130.0, "net_profit": 20.0},
            "2025:q1": {"revenue": 100.0, "net_profit": 10.0},
            "2026:q2": {"revenue": 140.0, "net_profit": 21.0},
            "2025:q2": {"revenue": 105.0, "net_profit": 11.0},
        },
        "FCEL": {
            "2026:q1": {"revenue": 30.0, "net_profit": -5.0},
            "2025:q1": {"revenue": 20.0, "net_profit": -4.0},
            "2026:q2": {"revenue": 35.0, "net_profit": -6.0},
            "2025:q2": {"revenue": 22.0, "net_profit": -3.0},
        },
    }
    for name in ("PLUG", "LIN", "BE", "BW", "CMBT"):
        tickers[name] = {
            "2026:q1": {"revenue": 100.0, "net_profit": 1.0},
            "2025:q1": {"revenue": 80.0, "net_profit": 1.0},
        }

    assert select_report_period_key(tickers) == "2026:q1"
    payload = aggregate_fundamentals_lite(tickers)
    assert payload["fin_status"] == "ok"
    assert payload["fin_report_period"] == "2026:q1"
    assert payload["fin_sample_count"] == 7
    assert payload["stage_hint"] in {"expanding", "stable"}
    assert payload["industry_revenue_yoy_pct"] > 0
