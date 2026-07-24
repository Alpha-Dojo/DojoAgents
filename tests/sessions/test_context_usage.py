from __future__ import annotations

from datetime import timedelta

import pytest

from dojoagents.sessions.models import (
    BeginRunCommand,
    ContextComponent,
    ContextUsageQuery,
    ContextUsageSnapshot,
    SessionCreateSpec,
    SessionPrincipal,
    utc_now,
)
from dojoagents.sessions.errors import SessionNotFoundError
from dojoagents.sessions.stores.file import FileSessionStore


def _snapshot(
    session_uid: str,
    index: int,
    tokens: int,
    *,
    invocation_category: str = "agent_inference",
):
    now = utc_now() + timedelta(seconds=index)
    component = ContextComponent(
        component_id=f"conversation:{index}",
        category="conversation",
        source="conversation:history.user",
        content_hash=f"hash-{index}",
        estimated_tokens=tokens,
        character_count=tokens * 4,
    )
    return ContextUsageSnapshot(
        snapshot_id=f"snapshot-{index}",
        session_uid=session_uid,
        run_id="run-1",
        turn_id="turn-1" if index < 3 else "turn-2",
        invocation_id=f"invocation-{index}",
        invocation_index=index,
        agent_id="dojo-agent",
        harness_id="financial",
        provider="provider-a",
        model="model-a",
        context_window_tokens=1000,
        estimated_input_tokens=tokens,
        actual_input_tokens=tokens,
        reconciliation_delta_tokens=0,
        reserved_output_tokens=0,
        quality="provider_reconciled",
        components=(component,),
        captured_at=now,
        reconciled_at=now,
        idempotency_key=f"context:{index}",
        invocation_category=invocation_category,
        operation=invocation_category,
        status="succeeded",
    )


@pytest.mark.asyncio
async def test_file_store_persists_context_latest_and_peaks(tmp_path):
    store = FileSessionStore(tmp_path, cursor_secret=b"context")
    await store.startup()
    principal = SessionPrincipal("alice")
    session = await store.create_session(
        principal,
        SessionCreateSpec("session-1", "financial", "1", 1),
    )
    handle = await store.begin_run_with_lease(
        principal,
        BeginRunCommand(
            "session-1",
            "run-1",
            "model-a",
            "run-key",
            "worker-a",
        ),
    )
    snapshots = (
        _snapshot(session.session_uid, 1, 100),
        _snapshot(session.session_uid, 2, 250),
        _snapshot(session.session_uid, 3, 150),
        _snapshot(
            session.session_uid,
            4,
            900,
            invocation_category="write_guard",
        ),
    )
    persisted = await store.append_context_usage(
        principal,
        "run-1",
        handle.lease,
        snapshots,
    )
    replayed = await store.append_context_usage(
        principal,
        "run-1",
        handle.lease,
        snapshots,
    )
    summary = await store.get_context_usage(
        principal,
        "session-1",
        ContextUsageQuery(include_history=True, limit=2),
    )

    assert persisted == replayed
    assert summary.latest == snapshots[2]
    assert summary.turn_peak == snapshots[2]
    assert summary.session_peak == snapshots[1]
    assert summary.history == snapshots[:2]
    assert summary.next_cursor is not None
    with pytest.raises(SessionNotFoundError):
        await store.get_context_usage(
            SessionPrincipal("bob"),
            "session-1",
            ContextUsageQuery(),
        )


@pytest.mark.asyncio
async def test_context_retention_keeps_turn_peak_and_idempotency_history(
    tmp_path,
):
    store = FileSessionStore(
        tmp_path,
        cursor_secret=b"context",
        context_usage_history_limit=2,
    )
    await store.startup()
    principal = SessionPrincipal("alice")
    session = await store.create_session(
        principal,
        SessionCreateSpec("session-1", "financial", "1", 1),
    )
    handle = await store.begin_run_with_lease(
        principal,
        BeginRunCommand(
            "session-1",
            "run-1",
            "model-a",
            "run-key",
            "worker-a",
        ),
    )
    snapshots = (
        _snapshot(session.session_uid, 1, 100),
        _snapshot(session.session_uid, 2, 500),
        _snapshot(session.session_uid, 3, 200),
        _snapshot(session.session_uid, 4, 150),
    )
    await store.append_context_usage(
        principal,
        "run-1",
        handle.lease,
        snapshots,
    )
    replayed = await store.append_context_usage(
        principal,
        "run-1",
        handle.lease,
        (snapshots[0],),
    )
    summary = await store.get_context_usage(
        principal,
        "session-1",
        ContextUsageQuery(include_history=True, limit=10),
    )

    assert replayed == (snapshots[0],)
    assert [item.snapshot_id for item in summary.history] == [
        "snapshot-2",
        "snapshot-3",
        "snapshot-4",
    ]
