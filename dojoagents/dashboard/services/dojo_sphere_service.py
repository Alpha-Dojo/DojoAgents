from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from dojoagents.dashboard.services.sector_metrics_store import SectorMetricsStore


class DojoSphereService:
    def __init__(
        self,
        metrics_store: SectorMetricsStore,
    ) -> None:
        self.metrics_store = metrics_store

    async def performance(
        self,
        key: str,
        compute: Callable[[], Awaitable[dict[str, Any]]],
        *,
        refresh: bool = False,
    ) -> dict[str, Any]:
        del key, refresh
        try:
            payload = await compute()
        except Exception:
            raise
        return {
            "payload": payload,
            "as_of": payload.get("as_of"),
            "source": "computed",
            "stale": bool(payload.get("stale", False)),
        }

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
