import asyncio
import json
import shutil
from datetime import timedelta

import pytest

from dojoagents.sessions.errors import SessionConflictError, SessionDataCorruptError, SessionLeaseLostError
from dojoagents.sessions.models import (
    BeginRunCommand,
    HistoryQuery,
    LeaseRequest,
    SessionCreateSpec,
    SessionListQuery,
    SessionPatch,
    SessionPrincipal,
    SessionEvent,
    utc_now,
)
from dojoagents.sessions.stores.file import FileSessionStore
from tests.sessions.store_contract import assert_session_store_contract


@pytest.mark.asyncio
async def test_file_session_store_satisfies_contract(tmp_path):
    root = tmp_path / "sessions"
    store = FileSessionStore(root, cursor_secret=b"test-cursor-secret")

    await assert_session_store_contract(store)

    state = json.loads((root / "state.json").read_text(encoding="utf-8"))["data"]
    assert "messages" not in state
    assert sum(len(items) for items in state["message_index"].values()) == 2
    paths = sorted((root / "session_shared-external-id" / "agents" / "agent_dojo-agent" / "messages").glob("message_*.json"))
    assert [path.name for path in paths] == ["message_1.json", "message_2.json"]
    first = json.loads(paths[0].read_text(encoding="utf-8"))
    assert first["message"] == {"role": "user", "content": [{"text": "hi"}]}
    assert first["dojo_canonical"]["content"] == {"text": "hi"}


@pytest.mark.asyncio
async def test_startup_migrates_legacy_state_messages_into_session_files(tmp_path):
    root = tmp_path / "sessions"
    store = FileSessionStore(root, cursor_secret=b"test-cursor-secret")
    await assert_session_store_contract(store)

    state_path = root / "state.json"
    document = json.loads(state_path.read_text(encoding="utf-8"))
    state = document["data"]
    session_uid, refs = next((uid, refs) for uid, refs in state["message_index"].items() if refs)
    message_root = root / state["message_roots"][session_uid]
    legacy_messages = [json.loads(path.read_text(encoding="utf-8"))["dojo_canonical"] for path in sorted(message_root.glob("agents/*/messages/message_*.json"))]
    state["messages"] = {session_uid: legacy_messages}
    state.pop("message_index")
    state.pop("message_roots")
    state_path.write_text(json.dumps(document), encoding="utf-8")
    shutil.rmtree(message_root)

    migrated = FileSessionStore(root, cursor_secret=b"test-cursor-secret")
    await migrated.startup()
    principal = SessionPrincipal(user_id="alice", tenant_id="tenant-a")
    history = await migrated.load_history(principal, "shared-external-id", HistoryQuery())

    assert [item.sequence for item in history.items] == [1, 2]
    migrated_state = json.loads(state_path.read_text(encoding="utf-8"))["data"]
    assert "messages" not in migrated_state
    assert len(migrated_state["message_index"][session_uid]) == 2
    migrated_root = root / migrated_state["message_roots"][session_uid]
    assert sorted(path.name for path in migrated_root.glob("agents/*/messages/message_*.json")) == ["message_1.json", "message_2.json"]


@pytest.mark.asyncio
async def test_same_external_session_id_uses_distinct_message_roots_per_owner(tmp_path):
    root = tmp_path / "sessions"
    store = FileSessionStore(root, cursor_secret=b"test-cursor-secret")
    await assert_session_store_contract(store)

    state_path = root / "state.json"
    document = json.loads(state_path.read_text(encoding="utf-8"))
    state = document["data"]
    alice_uid = next(uid for uid, data in state["sessions"].items() if data["owner"]["user_id"] == "alice")
    bob_uid = next(uid for uid, data in state["sessions"].items() if data["owner"]["user_id"] == "bob")
    alice_root = root / state["message_roots"][alice_uid]
    bob_message = json.loads((alice_root / "agents" / "agent_dojo-agent" / "messages" / "message_1.json").read_text(encoding="utf-8"))["dojo_canonical"]
    bob_message["session_uid"] = bob_uid
    state["messages"] = {bob_uid: [bob_message]}
    state_path.write_text(json.dumps(document), encoding="utf-8")

    migrated = FileSessionStore(root, cursor_secret=b"test-cursor-secret")
    await migrated.startup()
    history = await migrated.load_history(SessionPrincipal(user_id="bob", tenant_id="tenant-a"), "shared-external-id", HistoryQuery())
    migrated_state = json.loads(state_path.read_text(encoding="utf-8"))["data"]

    assert len(history.items) == 1
    assert migrated_state["message_roots"][bob_uid] != migrated_state["message_roots"][alice_uid]
    assert migrated_state["message_roots"][bob_uid].startswith("session_shared-external-id__")


def _spec(session_id: str):
    return SessionCreateSpec(session_id, "financial", "1.0", 1, title=session_id)


