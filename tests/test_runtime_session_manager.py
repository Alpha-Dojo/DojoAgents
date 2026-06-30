from pathlib import Path

import pytest

from dojoagents.agent.loop import AgentLoop
from dojoagents.agent.models import ChatRequest, LLMResult
from dojoagents.agent.providers import StaticLLMProvider
from dojoagents.agent.session_manager import DojoAgentSessionManager
from dojoagents.config.models import AgentConfig, AgentsConfig, SessionsConfig
from dojoagents.agent.runtime import Runtime
from dojoagents.dojo_extensions.registry import DojoExtensionRegistry
from dojoagents.memory.manager import MemoryManager
from dojoagents.skills.manager import SkillManager
from dojoagents.tools.executor import ToolExecutor
from dojoagents.tools.registry import ToolRegistry
from dojoagents.tools.sandbox import SandboxPolicy

from tests.test_runtime_multi_agent_plan import _make_store


def test_runtime_owns_session_manager(tmp_path):
    config = AgentsConfig(sessions=SessionsConfig(root=str(tmp_path / "sessions")))
    runtime = Runtime.from_config_store(_make_store(config))

    assert isinstance(runtime.sessions, DojoAgentSessionManager)
    assert runtime.agent.session_manager is runtime.sessions


@pytest.mark.asyncio
async def test_agent_loop_persists_messages_through_strands_session_manager(tmp_path):
    sessions = DojoAgentSessionManager(root=tmp_path / "sessions", memory_manager=MemoryManager())
    loop = AgentLoop(
        llm_provider=StaticLLMProvider([LLMResult(content="hello from assistant")]),
        tool_executor=ToolExecutor(ToolRegistry(), SandboxPolicy(timeout_seconds=2)),
        skill_manager=SkillManager([]),
        memory_manager=MemoryManager(),
        extension_registry=DojoExtensionRegistry(),
        config=AgentConfig(
            model="test-model",
            enable_guardrails=False,
            enable_context_compression=False,
        ),
        session_manager=sessions,
    )

    response = await loop.run(ChatRequest(user_id="local", session_id="sess-loop", message="hello"))

    assert response.content == "hello from assistant"
    stored = sessions.get_messages_sync("sess-loop")
    assert [message.role for message in stored.messages] == ["user", "assistant"]
    assert stored.messages[0].content == "hello"
    assert stored.messages[1].content == "hello from assistant"
    assert Path(tmp_path / "sessions" / "session_sess-loop" / "agents" / "agent_dojo-agent").exists()
