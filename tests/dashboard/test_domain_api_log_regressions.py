from __future__ import annotations

from types import SimpleNamespace

import pytest

from dojoagents.dashboard.schemas.dojo_core import CoreTickerSearchItem
from dojoagents.dashboard.schemas.dojo_mesh import BilingualText
import dojoagents.dashboard.services.domain_api as domain_api


@pytest.mark.asyncio
async def test_build_sector_movers_uses_resolved_sector_names() -> None:
    registry = SimpleNamespace(
        sector_store=SimpleNamespace(find_resolved_path=lambda *_args: SimpleNamespace(level3_zh="半导体", level3_en="Semiconductors")),
        stock_store=SimpleNamespace(
            get=lambda market, ticker: SimpleNamespace(
                ticker=ticker,
                short_name=ticker,
                long_name=ticker,
                stock_quote=SimpleNamespace(last_price=10.0),
            )
        ),
        sector_precomputed_store=SimpleNamespace(
            resolve_window_bounds=lambda window: window.with_resolved_bounds(
                start="2026-01-01",
                end="2026-01-07",
            ),
            get_sector_movers_for_window=lambda window: [
                {
                    "market": "us",
                    "scope": "L3",
                    "level1_id": "1",
                    "level2_id": "2",
                    "level3_id": "3",
                    "daily_return_pct": 1.23,
                    "total_market_cap": 200.0,
                    "member_count": 5,
                }
            ],
            get_sector_constituents=lambda **_kwargs: [
                {"ticker": "NVDA", "market_cap": 100.0},
                {"ticker": "AMD", "market_cap": 100.0},
            ],
            get_ticker_daily_for_window=lambda window, tickers: [
                {"ticker": "NVDA", "daily_return_pct": 2.0},
                {"ticker": "AMD", "daily_return_pct": 1.0},
            ],
        ),
    )

    response = await domain_api.build_sector_movers(
        registry,
        days=1,
        limit=5,
        market="us",
    )

    item = response.markets["us"].gainers[0]
    assert item.name.zh == "半导体"
    assert item.name.en == "Semiconductors"
    assert item.concept_code == "US.L3.semiconductors"


@pytest.mark.asyncio
async def test_build_sector_movers_supports_date_range_window() -> None:
    registry = SimpleNamespace(
        sector_store=SimpleNamespace(find_resolved_path=lambda *_args: SimpleNamespace(level3_zh="半导体", level3_en="Semiconductors")),
        stock_store=SimpleNamespace(
            get=lambda market, ticker: SimpleNamespace(
                ticker=ticker,
                short_name=ticker,
                long_name=ticker,
                stock_quote=SimpleNamespace(last_price=10.0, name=""),
            )
        ),
        sector_precomputed_store=SimpleNamespace(
            resolve_window_bounds=lambda window: window.with_resolved_bounds(
                start=window.start_date,
                end=window.end_date,
            ),
            get_sector_movers_for_window=lambda window: [
                {
                    "market": "us",
                    "scope": "L3",
                    "level1_id": "1",
                    "level2_id": "2",
                    "level3_id": "3",
                    "daily_return_pct": 2.5,
                    "total_market_cap": 200.0,
                    "member_count": 5,
                }
            ],
            get_sector_constituents=lambda **_kwargs: [{"ticker": "NVDA", "market_cap": 100.0}],
            get_ticker_daily_for_window=lambda window, tickers: [{"ticker": "NVDA", "daily_return_pct": 2.5}],
        ),
        sector_movers_service=None,
    )

    response = await domain_api.build_sector_movers(
        registry,
        days=1,
        limit=5,
        market="us",
        start_date="2026-01-02",
        end_date="2026-01-31",
    )

    assert response.window_mode == "date_range"
    assert response.window_start == "2026-01-02"
    assert response.window_end == "2026-01-31"
    assert response.markets["us"].gainers[0].change_percent == 2.5


