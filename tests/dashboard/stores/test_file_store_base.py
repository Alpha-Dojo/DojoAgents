from __future__ import annotations

import asyncio
import json

import pytest

from dojoagents.sessions.atomic import (
    AtomicJsonStore,
    AtomicJsonlStore,
    CorruptStoreError,
    InvalidStoreKeyError,
    SchemaVersionError,
)


@pytest.mark.asyncio
async def test_json_store_writes_versioned_document_atomically(tmp_path) -> None:
    store = AtomicJsonStore(tmp_path, schema_version=2)

    await store.write("quotes/us", {"AAPL": 200})

    path = tmp_path / "quotes" / "us.json"
    assert json.loads(path.read_text(encoding="utf-8")) == {
        "schema_version": 2,
        "data": {"AAPL": 200},
    }
    assert await store.read("quotes/us") == {"AAPL": 200}
    assert list(tmp_path.rglob("*.tmp")) == []


@pytest.mark.asyncio
async def test_jsonl_store_round_trips_rows_with_version_header(tmp_path) -> None:
    store = AtomicJsonlStore(tmp_path, schema_version=3)

    await store.write("kline/us/AAPL", [{"date": "2026-06-20", "close": 200}])

    lines = (tmp_path / "kline" / "us" / "AAPL.jsonl").read_text(encoding="utf-8").splitlines()
    assert json.loads(lines[0]) == {"schema_version": 3}
    assert await store.read("kline/us/AAPL") == [{"date": "2026-06-20", "close": 200}]


@pytest.mark.asyncio
async def test_corrupt_document_is_preserved_and_never_replaced(tmp_path) -> None:
    path = tmp_path / "portfolio" / "p1.json"
    path.parent.mkdir(parents=True)
    path.write_text("{broken", encoding="utf-8")
    store = AtomicJsonStore(tmp_path, schema_version=1)

    with pytest.raises(CorruptStoreError, match="portfolio/p1"):
        await store.read("portfolio/p1")

    assert path.read_text(encoding="utf-8") == "{broken"


@pytest.mark.asyncio
async def test_schema_mismatch_is_explicit_and_source_is_preserved(tmp_path) -> None:
    path = tmp_path / "derived" / "scope.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"schema_version": 1, "data": {"value": 1}}), encoding="utf-8")
    store = AtomicJsonStore(tmp_path, schema_version=2)

    with pytest.raises(SchemaVersionError, match="expected 2, got 1"):
        await store.read("derived/scope")

    assert json.loads(path.read_text(encoding="utf-8"))["data"] == {"value": 1}


@pytest.mark.asyncio
async def test_invalidate_moves_rebuildable_cache_without_deleting_it(tmp_path) -> None:
    store = AtomicJsonStore(tmp_path, schema_version=1)
    await store.write("derived/scope", {"value": 1})

    invalid_path = await store.invalidate("derived/scope")

    assert invalid_path.exists()
    assert invalid_path.name.startswith("scope.json.invalid-")
    assert not (tmp_path / "derived" / "scope.json").exists()


@pytest.mark.asyncio
async def test_concurrent_same_key_writes_are_serialized_and_valid(tmp_path) -> None:
    store = AtomicJsonStore(tmp_path, schema_version=1)

    await asyncio.gather(*(store.write("working/quotes", {"value": i}) for i in range(20)))

    result = await store.read("working/quotes")
    assert result in ({"value": i} for i in range(20))
    assert list(tmp_path.rglob("*.tmp")) == []


@pytest.mark.asyncio
async def test_store_rejects_path_traversal_keys(tmp_path) -> None:
    store = AtomicJsonStore(tmp_path, schema_version=1)

    with pytest.raises(InvalidStoreKeyError):
        await store.write("../outside", {})
