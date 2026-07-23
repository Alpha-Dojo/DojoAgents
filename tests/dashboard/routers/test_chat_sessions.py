from __future__ import annotations

from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from dojoagents.agent.models import AgentResponse, ChatRequest
from dojoagents.agent.session_manager import DojoAgentSessionManager


class FakeAgent:
    async def run(self, request, *, event_sink=None):
        return AgentResponse(content="ok", session_id=request.session_id)


class FakeRuntime:
    def __init__(self, sessions):
        self.agent = FakeAgent()
        self.sessions = sessions
        self.config_store = None
        self.extensions = MagicMock()
        self.extensions.status = MagicMock(return_value=[])
        self.scheduler = MagicMock()
        self.scheduler.list_jobs = MagicMock(return_value=[])


def _make_client(tmp_path):
    from dojoagents.dashboard.server import create_app

    sessions = DojoAgentSessionManager(root=tmp_path / "sessions")
    req = ChatRequest(message="hello", user_id="u1", session_id="sess-api", channel="dashboard")
    handle = sessions.begin_run_sync(req, model="fake-model", run_id="run-1")
    sessions.repository.create_message("sess-api", "dojo-agent", sessions.message_from_text("user", "hello", 0))
    sessions.repository.create_message("sess-api", "dojo-agent", sessions.message_from_text("assistant", "ok", 1))
    sessions.finish_run_sync(handle, AgentResponse(content="ok", session_id="sess-api"))
    return TestClient(create_app(FakeRuntime(sessions))), sessions


def test_chat_sessions_routes_list_get_messages_archive_and_export(tmp_path):
    client, sessions = _make_client(tmp_path)
    turns_path = sessions._turns_path("sess-api")
    turns_path.write_text(
        '{"turn_id":"turn-1","events":[{"type":"think_delta","text":"reason"},' '{"type":"tool_start","call_id":"call-1","tool":"search","arguments":{}}]}\n',
        encoding="utf-8",
    )

    list_response = client.get("/api/v1/chat/sessions")
    assert list_response.status_code == 200
    assert list_response.json()["sessions"][0]["session_id"] == "sess-api"

    detail_response = client.get("/api/v1/chat/sessions/sess-api")
    assert detail_response.status_code == 200
    assert detail_response.json()["message_count"] == 2

    messages_response = client.get("/api/v1/chat/sessions/sess-api/messages")
    assert messages_response.status_code == 200
    assert [item["role"] for item in messages_response.json()["messages"]] == ["user", "assistant"]
    assert messages_response.json()["turns"][0]["events"][1]["type"] == "tool_start"

    export_response = client.post(
        "/api/v1/chat/sessions/export",
        json={"output_dir": str(tmp_path / "export")},
    )
    assert export_response.status_code == 200
    assert export_response.json()["ok"] is True

    archive_response = client.post("/api/v1/chat/sessions/sess-api/archive")
    assert archive_response.status_code == 200
    assert archive_response.json()["archived"] is True

    hidden_response = client.get("/api/v1/chat/sessions")
    assert hidden_response.status_code == 200
    assert hidden_response.json()["sessions"] == []


def test_chat_sessions_missing_session_returns_404(tmp_path):
    client, _ = _make_client(tmp_path)

    response = client.get("/api/v1/chat/sessions/missing")

    assert response.status_code == 404
    assert "error" in response.json()
