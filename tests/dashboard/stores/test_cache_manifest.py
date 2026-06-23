from __future__ import annotations

import pytest

from dojoagents.dashboard.services.cache_manifest import CacheManifest


@pytest.mark.asyncio
async def test_manifest_persists_entries_and_invalid_state(tmp_path) -> None:
    manifest = CacheManifest(tmp_path, schema_version=4)

    await manifest.upsert(
        "kline:us:AAPL:1D:none",
        path="working-set/stock-kline/us/AAPL.jsonl",
        as_of="2026-06-20",
        source="sdk_online",
    )
    await manifest.mark_invalid("kline:us:AAPL:1D:none", reason="schema mismatch")

    reloaded = CacheManifest(tmp_path, schema_version=4)
    entry = await reloaded.get("kline:us:AAPL:1D:none")

    assert entry is not None
    assert entry["status"] == "invalid"
    assert entry["reason"] == "schema mismatch"
    assert entry["schema_version"] == 4


@pytest.mark.asyncio
async def test_manifest_returns_none_for_unknown_key(tmp_path) -> None:
    manifest = CacheManifest(tmp_path, schema_version=1)

    assert await manifest.get("missing") is None
