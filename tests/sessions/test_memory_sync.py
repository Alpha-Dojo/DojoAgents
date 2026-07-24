import pytest

from dojoagents.config.models import SessionsConfig
from dojoagents.memory.manager import MemoryManager
from dojoagents.sessions.blobs.file import FileBlobStore
from dojoagents.sessions.memory_sync import SessionMemorySyncWorker
from dojoagents.sessions.models import SessionCreateSpec, SessionPrincipal, TurnQuery, TurnRecord, utc_now
from dojoagents.sessions.run_coordinator import RunCoordinator
from dojoagents.sessions.service import SessionService
from dojoagents.sessions.stores.file import FileSessionStore


class FailOnceProvider:
    name = "fail-once"

    def __init__(self):
        self.calls = []

    def is_available(self):
        return True

    async def initialize(self, session_id, **context):
        return None

    def system_prompt_block(self):
        return ""

    async def prefetch(self, query, *, session_id):
        return ""

    async def queue_prefetch(self, query, *, session_id):
        return None

    async def sync_turn(self, user_content, assistant_content, *, session_id, idempotency_context=None):
        self.calls.append(idempotency_context)
        if len(self.calls) == 1:
            raise RuntimeError("memory temporarily unavailable")

    async def on_session_end(self, messages):
        return None

    async def shutdown(self):
        return None


@pytest.mark.asyncio
async def test_memory_sync_retries_without_rolling_back_turn_or_advancing_watermark(tmp_path):
    service = SessionService(
        store=FileSessionStore(tmp_path / "sessions", cursor_secret=b"secret"),
        blob_store=FileBlobStore(tmp_path / "blobs"),
        config=SessionsConfig(),
    )
    principal = SessionPrincipal("alice")
    await service.startup()
    session = await service.create_session(principal, SessionCreateSpec("s1", "financial", "1.0", 1))
    coordinator = RunCoordinator(service, principal, "s1", holder_id="worker", model="test-model")
    await coordinator.begin("run-1", idempotency_key="run-idem")
    now = utc_now()
    turn = TurnRecord(
        session.session_uid,
        "s1",
        "run-1",
        "turn-stable-id",
        1,
        {"text": "user question"},
        {"text": "assistant answer"},
        created_at=now,
        updated_at=now,
    )
    await coordinator.commit(turn)
    provider = FailOnceProvider()
    manager = MemoryManager()
    manager.add_provider(provider)
    worker = SessionMemorySyncWorker(service, manager)

    with pytest.raises(RuntimeError, match="temporarily unavailable"):
        await worker.sync_pending(principal, "s1")

    assert len((await service.turns(principal, "s1", TurnQuery())).items) == 1
    assert await service.get_checkpoint(principal, "s1", "memory", "sync_watermark") is None

    assert await worker.sync_pending(principal, "s1") == 1
    assert await worker.sync_pending(principal, "s1") == 0
    checkpoint = await service.get_checkpoint(principal, "s1", "memory", "sync_watermark")
    assert checkpoint.payload == {"last_turn_id": "turn-stable-id", "last_turn_sequence": 1}
    assert (
        provider.calls[0]
        == provider.calls[1]
        == {
            "idempotency_key": "turn-stable-id",
            "turn_id": "turn-stable-id",
        }
    )
    assert len(manager.turns) == 1
