"""Tests for dashboard visualization guidance injected into Agent prompts.

The current dashboard chat UI renders structured ``viz_blocks``. It should not
teach the model to emit legacy ``DOJO_CHART`` fenced blocks that the source UI
no longer renders.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock


class TestDashboardVizProtocol:
    def test_module_importable(self) -> None:
        from dojoagents.harnesses.built_in.financial.prompts.canvas_protocol import DASHBOARD_VIZ_PROTOCOL

        assert isinstance(DASHBOARD_VIZ_PROTOCOL, str)
        assert len(DASHBOARD_VIZ_PROTOCOL) > 0

    def test_protocol_mentions_structured_viz_blocks(self) -> None:
        from dojoagents.harnesses.built_in.financial.prompts.canvas_protocol import DASHBOARD_VIZ_PROTOCOL

        assert "viz_blocks" in DASHBOARD_VIZ_PROTOCOL
        assert "agent_viz_build" in DASHBOARD_VIZ_PROTOCOL

    def test_protocol_forbids_legacy_dojo_chart_output(self) -> None:
        from dojoagents.harnesses.built_in.financial.prompts.canvas_protocol import DASHBOARD_VIZ_PROTOCOL

        assert "Do NOT output `DOJO_CHART` fenced blocks." in DASHBOARD_VIZ_PROTOCOL
        assert "Do NOT output JavaScript, ECharts scripts, or HTML" in DASHBOARD_VIZ_PROTOCOL

    def test_legacy_alias_points_to_current_protocol(self) -> None:
        from dojoagents.harnesses.built_in.financial.prompts.canvas_protocol import (
            DASHBOARD_CANVAS_PROTOCOL,
            DASHBOARD_VIZ_PROTOCOL,
        )

        assert DASHBOARD_CANVAS_PROTOCOL == DASHBOARD_VIZ_PROTOCOL


class TestProtocolInjectionByChannel:
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
        from dojoagents.harnesses.built_in.financial.prompts.canvas_protocol import DASHBOARD_VIZ_PROTOCOL
        from dojoagents.agent.models import ChatRequest

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

        if request.channel == "dashboard":
            blocks.append(DASHBOARD_VIZ_PROTOCOL)

        return "\n\n".join(block for block in blocks if block)

    def test_dashboard_channel_includes_structured_viz_protocol(self) -> None:
        loop = self._make_agent_loop()
        prompt = self._build_system_prompt(loop, "dashboard")

        assert "viz_blocks" in prompt
        assert "agent_viz_build" in prompt
        assert "DOJO_CHART" in prompt

    def test_cli_channel_excludes_dashboard_viz_protocol(self) -> None:
        loop = self._make_agent_loop()
        prompt = self._build_system_prompt(loop, "cli")

        assert "viz_blocks" not in prompt
        assert "agent_viz_build" not in prompt
        assert "DOJO_CHART" not in prompt

    def test_telegram_channel_excludes_dashboard_viz_protocol(self) -> None:
        loop = self._make_agent_loop()
        prompt = self._build_system_prompt(loop, "telegram")

        assert "viz_blocks" not in prompt
        assert "agent_viz_build" not in prompt
