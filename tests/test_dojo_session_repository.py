from strands.types.session import Session, SessionAgent, SessionMessage, SessionType

from dojoagents.agent.session_repository import DojoSessionRepository


def test_dojo_session_repository_persists_strands_session_agent_and_messages(tmp_path):
    repo = DojoSessionRepository(tmp_path)
    session = repo.create_session(Session(session_id="sess-1", session_type=SessionType.AGENT))

    assert session.session_id == "sess-1"
    assert repo.read_session("sess-1").session_id == "sess-1"

    agent = SessionAgent(
        agent_id="dojo-agent",
        state={"portfolio": "quality"},
        conversation_manager_state={"removed_message_count": 0},
    )
    repo.create_agent("sess-1", agent)

    loaded_agent = repo.read_agent("sess-1", "dojo-agent")
    assert loaded_agent is not None
    assert loaded_agent.state == {"portfolio": "quality"}

    repo.create_message(
        "sess-1",
        "dojo-agent",
        SessionMessage.from_message({"role": "user", "content": [{"text": "hello"}]}, 0),
    )
    repo.create_message(
        "sess-1",
        "dojo-agent",
        SessionMessage.from_message({"role": "assistant", "content": [{"text": "hi"}]}, 1),
    )

    messages = repo.list_messages("sess-1", "dojo-agent")
    assert [message.message_id for message in messages] == [0, 1]
    assert messages[0].to_message()["content"][0]["text"] == "hello"
    assert repo.list_messages("sess-1", "dojo-agent", limit=1, offset=1)[0].message_id == 1


def test_dojo_session_repository_rejects_path_traversal(tmp_path):
    repo = DojoSessionRepository(tmp_path)

    try:
        repo.read_session("../escape")
    except ValueError as exc:
        assert "session" in str(exc).lower()
    else:
        raise AssertionError("expected invalid session id to be rejected")
