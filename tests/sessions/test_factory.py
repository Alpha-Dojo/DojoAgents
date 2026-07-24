import sys
import types

import pytest

from dojoagents.config.models import StoreProviderConfig
from dojoagents.sessions.blobs.file import FileBlobStore
from dojoagents.sessions.errors import SessionStoreUnavailableError
from dojoagents.sessions.factory import create_blob_store, create_session_store, shutdown_stores
from dojoagents.sessions.models import StoreHealth
from dojoagents.sessions.stores.file import FileSessionStore


@pytest.mark.asyncio
async def test_factory_creates_and_starts_built_in_file_stores(tmp_path):
    session = await create_session_store(StoreProviderConfig(provider="file", options={"root": str(tmp_path / "s")}))
    blob = await create_blob_store(StoreProviderConfig(provider="file", options={"root": str(tmp_path / "b")}))

    assert isinstance(session, FileSessionStore)
    assert isinstance(blob, FileBlobStore)
    assert (await session.health()).healthy is True
    await shutdown_stores(blob, session)


@pytest.mark.asyncio
async def test_factory_loads_exact_custom_factory_with_copied_options(monkeypatch, tmp_path):
    module = types.ModuleType("project_session_adapter")
    received = []

    def create_store(options):
        received.append(options)
        options["mutated"] = True
        return FileSessionStore(tmp_path / "custom", cursor_secret=b"secret")

    module.create_store = create_store
    monkeypatch.setitem(sys.modules, module.__name__, module)
    options = {"dsn": "postgresql://secret", "pool_size": 4}

    store = await create_session_store(StoreProviderConfig(provider="postgresql", factory="project_session_adapter:create_store", options=options))

    assert isinstance(store, FileSessionStore)
    assert received[0] is not options
    assert "mutated" not in options


@pytest.mark.asyncio
async def test_factory_rejects_wrong_protocol_without_leaking_secret(monkeypatch):
    module = types.ModuleType("bad_adapter")
    module.create_store = lambda options: object()
    monkeypatch.setitem(sys.modules, module.__name__, module)

    with pytest.raises(TypeError) as exc:
        await create_session_store(
            StoreProviderConfig(
                provider="mysql",
                factory="bad_adapter:create_store",
                options={"dsn": "mysql://user:do-not-leak@db/sessions"},
            )
        )

    assert "do-not-leak" not in str(exc.value)


class UnhealthyFileStore(FileSessionStore):
    async def health(self):
        return StoreHealth(False, "test", 1, detail="unavailable")


@pytest.mark.asyncio
async def test_factory_shuts_down_store_when_health_check_fails(monkeypatch, tmp_path):
    module = types.ModuleType("unhealthy_adapter")
    store = UnhealthyFileStore(tmp_path / "unhealthy", cursor_secret=b"secret")
    module.create_store = lambda options: store
    monkeypatch.setitem(sys.modules, module.__name__, module)

    with pytest.raises(SessionStoreUnavailableError, match="unhealthy"):
        await create_session_store(StoreProviderConfig(provider="custom", factory="unhealthy_adapter:create_store"))

    assert store._started is False
