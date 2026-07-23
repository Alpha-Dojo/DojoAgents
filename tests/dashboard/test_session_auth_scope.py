from __future__ import annotations

import asyncio
from types import SimpleNamespace

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from dojoagents.dashboard.routers.chat_sessions import router
from dojoagents.sessions.blobs.file import FileBlobStore
from dojoagents.sessions.models import SessionCreateSpec, SessionPrincipal
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