@pytest.mark.asyncio
async def test_build_sector_movers_excludes_single_member_sectors() -> None:
    registry = SimpleNamespace(
        sector_store=SimpleNamespace(find_resolved_path=lambda *_args: SimpleNamespace(level3_zh="单票", level3_en="Solo")),
        stock_store=SimpleNamespace(get=lambda *_args, **_kwargs: None),
        sector_precomputed_store=SimpleNamespace(
            resolve_window_bounds=lambda window: window,
            get_sector_movers_for_window=lambda window: [
                {
                    "market": "us",
                    "scope": "L3",
                    "level1_id": "1",
                    "level2_id": "2",
                    "level3_id": "3",
                    "daily_return_pct": 9.99,
                    "total_market_cap": 999.0,
                    "member_count": 1,
                }
            ],
            get_sector_constituents=lambda **_kwargs: [],
            get_ticker_daily_for_window=lambda window, tickers: [],
        ),
        sector_movers_service=None,
    )

    response = await domain_api.build_sector_movers(registry, days=1, limit=5, market="us")

    assert response.markets["us"].gainers == []
    assert response.markets["us"].losers == []


@pytest.mark.asyncio
async def test_build_sector_analysis_backfills_kline_precomputed_store(monkeypatch) -> None:
    path = SimpleNamespace(level1_id="1", level2_id="2", level3_id="3")
    calls = {"prioritize": 0}

    async def prioritize_sector_path(*_args, **_kwargs):
        calls["prioritize"] += 1

    async def fake_metrics(*_args, **_kwargs):
        return SimpleNamespace(model_dump=lambda: {"level1_id": "1", "level2_id": "2", "level3_id": "3"})

    async def fake_performance(*_args, scope: str, **_kwargs):
        return SimpleNamespace(
            model_dump=lambda: {
                "level1_id": "1",
                "level2_id": "2",
                "level3_id": "3",
                "scope": scope,
                "as_of": "2026-06-20",
                "window_start": "2025-06-20",
                "window_end": "2026-06-20",
            }
        )

    registry = SimpleNamespace(
        sector_store=SimpleNamespace(find_resolved_path=lambda *_args: path),
        stock_store=object(),
        sector_precomputed_store=object(),
        kline_store=SimpleNamespace(
            sector_precomputed_store=None,
            prioritize_sector_path=prioritize_sector_path,
        ),
        dojo_sphere_service=SimpleNamespace(
            metrics=lambda key, compute: compute(),
            performance=lambda key, compute: compute(),
        ),
    )

    monkeypatch.setattr(domain_api, "compute_sector_scope_metrics", fake_metrics)
    monkeypatch.setattr(domain_api, "compute_sector_scope_performance", fake_performance)

    response = await domain_api.build_sector_analysis(registry, path, scope="L3")

    assert response.scope == "L3"
    assert registry.kline_store.sector_precomputed_store is registry.sector_precomputed_store
    assert calls["prioritize"] == 1


def _quoted_stock(ticker: str, market: str = "sh"):
    return SimpleNamespace(
        ticker=ticker,
        market=market,
        short_name=ticker,
        long_name=ticker,
        currency="CNY",
        stock_quote=SimpleNamespace(
            name=ticker,
            last_price=10.0,
            change_percent=1.0,
            volume=1,
            turn_rate=0.5,
            market_cap=10_000_000_000.0,
            pe=12.0,
            pb=1.5,
            amount=1000.0,
        ),
    )


@pytest.mark.asyncio
async def test_build_sector_constituents_reads_source_cn_market_rows() -> None:
    path = SimpleNamespace(level1_id="1", level2_id="18", level3_id="21")

    def get_sector_constituents(**kwargs):
        if kwargs["market"] != "cn":
            return []
        return [{"ticker": "000001.SZ", "market": "cn"}]

    registry = SimpleNamespace(
        sector_store=SimpleNamespace(find_resolved_path=lambda *_args: path),
        stock_store=SimpleNamespace(get=lambda _market, ticker: _quoted_stock(ticker)),
        kline_store=SimpleNamespace(),
        sector_precomputed_store=SimpleNamespace(
            get_sector_constituents=get_sector_constituents,
            get_ticker_daily_by_window=lambda _days, _tickers: [{"ticker": "000001.SZ", "daily_return_pct": 2.5}],
        ),
    )

    response = await domain_api.build_sector_constituents_v1(
        registry,
        level1_id="1",
        level2_id="18",
        level3_id="21",
        scope="L3",
        market="cn",
        days=1,
    )

    assert response.market == "cn"
    assert response.count == 1
    assert response.items[0].ticker == "000001.SZ"


