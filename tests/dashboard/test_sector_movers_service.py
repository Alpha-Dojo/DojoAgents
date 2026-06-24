from __future__ import annotations

from types import SimpleNamespace

import pandas as pd

from dojoagents.dashboard.services.sector_movers_service import SectorMoversService
from dojoagents.dashboard.services.sector_precomputed_store import SectorPrecomputedStore


def test_ticker_window_results_are_cached_per_day(monkeypatch) -> None:
    store = SectorPrecomputedStore()
    store._ticker_daily_df = pd.DataFrame(
        [
            {"market": "us", "ticker": "AAA", "trade_date": "2026-06-20", "close": 100.0, "daily_return_pct": 1.0},
            {"market": "us", "ticker": "AAA", "trade_date": "2026-06-21", "close": 110.0, "daily_return_pct": 10.0},
            {"market": "us", "ticker": "BBB", "trade_date": "2026-06-20", "close": 50.0, "daily_return_pct": 2.0},
            {"market": "us", "ticker": "BBB", "trade_date": "2026-06-21", "close": 45.0, "daily_return_pct": -10.0},
        ]
    )
    store._rebuild_indexes_locked()

    calls = {"count": 0}
    original = SectorPrecomputedStore._compute_window_frame

    def wrapped(*args, **kwargs):
        calls["count"] += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(SectorPrecomputedStore, "_compute_window_frame", staticmethod(wrapped))

    first = store.get_ticker_daily_by_window(2, ["AAA"])
    second = store.get_ticker_daily_by_window(2, ["BBB"])

    assert len(first) == 1
    assert len(second) == 1
    assert calls["count"] == 1


def test_sector_movers_service_only_builds_members_for_selected_top_sectors() -> None:
    sector_rows = pd.DataFrame(
        [
            {
                "market": "us",
                "scope": "L3",
                "level1_id": "1",
                "level2_id": "1",
                "level3_id": "1",
                "daily_return_pct": 3.0,
                "total_market_cap": 300.0,
                "member_count": 1,
            },
            {
                "market": "us",
                "scope": "L3",
                "level1_id": "1",
                "level2_id": "1",
                "level3_id": "2",
                "daily_return_pct": 1.0,
                "total_market_cap": 100.0,
                "member_count": 1,
            },
            {
                "market": "us",
                "scope": "L3",
                "level1_id": "1",
                "level2_id": "1",
                "level3_id": "3",
                "daily_return_pct": -2.0,
                "total_market_cap": 200.0,
                "member_count": 1,
            },
        ]
    )
    ticker_rows = pd.DataFrame(
        [
            {"market": "us", "ticker": "AAA", "daily_return_pct": 3.0},
            {"market": "us", "ticker": "BBB", "daily_return_pct": 1.0},
            {"market": "us", "ticker": "CCC", "daily_return_pct": -2.0},
        ]
    )

    constituent_calls: list[str] = []

    class FakePrecomputedStore:
        load_generation = 1

        def get_sector_movers_window_frame(self, days: int):
            assert days == 2
            return sector_rows

        def get_ticker_daily_window_frame(self, days: int):
            assert days == 2
            return ticker_rows

        def get_sector_constituents_exact(self, level1_id: str, level2_id: str, level3_id: str, market: str | None = None):
            constituent_calls.append(level3_id)
            return [{"ticker": {"1": "AAA", "2": "BBB", "3": "CCC"}[level3_id], "market_cap": 100.0}]

    sector_store = SimpleNamespace(
        find_resolved_path=lambda _l1, _l2, l3: SimpleNamespace(
            level3_zh=f"板块{l3}",
            level3_en=f"Sector {l3}",
        )
    )
    stock_store = SimpleNamespace(
        get=lambda _market, ticker: SimpleNamespace(
            ticker=ticker,
            market="us",
            short_name=ticker,
            long_name=ticker,
            stock_quote=SimpleNamespace(last_price=10.0),
        )
    )

    service = SectorMoversService(
        sector_store=sector_store,
        stock_store=stock_store,
        sector_precomputed_store=FakePrecomputedStore(),
    )

    response = service.build_market_movers_response(
        days=2,
        limit=1,
        market="us",
        min_cap_by_market={},
    )

    assert [item.name.en for item in response.markets["us"].gainers] == ["Sector 1"]
    assert [item.name.en for item in response.markets["us"].losers] == ["Sector 3"]
    assert constituent_calls == ["1", "3"]
