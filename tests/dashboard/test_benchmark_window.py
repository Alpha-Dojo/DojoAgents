from __future__ import annotations

import pytest

from dojoagents.harnesses.built_in.financial.contracts.stock_kline import StockKlineBar
from dojoagents.harnesses.built_in.financial.services.benchmark_store import _bars_for_window, _window_change_percent
from dojoagents.harnesses.built_in.financial.services.market_window import MarketAnalysisWindow


def _bar(day: str, close: float) -> StockKlineBar:
    return StockKlineBar(
        symbol="^SPX",
        kline_t="1D",
        bar_time=day,
        open=close,
        high=close,
        low=close,
        close=close,
        vol=0.0,
        amount=0.0,
        change_p=0.0,
        tr=0.0,
        adj_factor_cum=1.0,
        dividends=0.0,
        splits=0.0,
    )


def test_bars_for_window_date_range_filters_kline() -> None:
    bars = [_bar("2026-01-02", 100.0), _bar("2026-01-03", 110.0), _bar("2026-01-06", 120.0)]
    scoped = _bars_for_window(
        bars,
        MarketAnalysisWindow(mode="date_range", start_date="2026-01-03", end_date="2026-01-06"),
    )
    assert [bar.bar_time for bar in scoped] == ["2026-01-03", "2026-01-06"]


def test_window_change_percent_for_date_range() -> None:
    bars = [_bar("2026-01-02", 100.0), _bar("2026-01-03", 110.0), _bar("2026-01-06", 120.0)]
    change = _window_change_percent(
        bars,
        MarketAnalysisWindow(mode="date_range", start_date="2026-01-03", end_date="2026-01-06"),
    )
    assert change == pytest.approx(9.090909090909092)
