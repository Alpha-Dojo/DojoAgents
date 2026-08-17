import json
from pathlib import Path

from dojoagents.agent.models import AgentResponse, ChatRequest
from dojoagents.agent.session_manager import DojoAgentSessionManager
from dojoagents.harnesses.built_in.financial.presenters.legacy_registry import (
    ToolResultPresenterRegistry,
)
from strands.types.session import SessionMessage


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
    assert (export_dir / "openai_dataset.jsonl").exists()
    assert (export_dir / "transcripts" / "sess-1.md").exists()


def test_session_manager_rebuilds_tool_result_viz_blocks_for_history(tmp_path):
    manager = DojoAgentSessionManager(
        root=tmp_path / "sessions",
        presenter_factory=ToolResultPresenterRegistry,
    )
    manager.for_strands("sess-viz", agent_id="dojo-agent")
    manager.repository.create_message(
        "sess-viz",
        "dojo-agent",
        SessionMessage.from_message(
            {
                "role": "user",
                "content": [
                    {
                        "toolResult": {
                            "status": "success",
                            "toolUseId": "call-list",
                            "name": "portfolio_read_list",
                            "content": [{"text": '[{"id":"p-1","name":"Core","kind":"manual","pinned":true}]'}],
                        }
                    }
                ],
            },
            0,
        ),
    )

    projected = manager.get_messages_sync("sess-viz").messages[0]

    assert projected.role == "tool"
    assert projected.tool_results[0]["call_id"] == "call-list"
    assert projected.tool_results[0]["data"]["items"][0]["id"] == "p-1"
    assert projected.tool_results[0]["viz_blocks"]
    assert projected.tool_results[0]["viz_blocks"][0]["source_tool"] == "portfolio_read_list"


def test_session_manager_rebuilds_missing_turn_trace_viz_blocks(tmp_path):
    manager = DojoAgentSessionManager(
        root=tmp_path / "sessions",
        presenter_factory=ToolResultPresenterRegistry,
    )
    turns_path = manager._turns_path("sess-trace")
    turns_path.parent.mkdir(parents=True, exist_ok=True)
    turns_path.write_text(
        json.dumps(
            {
                "turn_id": "turn-1",
                "events": [],
                "tool_trace": [
                    {
                        "call_id": "call-detail",
                        "tool": "portfolio_read_list",
                        "ok": True,
                        "data": {"items": [{"id": "p-1", "name": "Core", "kind": "manual", "pinned": True}]},
                        "viz_blocks": [],
                    }
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )

    turns = manager.get_turns_sync("sess-trace")

    assert turns[0]["tool_trace"][0]["viz_blocks"]
    assert turns[0]["tool_trace"][0]["viz_blocks"][0]["source_tool"] == "portfolio_read_list"


def test_session_manager_exports_one_session_by_id(tmp_path):
    manager = DojoAgentSessionManager(root=tmp_path / "sessions")
    repo = manager.repository

    first = manager.begin_run_sync(ChatRequest(message="first", user_id="u1", session_id="sess-1"), model="fake-model")
    manager.for_strands("sess-1", agent_id="dojo-agent")
    repo.create_message("sess-1", "dojo-agent", manager.message_from_text("user", "first", 0))
    manager.finish_run_sync(first, AgentResponse(content="first done", session_id="sess-1"))

    second = manager.begin_run_sync(ChatRequest(message="second", user_id="u1", session_id="sess-2"), model="fake-model")
    manager.for_strands("sess-2", agent_id="dojo-agent")
    repo.create_message("sess-2", "dojo-agent", manager.message_from_text("user", "second", 0))
    manager.finish_run_sync(second, AgentResponse(content="second done", session_id="sess-2"))

    export = manager.export_all_sync(
        {
            "output_dir": str(tmp_path / "export"),
            "session_id": "sess-2",
            "include_raw_strands": True,
        }
    )
    export_dir = Path(export.export_dir)
    sessions = json.loads((export_dir / "sessions.json").read_text(encoding="utf-8"))
    message_rows = [json.loads(line) for line in (export_dir / "messages.jsonl").read_text(encoding="utf-8").splitlines()]

    assert export.session_count == 1
    assert sessions[0]["session_id"] == "sess-2"
    assert {row["session_id"] for row in message_rows} == {"sess-2"}
    assert (export_dir / "transcripts" / "sess-2.md").exists()
    assert not (export_dir / "transcripts" / "sess-1.md").exists()
    assert (export_dir / "strands" / "session_sess-2").exists()
    assert not (export_dir / "strands" / "session_sess-1").exists()


def test_session_manager_projects_tool_messages_to_openai_format(tmp_path):
    manager = DojoAgentSessionManager(root=tmp_path / "sessions")
    request = ChatRequest(message="lookup", user_id="u1", session_id="sess-tools", channel="dashboard")
    handle = manager.begin_run_sync(request, model="fake-model", run_id="run-1")
    repo = manager.repository
    manager.for_strands("sess-tools", agent_id="dojo-agent")

    repo.create_message(
        "sess-tools",
        "dojo-agent",
        SessionMessage.from_message(
            {
                "role": "assistant",
                "content": [
                    {"text": "I will search."},
                    {
                        "toolUse": {
                            "toolUseId": "call_123",
                            "name": "search_company_ticker",
                            "input": {"query": "小米"},
                        }
                    },
                ],
            },
            0,
        ),
    )
    repo.create_message(
        "sess-tools",
        "dojo-agent",
        SessionMessage.from_message(
            {
                "role": "user",
                "content": [
                    {
                        "toolResult": {
                            "status": "success",
                            "toolUseId": "call_123",
                            "name": "search_company_ticker",
                            "content": [{"text": '{"ticker":"1810.HK"}'}],
                        }
                    }
                ],
            },
            1,
        ),
    )

    manager.finish_run_sync(handle, AgentResponse(content="done", session_id="sess-tools"))

    messages = manager.get_messages_sync("sess-tools").messages
    assert messages[0].raw == {
        "role": "assistant",
        "content": "I will search.",
        "tool_calls": [
            {
                "id": "call_123",
                "type": "function",
                "function": {
                    "name": "search_company_ticker",
                    "arguments": '{"query": "小米"}',
                },
            }
        ],
    }
    assert messages[1].raw == {
        "role": "tool",
        "tool_call_id": "call_123",
        "name": "search_company_ticker",
        "content": '{"ticker":"1810.HK"}',
    }

    export = manager.export_all_sync({"output_dir": str(tmp_path / "export")})
    dataset_path = Path(export.export_dir) / "openai_dataset.jsonl"
    [dataset_row] = [json.loads(line) for line in dataset_path.read_text(encoding="utf-8").splitlines()]
    assert dataset_row["messages"] == [messages[0].raw, messages[1].raw]
