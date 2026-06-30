from pathlib import Path

from dojoagents.agent.models import AgentResponse, ChatRequest
from dojoagents.agent.session_manager import DojoAgentSessionManager


class RecordingMemory:
    def __init__(self):
        self.turns = []

    async def sync_turn(self, user_content: str, assistant_content: str, *, session_id: str):
        self.turns.append((session_id, user_content, assistant_content))


def test_session_manager_lists_messages_and_exports(tmp_path):
    memory = RecordingMemory()
    manager = DojoAgentSessionManager(root=tmp_path / "sessions", memory_manager=memory)
    request = ChatRequest(message="hello", user_id="u1", session_id="sess-1", channel="dashboard")

    handle = manager.begin_run_sync(request, model="fake-model", run_id="run-1")
    repo = manager.repository
    session_manager = manager.for_strands("sess-1", agent_id="dojo-agent")
    assert session_manager.session_id == "sess-1"

    repo.create_message(
        "sess-1",
        "dojo-agent",
        manager.message_from_text("user", "hello", 0),
    )
    repo.create_message(
        "sess-1",
        "dojo-agent",
        manager.message_from_text("assistant", "hi there", 1),
    )

    manager.finish_run_sync(
        handle,
        AgentResponse(
            content="hi there",
            session_id="sess-1",
            metadata={"usage": {"prompt_tokens": 1, "completion_tokens": 2, "total_tokens": 3}},
        ),
        events=[{"type": "done", "seq": 1}],
    )

    sessions = manager.list_sessions_sync()
    assert sessions.sessions[0].session_id == "sess-1"
    assert sessions.sessions[0].message_count == 2

    messages = manager.get_messages_sync("sess-1")
    assert [message.role for message in messages.messages] == ["user", "assistant"]
    assert messages.messages[1].content == "hi there"
    assert memory.turns == [("sess-1", "hello", "hi there")]

    export = manager.export_all_sync({"output_dir": str(tmp_path / "export")})
    export_dir = Path(export.export_dir)
    assert export.ok is True
    assert (export_dir / "sessions.json").exists()
    assert (export_dir / "messages.jsonl").exists()
    assert (export_dir / "transcripts" / "sess-1.md").exists()
