from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from dojoagents.dashboard.services.sector_metrics_store import SectorMetricsStore


class DojoSphereService:
    """Persistent cache for sector metrics/performance payloads.

    Cached payloads are guarded by a data revision supplied by
    ``revision_provider`` (the precomputed store's manifest identity). A cached
    payload computed against a different revision is recomputed and overwritten,
    so restarting the process or refreshing upstream snapshots can never serve
    stale curves indefinitely.
    """

    def __init__(
        self,
        metrics_store: SectorMetricsStore,
        *,
        revision_provider: Callable[[], str | None] | None = None,
    ) -> None:
        self.metrics_store = metrics_store
        self._revision_provider = revision_provider

    def _current_revision(self) -> str | None:
        if self._revision_provider is None:
            return None
        try:
            revision = self._revision_provider()
        except Exception:
            return None
        return str(revision) if revision else None

    def _cache_usable(self, cached: Any) -> bool:
        if not isinstance(cached, dict):
            return False
        current = self._current_revision()
        if current is None:
            return True
        return cached.get("data_revision") == current

    async def performance(
        self,
        key: str,
        compute: Callable[[], Awaitable[dict[str, Any]]],
        *,
        refresh: bool = False,
    ) -> dict[str, Any]:
        if not refresh:
            cached = await self.metrics_store.get(key)
            if isinstance(cached, dict) and "payload" in cached and self._cache_usable(cached):
                return cached
        payload = await compute()
        revision = self._current_revision()
        wrapped = {
            "payload": payload,
            "as_of": payload.get("as_of"),
            "source": "computed",
            "stale": bool(payload.get("stale", False)),
        }
        if revision is not None:
            wrapped["data_revision"] = revision
        await self.metrics_store.put(key, wrapped)
        return wrapped

    async def metrics(
        self,
        key: str,
        compute: Callable[[], Awaitable[dict[str, Any]]],
    ) -> dict[str, Any]:
        cached = await self.metrics_store.get(key)
        if isinstance(cached, dict):
            if "payload" in cached:
                if self._cache_usable(cached):
                    return cached["payload"]
            elif self._current_revision() is None:
                # Legacy format: payload stored unwrapped; only servable when
                # no revision guard is configured.
                return cached
        payload = await compute()
        revision = self._current_revision()
        if revision is None:
            await self.metrics_store.put(key, payload)
            return payload
        wrapped = {"payload": payload, "data_revision": revision}
        await self.metrics_store.put(key, wrapped)
        return payload
