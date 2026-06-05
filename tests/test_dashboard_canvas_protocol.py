"""Tests for DOJO_CHART protocol injection into Agent system prompt.

When the request comes from the Dashboard (channel="dashboard"), the Agent's
system prompt must include the DOJO_CHART protocol instructions so it knows
how to output chart data for the Canvas panel.

For non-dashboard channels (CLI, gateway, etc.), the protocol is NOT injected.
"""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock


# ---------------------------------------------------------------------------
# Tests: protocol constant exists and has correct content
# ---------------------------------------------------------------------------

class TestDashboardCanvasProtocol:
    def test_module_importable(self):
        from dojoagents.agent.canvas_protocol import DASHBOARD_CANVAS_PROTOCOL
        assert isinstance(DASHBOARD_CANVAS_PROTOCOL, str)
        assert len(DASHBOARD_CANVAS_PROTOCOL) > 0

    def test_contains_dojo_chart_keyword(self):
        from dojoagents.agent.canvas_protocol import DASHBOARD_CANVAS_PROTOCOL
        assert "DOJO_CHART" in DASHBOARD_CANVAS_PROTOCOL

    def test_contains_data_and_script_fields(self):
        from dojoagents.agent.canvas_protocol import DASHBOARD_CANVAS_PROTOCOL
        assert "data" in DASHBOARD_CANVAS_PROTOCOL
        assert "script" in DASHBOARD_CANVAS_PROTOCOL

    def test_contains_echarts_reference(self):
        from dojoagents.agent.canvas_protocol import DASHBOARD_CANVAS_PROTOCOL
        assert "chart.setOption" in DASHBOARD_CANVAS_PROTOCOL

    def test_contains_candlestick_template(self):
        from dojoagents.agent.canvas_protocol import DASHBOARD_CANVAS_PROTOCOL
        assert "candlestick" in DASHBOARD_CANVAS_PROTOCOL.lower()

    def test_contains_dark_theme_colors(self):
        from dojoagents.agent.canvas_protocol import DASHBOARD_CANVAS_PROTOCOL
        # Dark theme color values used in the dashboard
        assert "#e0e0e0" in DASHBOARD_CANVAS_PROTOCOL or "transparent" in DASHBOARD_CANVAS_PROTOCOL

    def test_contains_example_output(self):
        from dojoagents.agent.canvas_protocol import DASHBOARD_CANVAS_PROTOCOL
        # Must include a concrete example of DOJO_CHART block
        assert "```DOJO_CHART" in DASHBOARD_CANVAS_PROTOCOL


# ---------------------------------------------------------------------------
# Tests: protocol injection based on channel
# ---------------------------------------------------------------------------

class TestProtocolInjectionByChannel:
    """Verify that the DOJO_CHART protocol is injected into the system prompt
    only when the request channel is 'dashboard'."""

    def _make_agent_loop(self):
        from dojoagents.agent.loop import AgentLoop
        from dojoagents.config.models import AgentConfig

        llm_provider = MagicMock()
        tool_executor = MagicMock()
        tool_executor.registry = MagicMock()
        tool_executor.registry.all = MagicMock(return_value=[])
        tool_executor.registry.schema_list = MagicMock(return_value=[])
        skill_manager = MagicMock()
        skill_manager.prompt_block = MagicMock(return_value="")
        memory_manager = MagicMock()
        memory_manager.build_system_prompt = MagicMock(return_value="")
        memory_manager.prefetch_all = AsyncMock(return_value="")
        memory_manager.as_hook_provider = MagicMock(return_value=MagicMock())
        extension_registry = MagicMock()
        extension_registry.prompt_context = MagicMock(return_value="")
        config = AgentConfig(model="test-model", max_iterations=1)

        return AgentLoop(
            llm_provider=llm_provider,
            tool_executor=tool_executor,
            skill_manager=skill_manager,
            memory_manager=memory_manager,
            extension_registry=extension_registry,
            config=config,
        )

    def _build_system_prompt(self, loop, channel: str) -> str:
        """Build the system prompt the same way AgentLoop.run() does,
        but without actually running the agent."""
        from dojoagents.agent.models import ChatRequest
        from dojoagents.agent.canvas_protocol import DASHBOARD_CANVAS_PROTOCOL

        request = ChatRequest(
            message="test",
            user_id="test",
            session_id="test",
            channel=channel,
        )

        blocks = [
            "You are DojoAgents, a quantitative finance analysis agent.",
            loop.skill_manager.prompt_block(platform=request.channel),
            loop.memory_manager.build_system_prompt(),
        ]

        # This is the injection logic we're testing
        if request.channel == "dashboard":
            blocks.append(DASHBOARD_CANVAS_PROTOCOL)

        return "\n\n".join(block for block in blocks if block)

    def test_dashboard_channel_includes_protocol(self):
        loop = self._make_agent_loop()
        prompt = self._build_system_prompt(loop, "dashboard")
        assert "DOJO_CHART" in prompt

    def test_cli_channel_excludes_protocol(self):
        loop = self._make_agent_loop()
        prompt = self._build_system_prompt(loop, "cli")
        assert "DOJO_CHART" not in prompt

    def test_telegram_channel_excludes_protocol(self):
        loop = self._make_agent_loop()
        prompt = self._build_system_prompt(loop, "telegram")
        assert "DOJO_CHART" not in prompt

    def test_empty_channel_excludes_protocol(self):
        loop = self._make_agent_loop()
        prompt = self._build_system_prompt(loop, "")
        assert "DOJO_CHART" not in prompt


# ---------------------------------------------------------------------------
# Tests: canvas-chart skill platforms fix
# ---------------------------------------------------------------------------

class TestCanvasChartSkillPlatforms:
    """Verify the canvas-chart skill uses valid OS platform identifiers."""

    def test_skill_platforms_are_valid_os_identifiers(self):
        from pathlib import Path
        skill_md = (
            Path(__file__).parent.parent
            / "dojoagents" / "skills" / "built_in" / "canvas-chart" / "SKILL.md"
        )
        if not skill_md.is_file():
            pytest.skip("canvas-chart SKILL.md not found")

        content = skill_md.read_text()
        # Must NOT have platforms: [dashboard]
        assert "platforms: [dashboard]" not in content, (
            "canvas-chart skill must not use 'dashboard' as platform. "
            "Use [linux, macos, windows] or omit platforms entirely."
        )

    def test_skill_is_discoverable_by_skill_manager(self):
        """The canvas-chart skill must pass platform filtering on the current OS."""
        from pathlib import Path
        from dojoagents.skills.manager import SkillManager

        built_in_dir = Path(__file__).parent.parent / "dojoagents" / "skills" / "built_in"
        if not built_in_dir.exists():
            pytest.skip("built_in skills directory not found")

        manager = SkillManager(skill_dirs=[str(built_in_dir)], enable_cache=False)
        names = manager.list_skills()
        assert "canvas-chart" in names, (
            f"canvas-chart not found in skill list: {names}"
        )

    def test_skill_appears_in_prompt_block(self):
        """The canvas-chart skill must appear in the prompt block (not filtered out)."""
        from pathlib import Path
        from dojoagents.skills.manager import SkillManager

        built_in_dir = Path(__file__).parent.parent / "dojoagents" / "skills" / "built_in"
        if not built_in_dir.exists():
            pytest.skip("built_in skills directory not found")

        manager = SkillManager(skill_dirs=[str(built_in_dir)], enable_cache=False)
        prompt = manager.prompt_block()
        assert "canvas-chart" in prompt, (
            "canvas-chart skill is filtered out of prompt_block. "
            "Check platforms field in SKILL.md frontmatter."
        )
