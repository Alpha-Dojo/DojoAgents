from __future__ import annotations

from dojoagents.harnesses.built_in.financial.contracts.portfolio import PortfolioPerformanceView, PortfolioRiskStats
from dojoagents.harnesses.built_in.financial.services.portfolio_performance_cache import (
    PortfolioPerformanceCache,
    performance_cache_key,
    portfolio_content_fingerprint,
)


def test_portfolio_content_fingerprint_changes_when_orders_change() -> None:
    base = {
        "updated_at": "2026-01-01T00:00:00+00:00",
        "config": {"start_date": "2026-01-01"},
        "orders": [],
        "candidates": [{"ticker": "AAPL", "market": "us"}],
    }
    changed = {
        **base,
        "orders": [{"id": "o1", "ticker": "AAPL", "market": "us", "order_status": "filled"}],
    }
    assert portfolio_content_fingerprint(base) != portfolio_content_fingerprint(changed)


def test_performance_cache_key_includes_revision() -> None:
    key_a = performance_cache_key(
        portfolio_id="p1",
        fingerprint="abc",
        start_date="2026-01-01",
        benchmark_by_market={"us": "^SPX"},
        market_data_revision="rev-1",
    )
    key_b = performance_cache_key(
        portfolio_id="p1",
        fingerprint="abc",
        start_date="2026-01-01",
        benchmark_by_market={"us": "^SPX"},
        market_data_revision="rev-2",
    )
    assert key_a != key_b


def test_performance_cache_returns_cached_view() -> None:
    cache = PortfolioPerformanceCache(max_entries=4)
    view = PortfolioPerformanceView(
        dates=["2026-01-01"],
        portfolio=[100.0],
        benchmark=[100.0],
        stats_by_market={"us": PortfolioRiskStats(trading_days=1)},
    )
    key = "p1:fp:start:bench:rev"
    assert cache.get(key) is None
    cache.set(key, view)
    assert cache.get(key) == view
    cache.clear("p1")
    assert cache.get(key) is None
