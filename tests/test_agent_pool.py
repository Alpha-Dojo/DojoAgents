"""Tests for dojoagents.multi_agent.pool — AgentPool with lazy agent creation."""

import pytest
from dataclasses import replace
from unittest.mock import AsyncMock, MagicMock

from dojoagents.multi_agent.pool import AgentPool
from dojoagents.multi_agent.models import AgentSpec, AgentRole
from dojoagents.agent.models import ChatRequest, AgentResponse
from dojoagents.tools.registry import ToolRegistry, ToolSpec


def _make_runtime(tool_names: list[str] = None, model: str = "gpt-4.1"):
    """Build a mock Runtime with a realistic AgentLoop stub."""
    runtime = MagicMock()
    agent = MagicMock()
    agent.llm_provider = MagicMock()
    agent.skill_manager = MagicMock()
    agent.memory_manager = MagicMock()
    agent.extension_registry = MagicMock()

    registry = ToolRegistry()
    for name in (tool_names or ["terminal", "code_execution", "dojo_sdk"]):
        registry.register(ToolSpec(
            name=name, description=name, parameters={"type": "object"}, handler=AsyncMock()
        ))
    agent.tool_executor = MagicMock()
    agent.tool_executor.registry = registry
    agent.tool_executor.sandbox = MagicMock()

    from dojoagents.config.models import AgentConfig
    runtime.config = MagicMock()
    runtime.config.agent = AgentConfig(model=model)
    runtime.agent = agent
    return runtime


class TestAgentPool:
    def test_register_and_lazy_creation(self):
        runtime = _make_runtime()
        pool = AgentPool(runtime)
        spec = AgentSpec(role=AgentRole.ANALYST, name="analyst")
        pool.register_agent(spec)
        assert pool._agents == {}  # not yet created
        agent = pool.get_or_create("analyst")
        assert agent is not None

    def test_same_instance_returned(self):
        runtime = _make_runtime()
        pool = AgentPool(runtime)
        pool.register_agent(AgentSpec(role=AgentRole.ANALYST, name="analyst"))
        a1 = pool.get_or_create("analyst")
        a2 = pool.get_or_create("analyst")
        assert a1 is a2

    def test_disallowed_tools_filtered(self):
        runtime = _make_runtime(tool_names=["terminal", "code_execution", "dojo_sdk"])
        pool = AgentPool(runtime)
        pool.register_agent(AgentSpec(
            role=AgentRole.ANALYST, name="analyst", disallowed_tools=["code_execution"]
        ))
        agent = pool.get_or_create("analyst")
        assert agent.tool_executor.registry.get("code_execution") is None
        assert agent.tool_executor.registry.get("terminal") is not None

    def test_missing_spec_raises_key_error(self):
        runtime = _make_runtime()
        pool = AgentPool(runtime)
        with pytest.raises(KeyError):
            pool.get_or_create("nonexistent")

    def test_model_override(self):
        runtime = _make_runtime(model="gpt-4.1")
        pool = AgentPool(runtime)
        pool.register_agent(AgentSpec(
            role=AgentRole.REVIEWER, name="reviewer", model="gpt-4o"
        ))
        agent = pool.get_or_create("reviewer")
        assert agent.config.model == "gpt-4o"

    @pytest.mark.asyncio
    async def test_invoke_delegates_to_agent(self):
        runtime = _make_runtime()
        pool = AgentPool(runtime)
        pool.register_agent(AgentSpec(role=AgentRole.ANALYST, name="analyst"))
        # Patch the created agent's run method
        fake_agent = MagicMock()
        fake_agent.run = AsyncMock(return_value=AgentResponse(
            content="Analysis done", session_id="sub-analyst-12345678"
        ))
        pool._agents["analyst"] = fake_agent

        req = ChatRequest(message="Analyze BTC", user_id="orch", session_id="sub-1", channel="internal")
        resp = await pool.invoke("analyst", req)
        assert resp.content == "Analysis done"
        fake_agent.run.assert_called_once_with(req)
