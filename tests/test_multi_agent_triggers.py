"""Tests for dojoagents.multi_agent.triggers — MultiAgentTriggerHook."""

import pytest
from unittest.mock import MagicMock

from dojoagents.multi_agent.triggers import (
    COMPLEXITY_TRIGGERS,
    TOOL_RESULT_TRIGGERS,
    MultiAgentTriggerHook,
)


class TestComplexityTriggers:
    def test_analyze_and_implement(self):
        hook = MultiAgentTriggerHook(orchestrator=MagicMock())
        result = hook.on_pre_llm_call(
            user_message="analyze BTC trends and then implement a trading strategy",
            session_id="sess-1",
        )
        assert result is not None  # orchestration prompt returned

    def test_backtest_strategy(self):
        hook = MultiAgentTriggerHook(orchestrator=MagicMock())
        result = hook.on_pre_llm_call(
            user_message="backtest my portfolio strategy",
            session_id="sess-2",
        )
        assert result is not None

    def test_simple_message_no_match(self):
        hook = MultiAgentTriggerHook(orchestrator=MagicMock())
        result = hook.on_pre_llm_call(
            user_message="What is the price of BTC?",
            session_id="sess-3",
        )
        assert result is None


class TestToolResultTriggers:
    def test_tool_result_triggers_activation(self):
        orchestrator = MagicMock()
        hook = MultiAgentTriggerHook(orchestrator=orchestrator)
        hook.on_post_tool_call(
            tool_name="dojo_market_data",
            result="Found multiple_assets in dataset",
            session_id="sess-4",
        )
        orchestrator.activate.assert_called_once()

    def test_tool_result_no_match(self):
        orchestrator = MagicMock()
        hook = MultiAgentTriggerHook(orchestrator=orchestrator)
        hook.on_post_tool_call(
            tool_name="terminal",
            result="command succeeded",
            session_id="sess-5",
        )
        orchestrator.activate.assert_not_called()


class TestTriggerConstants:
    def test_complexity_triggers_have_pattern(self):
        for t in COMPLEXITY_TRIGGERS:
            assert "pattern" in t
            assert "confidence" in t

    def test_tool_result_triggers_have_fields(self):
        for t in TOOL_RESULT_TRIGGERS:
            assert "tool" in t
            assert "result_pattern" in t
            assert "action" in t
