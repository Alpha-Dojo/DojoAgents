from __future__ import annotations

import pytest

from dojoagents.dashboard.services.dojo_sphere_service import DojoSphereService
from dojoagents.dashboard.services.sector_metrics_store import SectorMetricsStore


@pytest.mark.asyncio
async def test_sphere_service_performance_returns_computed_payload(tmp_path) -> None:
    service = DojoSphereService(SectorMetricsStore(tmp_path, schema_version=1))

    async def compute():
        return {"points": [{"date": "2026-06-20", "us": 101}], "as_of": "2026-06-20"}

    result = await service.performance("L3/1/2/3", compute)

    assert result["payload"]["points"][0]["us"] == 101
    assert result["as_of"] == "2026-06-20"
    assert result["source"] == "computed"
    assert result["stale"] is False


@pytest.mark.asyncio
async def test_sphere_service_performance_propagates_failure(tmp_path) -> None:
    service = DojoSphereService(SectorMetricsStore(tmp_path, schema_version=1))

    async def fail():
        raise RuntimeError("upstream unavailable")

    with pytest.raises(RuntimeError):
        await service.performance("L3/1/2/3", fail, refresh=True)


@pytest.mark.asyncio
async def test_sphere_metrics_snapshot_round_trip(tmp_path) -> None:
    service = DojoSphereService(SectorMetricsStore(tmp_path, schema_version=1))

    async def compute():
        return {"scopes": {"L3": {"us": {"member_count": 2}}}}

    first = await service.metrics("1/2/3", compute)
    second = await service.metrics("1/2/3", lambda: None)  # type: ignore[arg-type]

    assert first == second
