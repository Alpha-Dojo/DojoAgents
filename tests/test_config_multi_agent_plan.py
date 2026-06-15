"""Tests for MultiAgentConfig and PlanConfig in dojoagents.config."""

import pytest
from dataclasses import FrozenInstanceError

from dojoagents.config.models import (
    AgentsConfig,
    MultiAgentConfig,
    PlanConfig,
)
from dojoagents.config.loader import _to_config


class TestMultiAgentConfig:
    def test_defaults(self):
        cfg = MultiAgentConfig()
        assert cfg.enabled is False
        assert cfg.max_workers == 3
        assert len(cfg.default_agents) == 3

    def test_frozen(self):
        cfg = MultiAgentConfig()
        with pytest.raises(FrozenInstanceError):
            cfg.enabled = True


class TestPlanConfig:
    def test_defaults(self):
        cfg = PlanConfig()
        assert cfg.enabled is False
        assert cfg.auto_plan_threshold == 100
        assert cfg.plan_store_path == "~/.dojo/agents/plans"
        assert cfg.max_plan_steps == 10

    def test_frozen(self):
        cfg = PlanConfig()
        with pytest.raises(FrozenInstanceError):
            cfg.enabled = True


class TestAgentsConfigNewFields:
    def test_has_multi_agent(self):
        cfg = AgentsConfig()
        assert hasattr(cfg, "multi_agent")
        assert isinstance(cfg.multi_agent, MultiAgentConfig)

    def test_has_planning(self):
        cfg = AgentsConfig()
        assert hasattr(cfg, "planning")
        assert isinstance(cfg.planning, PlanConfig)


class TestConfigLoader:
    def test_parses_multi_agent(self):
        raw = {"multi_agent": {"enabled": True, "max_workers": 5}}
        cfg = _to_config(raw)
        assert cfg.multi_agent.enabled is True
        assert cfg.multi_agent.max_workers == 5

    def test_parses_planning(self):
        raw = {"planning": {"enabled": True, "auto_plan_threshold": 50}}
        cfg = _to_config(raw)
        assert cfg.planning.enabled is True
        assert cfg.planning.auto_plan_threshold == 50

    def test_defaults_when_missing(self):
        cfg = _to_config({})
        assert cfg.multi_agent.enabled is False
        assert cfg.planning.enabled is False
