from __future__ import annotations

import pytest

from dojoagents.sessions.models import (
    BeginRunCommand,
    SessionCreateSpec,
    SessionPrincipal,
    UsageQuery,
    UsageRecord,
)
from dojoagents.sessions.stores.file import FileSessionStore


@pytest.mark.asyncio
async def test_usage_can_be_appended_before_turn_commit_and_grouped(tmp_path):
    store = FileSessionStore(tmp_path / "sessions", cursor_secret=b"secret")
    principal = SessionPrincipal("alice")
    await store.startup()
    session = await store.create_session(
        principal,
        SessionCreateSpec("session-1", "financial", "1.0", 1),
    )
    handle = await store.begin_run_with_lease(
        principal,
        BeginRunCommand(
            "session-1",
            "run-1",
            "model-a",
            "run-idempotency",
            "worker-a",
        ),
    )
    records = (
        UsageRecord(
            usage_id="usage-1",
            session_uid=session.session_uid,
            run_id="run-1",
            provider="provider-a",
            model="model-a",
            input_tokens=10,
            output_tokens=2,
            idempotency_key="usage-idempotency-1",
            schema_version=2,
            turn_id="turn-1",
            invocation_id="invocation-1",
            invocation_index=1,
            category="agent_inference",
            operation="agent_inference",
            total_tokens=12,
            quality="actual",
        ),
        UsageRecord(
            usage_id="usage-2",
            session_uid=session.session_uid,
            run_id="run-1",
            provider="provider-a",
            model="model-a",
            input_tokens=3,
            output_tokens=1,
            idempotency_key="usage-idempotency-2",
            schema_version=2,
            turn_id="turn-1",
            invocation_id="invocation-2",
            invocation_index=2,
            category="turn_intent",
            operation="turn_intent.financial",
            total_tokens=4,
            quality="estimated",
        ),
    )

    assert (
        await store.append_usage(
            principal,
            "run-1",
            handle.lease,
            records,
        )
        == records
    )
    assert (
        await store.append_usage(
            principal,
            "run-1",
            handle.lease,
            records,
        )
        == records
    )

    summary = await store.get_usage(
        principal,
        "session-1",
        UsageQuery(group_by=("category",)),
    )
    assert summary.total_tokens == 16
    assert summary.calls == 2
    assert summary.actual_calls == 1
    assert summary.estimated_calls == 1
    assert {group.dimensions["category"]: group.totals.total_tokens for group in summary.groups} == {"agent_inference": 12, "turn_intent": 4}
