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
async def test_sphere_service_performance_caches_wrapped_payload(tmp_path) -> None:
    service = DojoSphereService(SectorMetricsStore(tmp_path, schema_version=1))
    calls = {"count": 0}

    async def compute():
        calls["count"] += 1
        return {"points": [{"date": "2026-06-20", "us": 101}], "as_of": "2026-06-20"}

    first = await service.performance("L3/1/2/3", compute)
    second = await service.performance("L3/1/2/3", compute)

    assert first == second
    assert calls["count"] == 1


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


@pytest.mark.asyncio
async def test_sphere_performance_recomputes_when_revision_changes(tmp_path) -> None:
    revision = {"value": "rev-1"}
    service = DojoSphereService(
        SectorMetricsStore(tmp_path, schema_version=1),
        revision_provider=lambda: revision["value"],
    )
    calls = {"count": 0}

    async def compute():
        calls["count"] += 1
        return {"points": [{"date": "2026-10-08", "us": 102}], "as_of": "2026-10-08"}

    first = await service.performance("L3/287/295/296", compute)
    cached = await service.performance("L3/287/295/296", compute)  # same revision -> cached
    assert calls["count"] == 1
    assert cached == first
    assert cached["data_revision"] == "rev-1"

    revision["value"] = "rev-2"
    refreshed = await service.performance("L3/287/295/296", compute)  # revision changed -> recompute
    assert calls["count"] == 2
    assert refreshed["data_revision"] == "rev-2"


@pytest.mark.asyncio
async def test_sphere_performance_serves_unguarded_cache_without_provider(tmp_path) -> None:
    service = DojoSphereService(SectorMetricsStore(tmp_path, schema_version=1))
    calls = {"count": 0}

    async def compute():
        calls["count"] += 1
        return {"points": [], "as_of": None}

    await service.performance("L3/1/2/3", compute)
    await service.performance("L3/1/2/3", compute)
    assert calls["count"] == 1


@pytest.mark.asyncio
async def test_sphere_metrics_recomputes_stale_legacy_payload(tmp_path) -> None:
    store = SectorMetricsStore(tmp_path, schema_version=1)
    # Seed a legacy-format (unwrapped) payload as written by older builds.
    await store.put("287/295/296", {"scopes": {"L3": {"us": {"member_count": 1}}}})

    service = DojoSphereService(store, revision_provider=lambda: "rev-9")

    async def compute():
        return {"scopes": {"L3": {"us": {"member_count": 19}}}}

    payload = await service.metrics("287/295/296", compute)
    assert payload["scopes"]["L3"]["us"]["member_count"] == 19

    # Second call hits the new wrapped cache (same revision).
    second = await service.metrics("287/295/296", compute)
    assert second == payload
