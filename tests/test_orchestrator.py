"""Tests for dojoagents.multi_agent.orchestrator — Orchestrator coordinator."""

import pytest
from dojoagents.multi_agent.orchestrator import Orchestrator


class TestOrchestrator:
    def test_get_orchestration_prompt(self):
        orch = Orchestrator()
        prompt = orch.get_orchestration_prompt()
        assert isinstance(prompt, str)
        assert len(prompt) > 0
        assert "delegate" in prompt.lower() or "specialist" in prompt.lower()

    def test_activate_sets_flag(self):
        orch = Orchestrator()
        orch.activate("spawn_analyst", "sess-1")
        assert orch.is_active("sess-1")

    def test_is_active_default_false(self):
        orch = Orchestrator()
        assert not orch.is_active("sess-unknown")
