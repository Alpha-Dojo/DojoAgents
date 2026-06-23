from __future__ import annotations

from types import SimpleNamespace

import pytest

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
            get_sector_movers_by_window=lambda days: [
                {
                    "market": "us",
                    "scope": "L3",
                    "level1_id": "1",
                    "level2_id": "2",
                    "level3_id": "3",
                    "daily_return_pct": 1.23,
                    "total_market_cap": 200.0,
                    "member_count": 2,
                }
            ],
            get_sector_constituents=lambda **_kwargs: [
                {"ticker": "NVDA", "market_cap": 100.0},
                {"ticker": "AMD", "market_cap": 100.0},
            ],
            get_ticker_daily_by_window=lambda days, tickers: [
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

    response = await domain_api.build_sector_analysis(
        registry,
        level1_id="1",
        level2_id="2",
        level3_id="3",
        scope="L3",
    )

    assert response.scope == "L3"
    assert registry.kline_store.sector_precomputed_store is registry.sector_precomputed_store
    assert calls["prioritize"] == 1
