from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dojoagents.dashboard.services.file_store_base import AtomicJsonStore


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class CacheManifest:
    def __init__(self, root: Path, *, schema_version: int) -> None:
        self.schema_version = schema_version
        self.store = AtomicJsonStore(root / "runtime", schema_version=schema_version)

    async def _load(self) -> dict[str, Any]:
        document = await self.store.read("cache-manifest")
        if not isinstance(document, dict):
            return {"entries": {}}
        entries = document.get("entries")
        if not isinstance(entries, dict):
            return {"entries": {}}
        return document

    async def upsert(self, key: str, **entry: Any) -> None:
        document = await self._load()
        entries = document.setdefault("entries", {})
        entries[key] = {
            **entry,
            "schema_version": self.schema_version,
            "status": "valid",
            "updated_at": _utc_now(),
        }
        await self.store.write("cache-manifest", document)

    async def mark_invalid(self, key: str, *, reason: str) -> None:
        document = await self._load()
        entries = document.setdefault("entries", {})
        current = entries.get(key) if isinstance(entries.get(key), dict) else {}
        entries[key] = {
            **current,
            "schema_version": self.schema_version,
            "status": "invalid",
            "reason": reason,
            "updated_at": _utc_now(),
        }
        await self.store.write("cache-manifest", document)

    async def get(self, key: str) -> dict[str, Any] | None:
        document = await self._load()
        entry = document.get("entries", {}).get(key)
        return dict(entry) if isinstance(entry, dict) else None
