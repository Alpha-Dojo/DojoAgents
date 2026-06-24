"""Tests for dojoagents.multi_agent.tools — delegate_task tool."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from dojoagents.multi_agent.tools import get_delegation_tool_spec
from dojoagents.multi_agent.pool import AgentPool
from dojoagents.agent.models import AgentResponse
from dojoagents.tools.registry import ToolSpec


def _make_pool() -> AgentPool:
    pool = MagicMock(spec=AgentPool)
    pool.invoke = AsyncMock(return_value=AgentResponse(
        content="Analysis result", session_id="sub-analyst-abc12345"
    ))
    return pool


class TestDelegationToolSpec:
    def test_name(self):
        pool = _make_pool()
        spec = get_delegation_tool_spec(pool)
        assert spec.name == "delegate_task"
        assert isinstance(spec, ToolSpec)

    def test_parameters(self):
        pool = _make_pool()
        spec = get_delegation_tool_spec(pool)
        props = spec.parameters["properties"]
        assert "agent_role" in props
        assert "task_description" in props
        assert "context" in props
        assert props["agent_role"]["type"] == "string"
        assert "enum" in props["agent_role"]
        assert spec.parameters["required"] == ["agent_role", "task_description"]

    @pytest.mark.asyncio
    async def test_handler_invokes_pool(self):
        pool = _make_pool()
        spec = get_delegation_tool_spec(pool)
        result = await spec.handler({
            "agent_role": "analyst",
            "task_description": "Analyze BTC trends",
            "context": "Prior: market is bullish",
        })
        pool.invoke.assert_called_once()
        call_args = pool.invoke.call_args
        assert call_args[0][0] == "analyst"
        req = call_args[0][1]
        assert "Analyze BTC trends" in req.message
        assert "market is bullish" in req.message
        assert req.channel == "internal"
        assert req.user_id == "orchestrator"

    @pytest.mark.asyncio
    async def test_handler_returns_content_string(self):
        pool = _make_pool()
        spec = get_delegation_tool_spec(pool)
        result = await spec.handler({
            "agent_role": "analyst",
            "task_description": "Do something",
        })
        assert result == "Analysis result"

    @pytest.mark.asyncio
    async def test_handler_without_context(self):
        pool = _make_pool()
        spec = get_delegation_tool_spec(pool)
        result = await spec.handler({
            "agent_role": "reviewer",
            "task_description": "Review code",
        })
        req = pool.invoke.call_args[0][1]
        assert "Review code" in req.message
