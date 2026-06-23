from __future__ import annotations

from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from dojoagents.dashboard.services.file_store_base import AtomicJsonStore


class SectorPerformanceCache:
    def __init__(self, root: Path, *, schema_version: int) -> None:
        self.store = AtomicJsonStore(
            root / "derived" / "sector-performance",
            schema_version=schema_version,
        )

    async def get(self, key: str) -> dict[str, Any] | None:
        value = await self.store.read(key)
        if not isinstance(value, dict):
            return None
        return {**value, "source": "dashboard_cache"}

    async def put(
        self,
        key: str,
        payload: dict[str, Any],
        *,
        as_of: str | None,
        source: str = "computed",
        stale: bool = False,
    ) -> dict[str, Any]:
        value = {
            "payload": payload,
            "as_of": as_of,
            "source": source,
            "stale": stale,
        }
        await self.store.write(key, value)
        return value

    async def get_or_compute(
        self,
        key: str,
        compute: Callable[[], Awaitable[dict[str, Any]]],
    ) -> dict[str, Any]:
        cached = await self.get(key)
        if cached is not None:
            return cached
        payload = await compute()
        return await self.put(key, payload, as_of=None)
