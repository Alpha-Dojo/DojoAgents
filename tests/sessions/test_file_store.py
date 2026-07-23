import asyncio
from datetime import timedelta

import pytest

from dojoagents.sessions.errors import SessionConflictError, SessionDataCorruptError, SessionLeaseLostError
from dojoagents.sessions.models import (
    BeginRunCommand,
    LeaseRequest,
    SessionCreateSpec,
    SessionListQuery,
    SessionPatch,
    SessionPrincipal,
    SessionEvent,
)
from dojoagents.sessions.stores.file import FileSessionStore
from dojoagents.sessions.models import utc_now
from tests.sessions.store_contract import assert_session_store_contract


@pytest.mark.asyncio
async def test_file_session_store_satisfies_contract(tmp_path):
    store = FileSessionStore(tmp_path / "sessions", cursor_secret=b"test-cursor-secret")

    await assert_session_store_contract(store)


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
async def test_corrupt_file_store_is_rejected(tmp_path):
    root = tmp_path / "sessions"
    root.mkdir()
    (root / "state.json").write_text("{broken", encoding="utf-8")
    store = FileSessionStore(root, cursor_secret=b"secret")

    with pytest.raises(SessionDataCorruptError):
        await store.startup()
