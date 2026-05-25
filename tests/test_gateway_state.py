import tempfile
from pathlib import Path
import pytest

from dojoagents.agent.models import ChatRequest
from dojoagents.gateway.state import GatewaySessionStore, GatewaySession
from dojoagents.gateway.adapters.base import GatewayEvent


def test_sqlite_session_store_lifecycle():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "state.db"
        store = GatewaySessionStore(db_path)

        # 1. Test ensure and get
        event = GatewayEvent(
            platform="telegram",
            target="123",
            user_id="45",
            text="hello",
        )
        session = store.ensure(event)
        assert session.key == "telegram:123:45"
        assert session.platform == "telegram"
        assert session.target == "123"
        assert session.user_id == "45"
        assert session.status == "idle"

        retrieved = store.get(session.key)
        assert retrieved.key == session.key
        assert retrieved.status == "idle"

        # 2. Test status and model updates
        store.set_status(session.key, "active")
        assert store.get(session.key).status == "active"

        store.set_model(session.key, "gpt-4o")
        assert store.get(session.key).model_override == "gpt-4o"

        # 3. Test ensure updates timestamp but keeps settings
        session2 = store.ensure(event)
        assert session2.model_override == "gpt-4o"

        # 4. Test clear
        store.clear(session.key)
        with pytest.raises(KeyError):
            store.get(session.key)


def test_sqlite_session_store_transcripts():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "state.db"
        store = GatewaySessionStore(db_path)

        session_key = "telegram:123:45"
        # Populate session first
        event = GatewayEvent(
            platform="telegram",
            target="123",
            user_id="45",
            text="hello",
        )
        store.ensure(event)

        # Add transcripts
        store.add_transcript(session_key, "user", "What is the capital of France?")
        store.add_transcript(session_key, "assistant", "Paris is the capital of France.")
        store.add_transcript(session_key, "user", "Thank you!")

        # Retrieve history
        history = store.get_history(session_key, limit=2)
        # Limit is 2, so should return the last 2 messages (assistant and user) in chronological order
        assert len(history) == 2
        assert history[0]["role"] == "assistant"
        assert history[0]["content"] == "Paris is the capital of France."
        assert history[1]["role"] == "user"
        assert history[1]["content"] == "Thank you!"

        # Full history
        full_history = store.get_history(session_key, limit=10)
        assert len(full_history) == 3
        assert full_history[0]["role"] == "user"
        assert full_history[0]["content"] == "What is the capital of France?"


@pytest.mark.asyncio
async def test_agent_loop_prepends_history_from_request_metadata():
    from dojoagents.agent.loop import AgentLoop
    from dojoagents.agent.providers import StaticLLMProvider
    from dojoagents.agent.models import LLMResult
    from dojoagents.config.models import AgentConfig
    from dojoagents.dojo_extensions.registry import DojoExtensionRegistry
    from dojoagents.memory.manager import MemoryManager
    from dojoagents.skills.manager import SkillManager
    from dojoagents.tools.executor import ToolExecutor
    from unittest.mock import MagicMock

    llm = StaticLLMProvider([LLMResult(content="Mocked answer")])
    # Setup dummy dependencies
    tool_executor = MagicMock()
    tool_executor.registry = MagicMock()
    tool_executor.registry.schema_list.return_value = []
    skill_manager = MagicMock(spec=SkillManager)
    skill_manager.prompt_block.return_value = "SkillPrompt"
    memory_manager = MagicMock(spec=MemoryManager)
    memory_manager.build_system_prompt.return_value = "MemoryPrompt"
    memory_manager.prefetch_all.return_value = "PrefetchedMemories"
    extension_registry = MagicMock(spec=DojoExtensionRegistry)

    config = AgentConfig(model="mock-model", max_iterations=5)

    loop = AgentLoop(
        llm_provider=llm,
        tool_executor=tool_executor,
        skill_manager=skill_manager,
        memory_manager=memory_manager,
        extension_registry=extension_registry,
        config=config,
    )

    history = [
        {"role": "user", "content": "Hello!"},
        {"role": "assistant", "content": "Hi there, how can I help you today?"},
    ]

    request = ChatRequest(
        message="What is Paris?",
        user_id="user1",
        session_id="session1",
        metadata={"history": history},
    )

    await loop.run(request)

    # Inspect messages sent to the LLM
    assert len(llm.calls) == 1
    messages = llm.calls[0]["messages"]
    
    # Assert system prompt is present
    assert messages[0]["role"] == "system"
    # Assert history was prepended
    assert messages[1]["role"] == "user"
    assert messages[1]["content"] == "Hello!"
    assert messages[2]["role"] == "assistant"
    assert messages[2]["content"] == "Hi there, how can I help you today?"
    # Assert current query is last
    assert messages[3]["role"] == "user"
    assert messages[3]["content"] == "What is Paris?"


@pytest.mark.asyncio
async def test_gateway_runner_sqlite_integration(tmp_path):
    from dojoagents.agent.models import AgentResponse
    from dojoagents.gateway.registry import GatewayRegistry, PlatformEntry
    from dojoagents.gateway.runner import GatewayRunner

    class FakeAgent:
        async def run(self, request):
            # Assert history is populated in metadata
            assert "history" in request.metadata
            return AgentResponse(content="I am Paris", session_id=request.session_id)

    class FakeRuntime:
        agent = FakeAgent()

    class FakeAdapter:
        platform = "test"
        label = "Test"
        def __init__(self, config):
            self.sent = []
        async def start(self): pass
        async def stop(self): pass
        def normalize_message(self, payload):
            return GatewayEvent(
                platform="test",
                text=payload["text"],
                target=payload["target"],
                user_id=payload["user_id"],
            )
        async def send(self, target, message, *, thread_id=None):
            self.sent.append(message)
            return GatewaySendResult(success=True, message_id="m1")

    from dojoagents.gateway.adapters.base import GatewaySendResult
    registry = GatewayRegistry()
    registry.register(PlatformEntry("test", "Test", lambda config: FakeAdapter(config)))

    runner = GatewayRunner(
        runtime=FakeRuntime(),
        registry=registry,
        gateway_config={
            "hooks": {"test": {"enabled": True}},
            "session_store": str(tmp_path / "state.db"),
            "pid_file": str(tmp_path / "gateway.pid"),
        }
    )

    await runner.start()
    print("SESSION STORE PATH:", runner.session_store.path)
    result = await runner.handle_webhook(
        "test",
        {"text": "What is Paris?", "target": "T1", "user_id": "U1"},
    )
    print("WEBHOOK RESULT:", result)
    assert result["accepted"] is True

    # Check directly via cursor
    conn = runner.session_store._get_conn()
    try:
        sessions_count = conn.execute("SELECT count(*) FROM sessions").fetchone()[0]
        transcripts_count = conn.execute("SELECT count(*) FROM transcripts").fetchone()[0]
        print("DB sessions count:", sessions_count)
        print("DB transcripts count:", transcripts_count)
        for row in conn.execute("SELECT * FROM transcripts").fetchall():
            print("Row:", dict(row))
    finally:
        conn.close()

    # Retrieve history from SQLite store to verify records exist
    history = runner.session_store.get_history("test:T1:U1", limit=10)
    print("HISTORY RETRIEVED:", history)
    assert len(history) == 2
    assert history[0]["role"] == "user"
    assert history[0]["content"] == "What is Paris?"
    assert history[1]["role"] == "assistant"
    assert history[1]["content"] == "I am Paris"

    await runner.stop()

