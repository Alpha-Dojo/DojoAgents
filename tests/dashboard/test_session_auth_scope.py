from __future__ import annotations

import asyncio
from types import SimpleNamespace

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from dojoagents.dashboard.routers.chat_sessions import router
from dojoagents.sessions.blobs.file import FileBlobStore
from dojoagents.sessions.models import (
    BeginRunCommand,
    ContextComponent,
    ContextUsageSnapshot,
    SessionCreateSpec,
    SessionPrincipal,
    UsageRecord,
    utc_now,
)
from dojoagents.sessions.service import SessionService
from dojoagents.sessions.stores.file import FileSessionStore
from dojoagents.config.models import SessionsConfig


class HeaderPrincipalProvider:
    async def resolve(self, request: Request):
        return SessionPrincipal(request.headers.get("x-user", "anonymous"))


def test_dashboard_session_ids_are_principal_scoped(tmp_path):
    store = FileSessionStore(tmp_path / "sessions", cursor_secret=b"auth-scope")
    blobs = FileBlobStore(tmp_path / "blobs")
    asyncio.run(store.startup())
    asyncio.run(blobs.startup())
    service = SessionService(store=store, blob_store=blobs, config=SessionsConfig())
    alice = SessionPrincipal("alice")
    asyncio.run(service.create_session(alice, SessionCreateSpec("private", "financial", "1.0.0", 1)))

    app = FastAPI()
    app.state.runtime = SimpleNamespace(sessions=service)
    app.state.principal_provider = HeaderPrincipalProvider()
    app.include_router(router, prefix="/api/v1")
    client = TestClient(app)
    try:
        visible = client.get("/api/v1/chat/sessions/private", headers={"x-user": "alice"})
        hidden = client.get("/api/v1/chat/sessions/private?user_id=alice", headers={"x-user": "bob"})
        listing = client.get("/api/v1/chat/sessions", headers={"x-user": "bob"})
    finally:
        asyncio.run(blobs.shutdown())
        asyncio.run(store.shutdown())

    assert visible.status_code == 200
    assert hidden.status_code == 404
    assert listing.json()["sessions"] == []


def test_dashboard_session_usage_groups_by_category(tmp_path):
    store = FileSessionStore(tmp_path / "sessions", cursor_secret=b"usage")
    blobs = FileBlobStore(tmp_path / "blobs")
    asyncio.run(store.startup())
    asyncio.run(blobs.startup())
    service = SessionService(
        store=store,
        blob_store=blobs,
        config=SessionsConfig(),
    )
    principal = SessionPrincipal("alice")
    session = asyncio.run(
        service.create_session(
            principal,
            SessionCreateSpec("usage-session", "financial", "1.0.0", 1),
        )
    )
    handle = asyncio.run(
        store.begin_run_with_lease(
            principal,
            BeginRunCommand(
                "usage-session",
                "run-usage",
                "model-a",
                "run-usage-idempotency",
                "worker-a",
            ),
        )
    )
    asyncio.run(
        store.append_usage(
            principal,
            "run-usage",
            handle.lease,
            (
                UsageRecord(
                    usage_id="usage-1",
                    session_uid=session.session_uid,
                    run_id="run-usage",
                    provider="provider-a",
                    model="model-a",
                    input_tokens=8,
                    output_tokens=2,
                    idempotency_key="usage-idempotency",
                    schema_version=2,
                    turn_id="turn-usage",
                    invocation_id="invocation-1",
                    invocation_index=1,
                    category="agent_inference",
                    total_tokens=10,
                    quality="actual",
                ),
            ),
        )
    )
    captured_at = utc_now()
    asyncio.run(
        store.append_context_usage(
            principal,
            "run-usage",
            handle.lease,
            (
                ContextUsageSnapshot(
                    snapshot_id="context-1",
                    session_uid=session.session_uid,
                    run_id="run-usage",
                    turn_id="turn-usage",
                    invocation_id="invocation-1",
                    invocation_index=1,
                    agent_id="dojo-agent",
                    harness_id="financial",
                    provider="provider-a",
                    model="model-a",
                    context_window_tokens=100,
                    estimated_input_tokens=7,
                    actual_input_tokens=8,
                    reconciliation_delta_tokens=1,
                    reserved_output_tokens=0,
                    quality="provider_reconciled",
                    components=(
                        ContextComponent(
                            component_id="system",
                            category="system_prompt",
                            source="harness:financial",
                            content_hash="hash",
                            estimated_tokens=7,
                            character_count=28,
                        ),
                    ),
                    captured_at=captured_at,
                    reconciled_at=captured_at,
                    idempotency_key="context-idempotency",
                    status="succeeded",
                ),
            ),
        )
    )

    app = FastAPI()
    app.state.runtime = SimpleNamespace(sessions=service, agent=None)
    app.state.principal_provider = HeaderPrincipalProvider()
    app.include_router(router, prefix="/api/v1")
    client = TestClient(app)
    try:
        response = client.get(
            "/api/v1/chat/sessions/usage-session/usage?group_by=category",
            headers={"x-user": "alice"},
        )
        context_only = client.get(
            "/api/v1/chat/sessions/usage-session/usage?view=context",
            headers={"x-user": "alice"},
        )
        hidden = client.get(
            "/api/v1/chat/sessions/usage-session/usage",
            headers={"x-user": "bob"},
        )
    finally:
        asyncio.run(blobs.shutdown())
        asyncio.run(store.shutdown())

    assert response.status_code == 200
    payload = response.json()
    assert payload["schema_version"] == 3
    assert payload["consumption"]["totals"]["total_tokens"] == 10
    assert payload["consumption"]["groups"][0]["dimensions"] == {"category": "agent_inference"}
    assert payload["consumption"]["turns"][0]["turn_id"] == "turn-usage"
    assert payload["context"]["latest"]["used_tokens"] == 8
    assert payload["context"]["latest"]["breakdown"][0]["category"] == ("system_prompt")
    assert "totals" not in payload
    assert context_only.status_code == 200
    assert context_only.json()["consumption"] is None
    assert context_only.json()["context"]["latest"]["used_tokens"] == 8
    assert hidden.status_code == 404
