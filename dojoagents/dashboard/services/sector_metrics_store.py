from __future__ import annotations

from pathlib import Path
from typing import Any

from dojoagents.dashboard.services.file_store_base import AtomicJsonStore


class SectorMetricsStore:
    def __init__(self, root: Path, *, schema_version: int) -> None:
        self.store = AtomicJsonStore(
            root / "derived" / "sector-metrics",
            schema_version=schema_version,
        )

    async def get(self, key: str) -> dict[str, Any] | None:
        value = await self.store.read(key)
        return value if isinstance(value, dict) else None

    async def put(self, key: str, value: dict[str, Any]) -> None:
        await self.store.write(key, value)

    async def clear_all(self) -> None:
        root = self.store.root
        if not root.exists():
            return
        for path in root.glob(f"*{self.store.suffix}"):
            path.unlink(missing_ok=True)
