from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from dojoagents.dashboard.services.sector_metrics_store import SectorMetricsStore
from dojoagents.dashboard.services.sector_performance_cache import SectorPerformanceCache


class DojoSphereService:
    def __init__(
        self,
        performance_cache: SectorPerformanceCache,
        metrics_store: SectorMetricsStore,
    ) -> None:
        self.performance_cache = performance_cache
        self.metrics_store = metrics_store

    async def performance(
        self,
        key: str,
        compute: Callable[[], Awaitable[dict[str, Any]]],
        *,
        refresh: bool = False,
    ) -> dict[str, Any]:
        cached = await self.performance_cache.get(key)
        if cached is not None and not refresh:
            return cached
        try:
            payload = await compute()
        except Exception:
            if cached is None:
                raise
            return {**cached, "source": "dashboard_cache", "stale": True}
        as_of = payload.get("as_of") if isinstance(payload, dict) else None
        return await self.performance_cache.put(key, payload, as_of=as_of, source="computed")

    async def metrics(
        self,
        key: str,
        compute: Callable[[], Awaitable[dict[str, Any]]],
    ) -> dict[str, Any]:
        cached = await self.metrics_store.get(key)
        if cached is not None:
            return cached
        payload = await compute()
        await self.metrics_store.put(key, payload)
        return payload
