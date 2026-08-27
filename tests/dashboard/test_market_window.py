from __future__ import annotations

import pytest

from dojoagents.dashboard.services.market_window import (
    MarketAnalysisWindow,
    compound_return_pct,
    resolve_market_analysis_window,
    resolve_window_bounds_from_trade_dates,
)


def test_resolve_market_analysis_window_days_mode() -> None:
    window = resolve_market_analysis_window(days=5, default_days=1)
    assert window.mode == "days"
    assert window.days == 5


def test_resolve_market_analysis_window_date_range_mode() -> None:
    window = resolve_market_analysis_window(
        days=5,
        start_date="2026-01-02",
        end_date="2026-01-31",
    )
    assert window.mode == "date_range"
    assert window.start_date == "2026-01-02"
    assert window.end_date == "2026-01-31"


def test_resolve_market_analysis_window_as_of_days_mode() -> None:
    window = resolve_market_analysis_window(as_of="2026-08-10", days=5, default_days=1)
    assert window.mode == "as_of"
    assert window.as_of == "2026-08-10"
    assert window.days == 5


def test_resolve_market_analysis_window_as_of_defaults_days() -> None:
    window = resolve_market_analysis_window(as_of="2026-08-10", default_days=1)
    assert window.mode == "as_of"
    assert window.days == 1


def test_resolve_market_analysis_window_rejects_as_of_with_date_range() -> None:
    with pytest.raises(ValueError, match="cannot be combined"):
        resolve_market_analysis_window(
            as_of="2026-08-10",
            days=5,
            start_date="2026-08-01",
            end_date="2026-08-10",
        )


def test_resolve_market_analysis_window_rejects_partial_dates() -> None:
    with pytest.raises(ValueError, match="together"):
        resolve_market_analysis_window(start_date="2026-01-02")


def test_resolve_window_bounds_from_trade_dates_for_days() -> None:
    window = resolve_window_bounds_from_trade_dates(
        MarketAnalysisWindow(mode="days", days=3),
        ["2026-01-02", "2026-01-03", "2026-01-06", "2026-01-07"],
    )
    assert window.resolved_start == "2026-01-03"
    assert window.resolved_end == "2026-01-07"


def test_resolve_window_bounds_from_trade_dates_for_range() -> None:
    window = resolve_window_bounds_from_trade_dates(
        MarketAnalysisWindow(mode="date_range", start_date="2026-01-03", end_date="2026-01-10"),
        ["2026-01-02", "2026-01-04", "2026-01-08", "2026-01-12"],
    )
    assert window.resolved_start == "2026-01-04"
    assert window.resolved_end == "2026-01-08"


def test_resolve_window_bounds_as_of_falls_back_on_non_trading_day() -> None:
    window = resolve_window_bounds_from_trade_dates(
        MarketAnalysisWindow(mode="as_of", days=3, as_of="2026-01-11"),
        ["2026-01-07", "2026-01-08", "2026-01-09", "2026-01-12"],
    )
    assert window.resolved_start == "2026-01-07"
    assert window.resolved_end == "2026-01-09"


def test_compound_return_pct_multiplies_session_returns() -> None:
    assert compound_return_pct([10.0, 10.0, 10.0]) == pytest.approx(33.1)
