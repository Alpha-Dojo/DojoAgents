from __future__ import annotations

from datetime import UTC, datetime

import pytest

from dojoagents.sessions.errors import SessionConflictError, SessionNotFoundError
from dojoagents.sessions.models import (
    BeginRunCommand,
    BlobRef,
    CheckpointWrite,
    CommitTurnCommand,
    HistoryQuery,
    LeaseRequest,
    ObjectQuery,
    SessionCreateSpec,
    SessionEvent,
    SessionListQuery,
    SessionMessageRecord,
    SessionObjectSpec,
    SessionPatch,
    SessionPrincipal,
    SessionScope,
    TurnQuery,
    TurnRecord,
    UsageQuery,
    UsageRecord,
)


async def assert_session_store_contract(store) -> None:
    alice = SessionPrincipal(user_id="alice", tenant_id="tenant-a")
    bob = SessionPrincipal(user_id="bob", tenant_id="tenant-a")
    stranger = SessionPrincipal(user_id="stranger", tenant_id="tenant-a")
    spec = SessionCreateSpec(
        session_id="shared-external-id",
        harness_id="financial",
        harness_version="1.0",
        harness_state_schema_version=1,
        title="Alpha",
    )

    await store.startup()
    await store.startup()
    assert (await store.health()).healthy is True

    alice_session = await store.create_session(alice, spec)
    bob_session = await store.create_session(bob, spec)
    assert alice_session.session_uid != bob_session.session_uid
    assert (await store.get_session(alice, spec.session_id)).owner.user_id == "alice"
    assert (await store.get_session(bob, spec.session_id)).owner.user_id == "bob"
    with pytest.raises(SessionNotFoundError):
        await store.get_session(stranger, spec.session_id)
    assert [item.session_uid for item in (await store.list_sessions(alice, SessionListQuery())).items] == [alice_session.session_uid]

    updated = await store.update_session(
        alice,
        spec.session_id,
        SessionPatch(title="Updated"),
        expected_version=alice_session.version,
    )
    assert updated.title == "Updated"
    with pytest.raises(SessionConflictError):
        await store.update_session(alice, spec.session_id, SessionPatch(title="stale"), alice_session.version)

    lease = await store.acquire_lease(alice, LeaseRequest(spec.session_id, holder_id="worker-a"))
    with pytest.raises(SessionConflictError):
        await store.acquire_lease(alice, LeaseRequest(spec.session_id, holder_id="worker-b"))
    renewed = await store.renew_lease(alice, lease)
    assert renewed.fencing_token == lease.fencing_token

    run = await store.begin_run(
        alice,
        BeginRunCommand(
            session_id=spec.session_id,
            run_id="run-1",
            model="test-model",
            idempotency_key="run-idem-1",
            holder_id="worker-a",
        ),
    )
    duplicate_run = await store.begin_run(
        alice,
        BeginRunCommand(
            session_id=spec.session_id,
            run_id="run-1",
            model="test-model",
            idempotency_key="run-idem-1",
            holder_id="worker-a",
        ),
    )
    assert duplicate_run == run
    bob_run = await store.begin_run(
        bob,
        BeginRunCommand(
            session_id=spec.session_id,
            run_id="run-1",
            model="test-model",
            idempotency_key="run-idem-1",
            holder_id="worker-b",
        ),
    )
    assert bob_run.session_uid == bob_session.session_uid

    event = SessionEvent(
        run_id=run.run_id,
        sequence=1,
        event_type="content.delta",
        payload={"text": "hello"},
        lease_id=renewed.lease_id,
        fencing_token=renewed.fencing_token,
        idempotency_key="event-1",
    )
    await store.append_events(alice, run.run_id, [event, event])
    assert [item.sequence for item in (await store.read_events(alice, run.run_id, 0, 10)).items] == [1]

    now = datetime.now(UTC)
    turn = TurnRecord(
        session_uid=alice_session.session_uid,
        session_id=spec.session_id,
        run_id=run.run_id,
        turn_id="turn-1",
        sequence=1,
        input={"text": "hi"},
        output={"text": "hello"},
        created_at=now,
        updated_at=now,
    )
    messages = (
        SessionMessageRecord(
            session_uid=alice_session.session_uid,
            session_id=spec.session_id,
            agent_id="dojo-agent",
            sequence=1,
            role="user",
            content={"text": "hi"},
        ),
        SessionMessageRecord(
            session_uid=alice_session.session_uid,
            session_id=spec.session_id,
            agent_id="dojo-agent",
            sequence=2,
            role="assistant",
            content={"text": "hello"},
        ),
    )
    usage = (
        UsageRecord(
            usage_id="usage-1",
            session_uid=alice_session.session_uid,
            run_id=run.run_id,
            provider="static",
            model="test-model",
            input_tokens=3,
            output_tokens=2,
            idempotency_key="usage-idem-1",
        ),
    )
    command = CommitTurnCommand(run_id=run.run_id, lease=renewed, turn=turn, messages=messages, usage=usage)
    assert await store.commit_turn(alice, command) == turn
    assert await store.commit_turn(alice, command) == turn
    assert len((await store.load_history(alice, spec.session_id, HistoryQuery())).items) == 2
    assert len((await store.list_turns(alice, spec.session_id, TurnQuery())).items) == 1
    assert (await store.get_usage(alice, spec.session_id, UsageQuery())).input_tokens == 3

    checkpoint = await store.put_checkpoint(
        alice,
        CheckpointWrite(spec.session_id, "harness:financial", "state", {"portfolio_id": "p-1"}),
        expected_version=None,
    )
    assert checkpoint.version == 1
    with pytest.raises(SessionConflictError):
        await store.put_checkpoint(
            alice,
            CheckpointWrite(spec.session_id, "harness:financial", "state", {}),
            expected_version=0,
        )
    assert (await store.get_checkpoint(alice, spec.session_id, "harness:financial", "state")) == checkpoint

    reserved = await store.reserve_object(
        alice,
        SessionObjectSpec(spec.session_id, "artifact", "report.json", "application/json"),
    )
    blob_ref = BlobRef(blob_id="blob-1", owner=SessionScope.from_principal(alice), state="committed")
    committed = await store.commit_object(alice, reserved.object_id, blob_ref, reserved.version)
    assert committed.status == "committed"
    assert (await store.get_object(alice, reserved.object_id)).blob_ref == blob_ref
    assert len((await store.list_objects(alice, spec.session_id, ObjectQuery())).items) == 1
    deleted = await store.mark_object_deleted(alice, reserved.object_id, committed.version)
    assert deleted.status == "deleted"

    await store.release_lease(alice, renewed)
    next_lease = await store.acquire_lease(alice, LeaseRequest(spec.session_id, holder_id="worker-b"))
    assert next_lease.fencing_token > renewed.fencing_token
    await store.release_lease(alice, next_lease)
    await store.shutdown()
    await store.shutdown()
