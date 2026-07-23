from __future__ import annotations

import math

import pandas as pd
import pytest

from dojoagents.harnesses.built_in.financial.pipelines.precompute_sector_horizon import (
    SECTOR_HORIZON_METRICS_COLUMNS,
    compute_sector_horizon_metrics_frame,
    max_drawdown_pct,
    summarize_multi_quarter_fundamentals,
)
from dojoagents.harnesses.built_in.financial.services.theme_state_metrics import list_report_period_keys


def test_max_drawdown_pct() -> None:
    assert max_drawdown_pct([100, 110, 99, 120]) == pytest.approx((-11 / 110) * 100.0)


def test_list_report_period_keys_newest_first() -> None:
    quarters = {
        "2023:q1": {"revenue": 8.0, "net_profit": 0.8},
        "2023:q2": {"revenue": 9.0, "net_profit": 0.9},
        "2023:q3": {"revenue": 9.5, "net_profit": 0.95},
        "2023:q4": {"revenue": 10.0, "net_profit": 1.0},
        "2024:q1": {"revenue": 10.0, "net_profit": 1.0},
        "2024:q2": {"revenue": 11.0, "net_profit": 1.1},
        "2024:q3": {"revenue": 12.0, "net_profit": 1.2},
        "2024:q4": {"revenue": 13.0, "net_profit": 1.3},
        "2025:q1": {"revenue": 14.0, "net_profit": 1.4},
    }
    ticker_quarters = {ticker: dict(quarters) for ticker in ("AAA", "BBB", "CCC", "DDD", "EEE")}
    keys = list_report_period_keys(ticker_quarters, max_periods=4)
    assert keys == ["2025:q1", "2024:q4", "2024:q3", "2024:q2"]


def test_summarize_multi_quarter_fundamentals_streak() -> None:
    fin = pd.DataFrame(
        [
            {
                "report_period_key": "2025:q1",
                "fin_status": "ok",
                "fin_report_period": "2025:q1",
                "industry_revenue_yoy_pct": 12.0,
                "industry_net_profit_yoy_pct": 20.0,
                "industry_net_margin_pct": 5.0,
                "stage_hint": "expanding",
            },
            {
                "report_period_key": "2024:q4",
                "fin_status": "ok",
                "fin_report_period": "2024:q4",
                "industry_revenue_yoy_pct": 8.0,
                "industry_net_profit_yoy_pct": 10.0,
                "industry_net_margin_pct": 4.5,
                "stage_hint": "expanding",
            },
            {
                "report_period_key": "2024:q3",
                "fin_status": "ok",
                "fin_report_period": "2024:q3",
                "industry_revenue_yoy_pct": -2.0,
                "industry_net_profit_yoy_pct": -1.0,
                "industry_net_margin_pct": 4.0,
                "stage_hint": "mixed",
            },
        ]
    )
    summary = summarize_multi_quarter_fundamentals(fin)
    assert summary["fin_status"] == "ok"
    assert summary["revenue_yoy_positive_streak"] == 2
    assert summary["fin_quarters_available"] == 3
    assert summary["revenue_yoy_avg_4q_pct"] == pytest.approx((12.0 + 8.0 - 2.0) / 3.0)


def test_compute_sector_horizon_metrics_frame_windows() -> None:
    dates = pd.bdate_range("2025-01-02", periods=130).strftime("%Y-%m-%d").tolist()
    rows: list[dict] = []
    for level3_id, growth, pe in (("3", 1.01, 20.0), ("4", 1.005, 40.0)):
        level = 100.0
        for i, trade_date in enumerate(dates):
            prev = level
            if i:
                level *= growth
            rows.append(
                {
                    "trade_date": trade_date,
                    "scope": "L3",
                    "market": "us",
                    "level1_id": "1",
                    "level2_id": "2",
                    "level3_id": level3_id,
                    "member_count": 10,
                    "member_count_with_return": 10,
                    "total_market_cap": 1e10,
                    "effective_weight_sum": 1.0,
                    "weighted_pe": pe,
                    "index_level": level,
                    "daily_return_pct": ((level / prev) - 1.0) * 100.0 if i else 0.0,
                }
            )
    sector_daily = pd.DataFrame(rows)
    bench = pd.DataFrame(
        {
            "trade_date": dates,
            "market": "us",
            "benchmark_id": "^SPX",
            "benchmark_source": "index",
            "daily_return_pct": [0.1] * len(dates),
            "return_5d_pct": [0.5] * len(dates),
            "return_10d_pct": [1.0] * len(dates),
            "return_20d_pct": [2.0] * len(dates),
        }
    )
    fin = pd.DataFrame(
        [
            {
                "market": "us",
                "scope": "L3",
                "level1_id": "1",
                "level2_id": "2",
                "level3_id": "3",
                "link_key": "theme-a",
                "report_period_key": "2025:q1",
                "fin_status": "ok",
                "fin_report_period": "2025:q1",
                "industry_revenue_yoy_pct": 25.0,
                "industry_net_profit_yoy_pct": 30.0,
                "industry_net_margin_pct": 10.0,
                "stage_hint": "expanding",
            }
        ]
    )

    out = compute_sector_horizon_metrics_frame(
        sector_daily=sector_daily,
        benchmark_daily=bench,
        fundamentals_period=fin,
        link_key_by_level3={"3": "theme-a", "4": "theme-b"},
    )
    assert list(out.columns) == SECTOR_HORIZON_METRICS_COLUMNS
    latest = out[(out["level3_id"] == "3") & (out["trade_date"] == dates[-1])].iloc[0]
    assert latest["row_status"] == "partial"  # 130 days → 60/120 ok, 252 missing
    assert math.isfinite(float(latest["return_60d_pct"]))
    assert math.isfinite(float(latest["return_120d_pct"]))
    assert math.isnan(float(latest["return_252d_pct"]))
    assert latest["fin_status"] == "ok"
    assert latest["stage_hint"] == "expanding"
    peer = out[(out["level3_id"] == "4") & (out["trade_date"] == dates[-1])].iloc[0]
    # Higher PE → higher cross-section percentile (more peers cheaper than you).
    assert float(peer["pe_percentile_cross_section"]) > float(latest["pe_percentile_cross_section"])
