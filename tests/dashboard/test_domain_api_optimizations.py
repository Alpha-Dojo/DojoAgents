from __future__ import annotations

from types import SimpleNamespace

import pytest

import dojoagents.harnesses.built_in.financial.services.domain_api as domain_api
from dojoagents.harnesses.built_in.financial.contracts.dojo_mesh import BilingualText
from dojoagents.harnesses.built_in.financial.contracts.dojo_sphere import (
    SectorConstituentsResponse,
    SectorPerformanceResponse,
    SectorScopeMetricsResponse,
)


def _registry(tmp_path):
    path = SimpleNamespace(level1_id="1", level2_id="2", level3_id="3")
    metrics_cache: dict[str, dict] = {}
    performance_cache: dict[str, dict] = {}
    calls = {"prioritize": 0}

    async def prioritize_sector_path(*_args, **_kwargs):
        calls["prioritize"] += 1

    async def metrics(key, compute):
        cached = metrics_cache.get(key)
        if cached is not None:
            return cached
        payload = await compute()
        metrics_cache[key] = payload
        return payload

    async def performance(key, compute):
        cached = performance_cache.get(key)
        if cached is not None:
            return cached
        payload = await compute()
        wrapped = {
            "payload": payload,
            "as_of": payload.get("as_of"),
            "source": "computed",
            "stale": bool(payload.get("stale", False)),
        }
        performance_cache[key] = wrapped
        return wrapped

    registry = SimpleNamespace(
        sector_store=SimpleNamespace(find_resolved_path=lambda *_args: path),
        stock_store=object(),
        stock_sector_store=object(),
        kline_store=SimpleNamespace(prioritize_sector_path=prioritize_sector_path),
        dojo_sphere_service=SimpleNamespace(
            metrics=metrics,
            performance=performance,
        ),
        sector_precomputed_store=None,
    )
    return registry, calls, path, performance_cache


@pytest.mark.asyncio
async def test_build_sector_analysis_uses_cached_metrics_and_scope_performance(tmp_path, monkeypatch) -> None:
    registry, calls, path, _performance_cache = _registry(tmp_path)
    compute_calls = {"metrics": 0, "performance": []}

    async def fake_metrics(*_args, **_kwargs):
        compute_calls["metrics"] += 1
        return SectorScopeMetricsResponse(level1_id="1", level2_id="2", level3_id="3")

    async def fake_performance(*_args, scope: str, **_kwargs):
        compute_calls["performance"].append(scope)
        return SectorPerformanceResponse(
            level1_id="1",
            level2_id="2",
            level3_id="3",
            scope=scope,
            as_of=f"2026-06-{scope[-1]}0",
            window_start="2025-06-20",
            window_end="2026-06-20",
        )

    monkeypatch.setattr(domain_api, "compute_sector_scope_metrics", fake_metrics)
    monkeypatch.setattr(domain_api, "compute_sector_scope_performance", fake_performance)

    first = await domain_api.build_sector_analysis(registry, path, scope="L3")
    second = await domain_api.build_sector_analysis(registry, path, scope="L1")

    assert first.scopes.keys() == {"L1", "L2", "L3"}
    assert second.scope == "L1"
    assert compute_calls["metrics"] == 1
    assert compute_calls["performance"] == ["L1", "L2", "L3"]
    assert calls["prioritize"] == 2


@pytest.mark.asyncio
async def test_build_sector_constituents_uses_native_market_and_counts_items(tmp_path, monkeypatch) -> None:
    registry, _calls, _path, _performance_cache = _registry(tmp_path)

    async def fake_list_sector_constituents(*_args, market=None, **_kwargs):
        assert market == "us"
        return SectorConstituentsResponse(
            level1_id="1",
            level2_id="2",
            level3_id="3",
            scope="L2",
            market="us",
            items=[],
        )

    monkeypatch.setattr(domain_api, "list_sector_constituents", fake_list_sector_constituents)

    response = await domain_api.build_sector_constituents_v1(
        registry,
        level1_id="1",
        level2_id="2",
        level3_id="3",
        scope="L2",
        market="us",
        days=5,
    )

    assert response.scope == "L2"
    assert response.market == "us"
    assert response.count == 0


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
                    "member_count": 2,
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
    assert item.name == BilingualText(zh="半导体", en="Semiconductors")
    assert item.concept_code == "US.L3.semiconductors"


@pytest.mark.asyncio
async def test_build_sector_analysis_backfills_kline_precomputed_store(tmp_path, monkeypatch) -> None:
    registry, calls, path, _performance_cache = _registry(tmp_path)
    registry.sector_precomputed_store = object()
    registry.kline_store = SimpleNamespace(
        sector_precomputed_store=None,
        prioritize_sector_path=registry.kline_store.prioritize_sector_path,
    )

    async def fake_metrics(*_args, **_kwargs):
        return SectorScopeMetricsResponse(level1_id="1", level2_id="2", level3_id="3")

    async def fake_performance(*_args, scope: str, **_kwargs):
        return SectorPerformanceResponse(
            level1_id="1",
            level2_id="2",
            level3_id="3",
            scope=scope,
            as_of=f"2026-06-{scope[-1]}0",
            window_start="2025-06-20",
            window_end="2026-06-20",
        )

    monkeypatch.setattr(domain_api, "compute_sector_scope_metrics", fake_metrics)
    monkeypatch.setattr(domain_api, "compute_sector_scope_performance", fake_performance)

    response = await domain_api.build_sector_analysis(registry, path, scope="L3")

    assert response.scope == "L3"
    assert registry.kline_store.sector_precomputed_store is registry.sector_precomputed_store
    assert calls["prioritize"] == 1
