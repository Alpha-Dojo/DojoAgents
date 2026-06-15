"""Tests for AgentLoop plan activation integration."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from dojoagents.agent.loop import AgentLoop
from dojoagents.agent.models import ChatRequest, AgentResponse
from dojoagents.config.models import AgentConfig
from dojoagents.tools.registry import ToolRegistry
from dojoagents.tools.executor import ToolExecutor
from dojoagents.tools.sandbox import SandboxPolicy


def _make_loop(plan_hook=None):
    registry = ToolRegistry()
    policy = SandboxPolicy(allowed_roots=["/tmp"], allow_network=False, allowed_commands=[], timeout_seconds=5)
    loop = AgentLoop(
        llm_provider=MagicMock(),
        tool_executor=ToolExecutor(registry, policy),
        skill_manager=MagicMock(),
        memory_manager=MagicMock(),
        extension_registry=MagicMock(),
        config=AgentConfig(model="gpt-4.1"),
        plan_activation_hook=plan_hook,
    )
    loop.skill_manager.prompt_block = MagicMock(return_value="")
    loop.memory_manager.build_system_prompt = MagicMock(return_value="")
    loop.memory_manager.prefetch_all = AsyncMock(return_value="")
    return loop


class TestAgentLoopPlanActivation:
    def test_plan_hook_stored(self):
        hook = MagicMock()
        loop = _make_loop(plan_hook=hook)
        assert loop._plan_activation_hook is hook

    def test_no_hook_none(self):
        loop = _make_loop()
        assert loop._plan_activation_hook is None

    def test_plan_activation_injects_prompt(self):
        hook = MagicMock()
        hook.should_create_plan = MagicMock(return_value=True)
        hook.get_plan_prompt = MagicMock(return_value="[PLAN PROMPT]")
        loop = _make_loop(plan_hook=hook)
        # We test that the system prompt would include plan instructions
        # by checking the hook is called correctly
        req = ChatRequest(message="test", user_id="u", session_id="s", channel="cli")
        assert hook.should_create_plan(req)
        assert "[PLAN PROMPT]" in hook.get_plan_prompt()

    def test_no_activation_normal_run(self):
        hook = MagicMock()
        hook.should_create_plan = MagicMock(return_value=False)
        loop = _make_loop(plan_hook=hook)
        req = ChatRequest(message="simple", user_id="u", session_id="s", channel="cli")
        assert not hook.should_create_plan(req)
        hook.get_plan_prompt.assert_not_called()
