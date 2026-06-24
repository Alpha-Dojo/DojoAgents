from __future__ import annotations

import pytest

from dojoagents.dashboard.services.dojo_sphere_service import DojoSphereService
from dojoagents.dashboard.services.sector_metrics_store import SectorMetricsStore
from dojoagents.dashboard.services.sector_performance_cache import SectorPerformanceCache


@pytest.mark.asyncio
async def test_sphere_service_cache_hit_skips_performance_compute(tmp_path) -> None:
    service = DojoSphereService(
        SectorPerformanceCache(tmp_path, schema_version=1),
        SectorMetricsStore(tmp_path, schema_version=1),
    )
    await service.performance_cache.put(
        "L3/1/2/3",
        {"points": [{"date": "2026-06-20", "us": 101}]},
        as_of="2026-06-20",
    )

    async def fail():
        raise AssertionError("cache hit must not compute")

    result = await service.performance("L3/1/2/3", fail)

    assert result["payload"]["points"][0]["us"] == 101
    assert result["source"] == "dashboard_cache"


@pytest.mark.asyncio
async def test_sphere_service_refresh_failure_returns_stale_cache(tmp_path) -> None:
    service = DojoSphereService(
        SectorPerformanceCache(tmp_path, schema_version=1),
        SectorMetricsStore(tmp_path, schema_version=1),
    )
    await service.performance_cache.put("L3/1/2/3", {"points": []}, as_of="2026-06-20")

    async def fail():
        raise RuntimeError("upstream unavailable")

    result = await service.performance("L3/1/2/3", fail, refresh=True)

    assert result["stale"] is True
    assert result["source"] == "dashboard_cache"


@pytest.mark.asyncio
async def test_sphere_metrics_snapshot_round_trip(tmp_path) -> None:
    service = DojoSphereService(
        SectorPerformanceCache(tmp_path, schema_version=1),
        SectorMetricsStore(tmp_path, schema_version=1),
    )

    async def compute():
        return {"scopes": {"L3": {"us": {"member_count": 2}}}}

    first = await service.metrics("1/2/3", compute)
    second = await service.metrics("1/2/3", lambda: None)  # type: ignore[arg-type]

    assert first == second
