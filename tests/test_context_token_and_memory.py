import pytest
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from dojoagents.agent.loop import AgentLoop
from dojoagents.agent.models import ChatRequest
from dojoagents.agent.token_ledger import SessionTokenLedger
from dojoagents.config.models import AgentConfig, LLMProviderConfig
from dojoagents.tools.registry import ToolRegistry
from dojoagents.tools.executor import ToolExecutor
from dojoagents.tools.sandbox import SandboxPolicy
from dojoagents.memory.provider import MemoryProvider
from dojoagents.memory.manager import MemoryManager as PluggableMemoryManager


class MockMemoryProvider(MemoryProvider):
    name = "mock"

    def __init__(self):
        self.memories = {}

    def is_available(self) -> bool:
        return True

    async def initialize(self, session_id: str, **context: Any) -> None:
        pass

    def system_prompt_block(self) -> str:
        return ""

    async def prefetch(self, query: str, *, session_id: str) -> str:
        return ""

    async def queue_prefetch(self, query: str, *, session_id: str) -> None:
        pass

    async def sync_turn(self, user_content: str, assistant_content: str, *, session_id: str) -> None:
        pass

    async def save_memory(self, session_id: str, content: str, metadata: dict = None):
        self.memories[session_id] = content

    async def retrieve_memory(self, session_id: str, query: str) -> str:
        return self.memories.get(session_id, "")

    async def on_session_end(self, messages: list[dict[str, Any]]) -> None:
        pass

    async def shutdown(self) -> None:
        pass


def _make_loop(agent_config: AgentConfig, *, sessions_root=None):
    registry = ToolRegistry()
    policy = SandboxPolicy(allowed_roots=["/tmp"], allow_network=False, allowed_commands=[], timeout_seconds=5)

    llm_provider = MagicMock()
    mock_invoke_result = MagicMock()
    mock_invoke_result.stop_reason = "stop"
    mock_invoke_result.metrics = MagicMock()
    mock_invoke_result.metrics.cycle_count = 1
    mock_invoke_result.__str__ = MagicMock(return_value="Output response")
    llm_provider.chat = AsyncMock(return_value=MagicMock(content="[CONSOLIDATION SUMMARY]\nSummary\n[LONG-TERM FACTS]\nSummary of middle history"))
    llm_provider.name = "openai"

    loop = AgentLoop(
        llm_provider=llm_provider,
        tool_executor=ToolExecutor(registry, policy),
        skill_manager=MagicMock(),
        memory_manager=MagicMock(),
        extension_registry=MagicMock(),
        config=agent_config,
        provider_config=LLMProviderConfig(model=agent_config.model, context_window=10000),
    )
    loop.skill_manager.prompt_block = MagicMock(return_value="")
    loop.memory_manager.build_system_prompt = MagicMock(return_value="")
    loop.memory_manager.prefetch_all = AsyncMock(return_value="")
    if sessions_root is not None:
        loop._test_sessions_root = sessions_root
    return loop, mock_invoke_result


@pytest.mark.asyncio
async def test_token_tracking_metadata(tmp_path):
    config = AgentConfig(model="gpt-4.1", compression_threshold_ratio=0.8)
    loop, mock_result = _make_loop(config, sessions_root=tmp_path)

    req = ChatRequest(
        message="Calculate something small",
        user_id="user-1",
        session_id="session-1",
        channel="cli",
        metadata={"history": [{"role": "user", "content": "Hello"}]},
    )

    with patch("dojoagents.agent.loop.SessionTokenLedger", lambda root="~/.dojo/agents/sessions": SessionTokenLedger(tmp_path)):
        with patch("strands.Agent.invoke_async", new_callable=AsyncMock) as mock_invoke:
            mock_invoke.return_value = mock_result
            res = await loop.run(req)

    assert "session_tokens" in res.metadata
    assert "used_tokens" in res.metadata
    assert "remaining_tokens" in res.metadata
    assert res.metadata["session_tokens"]["session_max_tokens"] == 10000


@pytest.mark.asyncio
async def test_memory_consolidation_trigger(tmp_path):
    config = AgentConfig(model="gpt-4.1", compression_threshold_ratio=0.8, enable_context_compression=True)
    loop, mock_result = _make_loop(config, sessions_root=tmp_path)
    loop.compressor.protect_first_n = 0
    loop.compressor.protect_last_n = 0

    provider = MockMemoryProvider()
    pluggable_manager = PluggableMemoryManager()
    pluggable_manager.add_provider(provider)
    loop.memory_manager = pluggable_manager

    ledger = SessionTokenLedger(tmp_path)
    ledger.load_or_create(
        "session-2",
        provider="openai",
        model_id="gpt-4.1",
        model_context_window=100,
        session_max_tokens=100,
        compression_threshold_ratio=0.8,
    )
    ledger.state.last_prompt_tokens = 85
    ledger.save()

    history = [
        {"role": "user", "content": "A" * 150},
        {"role": "assistant", "content": "B" * 150},
        {"role": "user", "content": "C" * 150},
    ]
    req = ChatRequest(
        message="Last prompt",
        user_id="user-1",
        session_id="session-2",
        channel="cli",
        metadata={"history": history},
    )

    with patch("dojoagents.agent.loop.SessionTokenLedger", lambda root="~/.dojo/agents/sessions": SessionTokenLedger(tmp_path)):
        with patch("strands.Agent.invoke_async", new_callable=AsyncMock) as mock_invoke:
            mock_invoke.return_value = mock_result
            await loop.run(req)

    assert "session-2" in provider.memories
    assert provider.memories["session-2"] == "Summary of middle history"
