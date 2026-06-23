from __future__ import annotations

from types import SimpleNamespace

import pytest

import dojoagents.dashboard.services.domain_api as domain_api
from dojoagents.dashboard.schemas.dojo_sphere import (
    SectorConstituentsResponse,
    SectorPerformanceResponse,
    SectorScopeMetricsResponse,
)
from dojoagents.dashboard.services.dojo_sphere_service import DojoSphereService
from dojoagents.dashboard.services.sector_metrics_store import SectorMetricsStore
from dojoagents.dashboard.services.sector_performance_cache import SectorPerformanceCache


def _registry(tmp_path):
    path = SimpleNamespace(level1_id="1", level2_id="2", level3_id="3")
    service = DojoSphereService(
        SectorPerformanceCache(tmp_path, schema_version=1),
        SectorMetricsStore(tmp_path, schema_version=1),
    )
    calls = {"prioritize": 0}

    async def prioritize_sector_path(*_args, **_kwargs):
        calls["prioritize"] += 1

    registry = SimpleNamespace(
        sector_store=SimpleNamespace(find_resolved_path=lambda *_args: path),
        stock_store=object(),
        stock_sector_store=object(),
        kline_store=SimpleNamespace(prioritize_sector_path=prioritize_sector_path),
        dojo_sphere_service=service,
        sector_precomputed_store=None,
    )
    return registry, calls


@pytest.mark.asyncio
async def test_build_sector_analysis_uses_cached_metrics_and_scope_performance(tmp_path, monkeypatch) -> None:
    registry, calls = _registry(tmp_path)
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

    first = await domain_api.build_sector_analysis(
        registry,
        level1_id="1",
        level2_id="2",
        level3_id="3",
        scope="L3",
    )
    second = await domain_api.build_sector_analysis(
        registry,
        level1_id="1",
        level2_id="2",
        level3_id="3",
        scope="L1",
    )

    assert first.scopes.keys() == {"L1", "L2", "L3"}
    assert second.scope == "L1"
    assert second.source == "dashboard_cache"
    assert compute_calls["metrics"] == 1
    assert compute_calls["performance"] == ["L1", "L2", "L3"]
    assert calls["prioritize"] == 2


@pytest.mark.asyncio
async def test_build_sector_constituents_reuses_cached_window_start(tmp_path, monkeypatch) -> None:
    registry, _calls = _registry(tmp_path)
    await registry.dojo_sphere_service.performance_cache.put(
        "L2/1/2/3",
        {"window_start": "2025-06-20"},
        as_of="2026-06-20",
    )
    captured: dict[str, str | None] = {"window_start": None}

    async def fake_list_sector_constituents(*_args, window_start=None, **_kwargs):
        captured["window_start"] = window_start
        return SectorConstituentsResponse(level1_id="1", level2_id="2", level3_id="3", scope="L2")

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
    assert captured["window_start"] == "2025-06-20"
