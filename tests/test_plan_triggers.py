"""Tests for dojoagents.planning.triggers — PlanActivationHook."""

import pytest

from dojoagents.planning.triggers import PlanActivationHook
from dojoagents.agent.models import ChatRequest


def _req(message: str, metadata: dict | None = None) -> ChatRequest:
    return ChatRequest(
        message=message,
        user_id="user",
        session_id="sess-1",
        channel="cli",
        metadata=metadata or {},
    )


class TestPlanActivationHook:
    def test_explicit_plan_keyword(self):
        hook = PlanActivationHook()
        assert hook.should_create_plan(_req("create a plan for backtesting"))

    def test_multi_step_pattern(self):
        hook = PlanActivationHook()
        assert hook.should_create_plan(_req("First analyze BTC, then implement the strategy"))

    def test_simple_message_no_plan(self):
        hook = PlanActivationHook()
        assert not hook.should_create_plan(_req("What is the price of BTC?"))

    def test_long_message_triggers(self):
        hook = PlanActivationHook()
        long_msg = " ".join(["word"] * 120)
        assert hook.should_create_plan(_req(long_msg))

    def test_metadata_workflow_type(self):
        hook = PlanActivationHook()
        assert hook.should_create_plan(_req("Run analysis", metadata={"workflow_type": "backtest"}))

    def test_quant_context_no_crash(self):
        hook = PlanActivationHook()
        req = _req("Simple question")
        assert not hook.should_create_plan(req)

    def test_backtest_multiple_pattern(self):
        hook = PlanActivationHook()
        assert hook.should_create_plan(_req("backtest multiple strategies for my portfolio"))

    def test_get_plan_prompt(self):
        hook = PlanActivationHook()
        prompt = hook.get_plan_prompt()
        assert "plan" in prompt.lower()
        assert "create_plan" in prompt