@pytest.mark.asyncio
async def test_build_sector_constituents_falls_back_to_precomputed_ids_when_path_index_missing() -> None:
    registry = SimpleNamespace(
        sector_store=SimpleNamespace(find_resolved_path=lambda *_args: None),
        stock_store=SimpleNamespace(get=lambda _market, ticker: _quoted_stock(ticker)),
        kline_store=SimpleNamespace(),
        sector_precomputed_store=SimpleNamespace(
            get_sector_constituents=lambda **_kwargs: [{"ticker": "AAPL", "market": "us"}],
            get_ticker_daily_by_window=lambda _days, _tickers: [{"ticker": "AAPL", "daily_return_pct": 3.0}],
        ),
    )

    response = await domain_api.build_sector_constituents_v1(
        registry,
        level1_id="109",
        level2_id="110",
        level3_id="111",
        scope="L3",
        market="us",
        days=1,
    )

    assert response.count == 1
    assert response.items[0].ticker == "AAPL"


@pytest.mark.asyncio
async def test_company_ticker_search_converts_core_items_to_source_schema(monkeypatch) -> None:
    monkeypatch.setattr(
        domain_api,
        "search_core_tickers",
        lambda *_args, **_kwargs: [
            CoreTickerSearchItem(
                ticker="NVDA",
                market="us",
                name=BilingualText(zh="英伟达", en="NVIDIA"),
                market_cap=4_849_044_200_000.0,
            )
        ],
    )
    registry = SimpleNamespace(
        stock_store=object(),
        stock_sector_store=object(),
        sector_store=object(),
    )

    response = await domain_api.search_company_ticker(
        registry,
        q="n",
        market=None,
        limit=30,
    )

    assert response.items[0].ticker == "NVDA"
    assert response.items[0].market == "us"


@pytest.mark.asyncio
async def test_build_sector_analysis_falls_back_to_precomputed_path_when_index_missing(monkeypatch) -> None:
    async def fake_metrics(*_args, **_kwargs):
        return SimpleNamespace(
            model_dump=lambda: {
                "scopes": {
                    "L3": {
                        "us": {
                            "market": "us",
                            "member_count": 1,
                            "total_market_cap": 100.0,
                            "weighted_pe": 12.0,
                            "pe_sample_count": 1,
                        }
                    }
                }
            }
        )

    async def fake_performance(*_args, scope: str, **_kwargs):
        return SimpleNamespace(
            model_dump=lambda: {
                "scope": scope,
                "window_start": "2025-06-20",
                "window_end": "2026-06-20",
                "series_by_market": {"us": [{"date": "2026-06-20", "value": 101.0}]},
                "stats_by_market": {"us": {"trading_days": 1}},
                "members_by_market": {"us": 1},
            }
        )

    async def prioritize_sector_path(*_args, **_kwargs):
        return None

    registry = SimpleNamespace(
        sector_store=SimpleNamespace(find_resolved_path=lambda *_args: None),
        stock_store=object(),
        sector_precomputed_store=SimpleNamespace(get_sector_constituents=lambda **_kwargs: [{"ticker": "NVDA", "market": "us"}]),
        kline_store=SimpleNamespace(
            sector_precomputed_store=None,
            prioritize_sector_path=prioritize_sector_path,
        ),
        dojo_sphere_service=SimpleNamespace(
            metrics=lambda _key, compute: compute(),
            performance=lambda _key, compute: compute(),
        ),
    )

    monkeypatch.setattr(domain_api, "compute_sector_scope_metrics", fake_metrics)
    monkeypatch.setattr(domain_api, "compute_sector_scope_performance", fake_performance)

    path = domain_api.resolve_sector_analysis_path(
        registry,
        level1_id="72",
        level2_id="82",
        level3_id="84",
    )

    assert path is not None

    response = await domain_api.build_sector_analysis(registry, path, scope="L3")

    assert response.scope == "L3"
    assert response.members_by_market == {"us": 1}