@pytest.mark.asyncio
async def test_two_file_store_instances_serialize_updates_and_paginate_stably(tmp_path):
    root = tmp_path / "sessions"
    first = FileSessionStore(root, cursor_secret=b"secret")
    second = FileSessionStore(root, cursor_secret=b"secret")
    principal = SessionPrincipal(user_id="alice")
    await first.startup()
    await second.startup()
    created = await asyncio.gather(
        first.create_session(principal, _spec("one")),
        second.create_session(principal, _spec("two")),
        first.create_session(principal, _spec("three")),
    )

    page_one = await first.list_sessions(principal, SessionListQuery(limit=2))
    page_two = await second.list_sessions(principal, SessionListQuery(limit=2, cursor=page_one.next_cursor))
    assert len(page_one.items) == 2
    assert len(page_two.items) == 1
    assert {item.session_uid for item in (*page_one.items, *page_two.items)} == {item.session_uid for item in created}

    current = await first.get_session(principal, "one")
    results = await asyncio.gather(
        first.update_session(principal, "one", SessionPatch(title="first"), current.version),
        second.update_session(principal, "one", SessionPatch(title="second"), current.version),
        return_exceptions=True,
    )
    assert sum(isinstance(result, SessionConflictError) for result in results) == 1


@pytest.mark.asyncio
async def test_expired_lease_takeover_invalidates_old_fencing_token(tmp_path, monkeypatch):
    import dojoagents.sessions.stores.file as file_module

    root = tmp_path / "sessions"
    first = FileSessionStore(root, cursor_secret=b"secret")
    second = FileSessionStore(root, cursor_secret=b"secret")
    principal = SessionPrincipal(user_id="alice")
    await first.startup()
    await first.create_session(principal, _spec("session"))
    started = utc_now()
    monkeypatch.setattr(file_module, "utc_now", lambda: started)
    old = await first.acquire_lease(principal, LeaseRequest("session", "worker-a", lease_seconds=10))
    await first.begin_run(
        principal,
        BeginRunCommand("session", "run-old", "test-model", "run-old-idem", "worker-a", lease_seconds=10),
    )
    monkeypatch.setattr(file_module, "utc_now", lambda: started + timedelta(seconds=11))

    replacement = await second.acquire_lease(principal, LeaseRequest("session", "worker-b", lease_seconds=10))

    assert replacement.fencing_token > old.fencing_token
    with pytest.raises(SessionLeaseLostError):
        await first.renew_lease(principal, old)
    with pytest.raises(SessionLeaseLostError):
        await first.append_events(
            principal,
            "run-old",
            [SessionEvent("run-old", 1, "content.delta", {"text": "stale"}, old.lease_id, old.fencing_token)],
        )


@pytest.mark.asyncio
async def test_same_holder_can_renew_and_append_after_lease_expires(tmp_path, monkeypatch):
    """Regression: expired lease used to make heartbeat cancel long agent runs."""
    import dojoagents.sessions.stores.file as file_module

    root = tmp_path / "sessions"
    store = FileSessionStore(root, cursor_secret=b"secret")
    principal = SessionPrincipal(user_id="alice")
    await store.startup()
    await store.create_session(principal, _spec("session"))
    started = utc_now()
    monkeypatch.setattr(file_module, "utc_now", lambda: started)
    handle = await store.begin_run_with_lease(
        principal,
        BeginRunCommand("session", "run-1", "test-model", "idem-1", "worker-a", lease_seconds=10),
    )
    monkeypatch.setattr(file_module, "utc_now", lambda: started + timedelta(seconds=11))

    renewed = await store.renew_lease(principal, handle.lease)
    assert renewed.lease_id == handle.lease.lease_id
    assert renewed.fencing_token == handle.lease.fencing_token
    assert renewed.expires_at > started + timedelta(seconds=11)

    await store.append_events(
        principal,
        "run-1",
        [
            SessionEvent(
                "run-1",
                1,
                "content.delta",
                {"text": "still-alive"},
                renewed.lease_id,
                renewed.fencing_token,
            )
        ],
    )


@pytest.mark.asyncio
async def test_corrupt_file_store_is_rejected(tmp_path):
    root = tmp_path / "sessions"
    root.mkdir()
    (root / "state.json").write_text("{broken", encoding="utf-8")
    store = FileSessionStore(root, cursor_secret=b"secret")

    with pytest.raises(SessionDataCorruptError):
        await store.startup()


@pytest.mark.asyncio
async def test_empty_unversioned_state_is_initialized(tmp_path):
    root = tmp_path / "sessions"
    root.mkdir()
    (root / "state.json").write_text("{}\n", encoding="utf-8")
    store = FileSessionStore(root, cursor_secret=b"secret")

    await store.startup()

    document = json.loads((root / "state.json").read_text(encoding="utf-8"))
    assert document["schema_version"] == 1
    assert document["data"] == store._empty_state()


@pytest.mark.asyncio
async def test_nonempty_unversioned_state_is_rejected(tmp_path):
    root = tmp_path / "sessions"
    root.mkdir()
    (root / "state.json").write_text('{"sessions": {}}\n', encoding="utf-8")
    store = FileSessionStore(root, cursor_secret=b"secret")

    with pytest.raises(SessionDataCorruptError, match="missing versioned document envelope"):
        await store.startup()
