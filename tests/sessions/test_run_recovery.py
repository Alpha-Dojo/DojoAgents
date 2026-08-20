from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from dojoagents.sessions.models import (
    BeginRunCommand,
    CommitTurnCommand,
    HistoryQuery,
    SessionCreateSpec,
    SessionMessageRecord,
    SessionPrincipal,
    TurnRecord,
)
from dojoagents.sessions.stores.file import FileSessionStore


@pytest.mark.asyncio
async def test_pending_messages_are_the_single_recovery_source_then_commit_in_place(
    tmp_path,
):
    store = FileSessionStore(tmp_path, cursor_secret=b"secret")
    await store.startup()
    principal = SessionPrincipal("alice")
    session = await store.create_session(
        principal,
        SessionCreateSpec("session-1", "harness", "1", 1),
    )
    deadline = datetime.now(UTC) + timedelta(minutes=5)
    initial = SessionMessageRecord(
        session_uid=session.session_uid,
        session_id=session.session_id,
        agent_id="dojo-agent",
        sequence=0,
        role="user",
        content="hello",
        message_id="turn-1:message:0",
        run_id="run-1",
        turn_id="turn-1",
        state="pending",
        boundary_kind="user_input",
    )
    first = await store.begin_run_with_lease(
        principal,
        BeginRunCommand(
            "session-1",
            "run-1",
            "model",
            "idem",
            "worker-1",
            recoverable=True,
            request={"schema_version": 1, "message": "hello"},
            deadline_at=deadline,
            initial_messages=(initial,),
        ),
    )

    assert (await store.load_history(principal, "session-1", HistoryQuery())).items == ()
    pending = await store.load_run_messages(principal, "run-1")
    assert [item.content for item in pending] == ["hello"]
    assert pending[0].state == "pending"

    assistant = replace(
        initial,
        role="assistant",
        content="world",
        message_id="turn-1:message:1",
        boundary_kind="final_assistant",
    )
    await store.append_run_messages(
        principal,
        "run-1",
        first.lease,
        (assistant,),
    )
    await store.commit_turn(
        principal,
        CommitTurnCommand(
            "run-1",
            first.lease,
            TurnRecord(
                session.session_uid,
                session.session_id,
                "run-1",
                "turn-1",
                1,
                {"message": "hello"},
                {"content": "world"},
            ),
        ),
    )

    history = await store.load_history(principal, "session-1", HistoryQuery())
    assert [item.content for item in history.items] == ["hello", "world"]
    assert all(item.state == "committed" for item in history.items)
    assert (await store.load_run_messages(principal, "run-1")) == ()
    events = await store.read_events(principal, "run-1", 0, 10)
    assert events.items[-1].event_type == "done"


@pytest.mark.asyncio
async def test_mutation_running_under_old_fence_becomes_unknown_on_takeover(tmp_path):
    store = FileSessionStore(tmp_path, cursor_secret=b"secret")
    await store.startup()
    principal = SessionPrincipal("alice")
    await store.create_session(
        principal,
        SessionCreateSpec("session-1", "harness", "1", 1),
    )
    first = await store.begin_run_with_lease(
        principal,
        BeginRunCommand("session-1", "run-1", "model", "idem", "worker-1"),
    )
    started = await store.start_run_tool(
        principal,
        "run-1",
        first.lease,
        "call-1",
        "portfolio.create",
        {"name": "demo"},
        True,
    )
    assert started.state == "running"
    await store.release_lease(principal, first.lease)

    second = await store.begin_run_with_lease(
        principal,
        BeginRunCommand("session-1", "run-1", "model", "idem", "worker-2"),
    )
    assert second.lease.fencing_token > first.lease.fencing_token
    recovered = await store.start_run_tool(
        principal,
        "run-1",
        second.lease,
        "call-1",
        "portfolio.create",
        {"name": "demo"},
        True,
    )
    assert recovered.state == "unknown"
