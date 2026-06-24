import pytest
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from dojoagents.agent.loop import AgentLoop
from dojoagents.agent.models import ChatRequest, AgentResponse
from dojoagents.config.models import AgentConfig
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


def _make_loop(agent_config: AgentConfig):
    registry = ToolRegistry()
    policy = SandboxPolicy(allowed_roots=["/tmp"], allow_network=False, allowed_commands=[], timeout_seconds=5)
    
    # Mock LLM provider that returns a dummy response
    llm_provider = MagicMock()
    
    # Create mock strands Agent invoke result
    mock_invoke_result = MagicMock()
    mock_invoke_result.stop_reason = "stop"
    mock_invoke_result.metrics = MagicMock()
    mock_invoke_result.metrics.cycle_count = 1
    mock_invoke_result.__str__ = MagicMock(return_value="Output response")
    
    # Mock invoke_async on agent instantiation
    llm_provider.chat = AsyncMock(return_value=MagicMock(content="[CONSOLIDATION SUMMARY]\nSummary\n[LONG-TERM FACTS]\nSummary of middle history"))
    
    loop = AgentLoop(
        llm_provider=llm_provider,
        tool_executor=ToolExecutor(registry, policy),
        skill_manager=MagicMock(),
        memory_manager=MagicMock(),
        extension_registry=MagicMock(),
        config=agent_config,
    )
    loop.skill_manager.prompt_block = MagicMock(return_value="")
    loop.memory_manager.build_system_prompt = MagicMock(return_value="")
    loop.memory_manager.prefetch_all = AsyncMock(return_value="")
    
    return loop, mock_invoke_result


@pytest.mark.asyncio
async def test_token_tracking_metadata():
    # Test that used_tokens and remaining_tokens are returned in response metadata
    config = AgentConfig(
        model="gpt-4.1",
        session_max_tokens=10000,
        threshold_ratio=0.9
    )
    loop, mock_result = _make_loop(config)
    
    req = ChatRequest(
        message="Calculate something small",
        user_id="user-1",
        session_id="session-1",
        channel="cli",
        metadata={"history": [{"role": "user", "content": "Hello"}]}
    )
    
    with patch("strands.Agent.invoke_async", new_callable=AsyncMock) as mock_invoke:
        mock_invoke.return_value = mock_result
        res = await loop.run(req)
        
        # Check that metadata contains token metrics
        assert "used_tokens" in res.metadata
        assert "remaining_tokens" in res.metadata
        assert res.metadata["used_tokens"] > 0
        assert res.metadata["remaining_tokens"] == 10000 - res.metadata["used_tokens"]


@pytest.mark.asyncio
async def test_memory_consolidation_trigger():
    # Setup config with low session max tokens to trigger compression at 90% (e.g. 100 tokens max, 90 tokens threshold)
    config = AgentConfig(
        model="gpt-4.1",
        session_max_tokens=100,
        threshold_ratio=0.9
    )
    loop, mock_result = _make_loop(config)
    
    # Register mock memory provider
    provider = MockMemoryProvider()
    pluggable_manager = PluggableMemoryManager()
    pluggable_manager.add_provider(provider)
    loop.memory_manager = pluggable_manager
    loop.compressor.protect_first_n = 0
    loop.compressor.protect_last_n = 0
    
    # Large history that exceeds 90 tokens threshold (approx 4 chars per token)
    # 450 chars -> 112 tokens
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
        metadata={"history": history}
    )
    
    with patch("strands.Agent.invoke_async", new_callable=AsyncMock) as mock_invoke:
        mock_invoke.return_value = mock_result
        await loop.run(req)
        
        # Consolidation should extract and save facts to memory provider
        assert "session-2" in provider.memories
        assert provider.memories["session-2"] == "Summary of middle history"
        
        # Check that strands Agent was invoked with compressed history
        called_args, called_kwargs = mock_invoke.call_args
        # The strands agent's initial messages list in agent instantiation or loop structure
        # Wait, the history in `Agent` is passed to invoke_async or Agent.__init__
        # In our implementation of run(), we construct Agent(messages=history_msgs, ...)
        # Let's verify that the messages passed to strands.Agent initialization are indeed compressed.
