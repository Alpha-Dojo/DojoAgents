"""Tests for MultiAgentConfig and PlanConfig in dojoagents.config."""

import pytest
from dataclasses import FrozenInstanceError

from dojoagents.config.models import (
    AgentsConfig,
    MultiAgentConfig,
    PlanConfig,
    WebToolsConfig,
)
from dojoagents.config.loader import _to_config, resolve_provider_config
from dojoagents.config.models import LLMConfig, LLMProviderConfig


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

    def test_has_web_tools(self):
        cfg = AgentsConfig()
        assert hasattr(cfg.tools, "web")
        assert isinstance(cfg.tools.web, WebToolsConfig)


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
        assert cfg.agent.model is None
        assert cfg.llm_provider.providers == {}

    def test_no_default_model_without_llm_provider(self):
        cfg = _to_config({"agent": {"max_iterations": 5}})
        assert cfg.agent.model is None
        assert cfg.llm_provider.default is None

    def test_inherits_model_from_configured_provider(self):
        cfg = _to_config(
            {
                "llm_provider": {
                    "providers": {
                        "openai": {"model": "test-model", "api_key_env": "OPENAI_API_KEY"},
                    }
                },
                "agent": {"max_iterations": 2},
            }
        )
        assert cfg.agent.model == "test-model"

    def test_parses_provider_author(self):
        cfg = _to_config(
            {
                "llm_provider": {
                    "default": "openrouter",
                    "providers": {
                        "openrouter": {
                            "model": "glm-5.2",
                            "author": "z-ai",
                            "base_url": "https://openrouter.ai/api/v1",
                        }
                    },
                }
            }
        )
        provider = cfg.llm_provider.providers["openrouter"]
        assert provider.model == "glm-5.2"
        assert provider.author == "z-ai"

    def test_fills_default_provider_author_when_missing(self):
        cfg = _to_config(
            {
                "llm_provider": {
                    "providers": {
                        "gemini": {
                            "model": "gemini-3.5-flash",
                            "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
                        }
                    }
                }
            }
        )
        provider = cfg.llm_provider.providers["gemini"]
        assert provider.model == "gemini-3.5-flash"
        assert provider.author == "google"

    def test_normalizes_provider_model_id_into_author_and_slug(self):
        cfg = _to_config(
            {
                "llm_provider": {
                    "providers": {
                        "openrouter": {
                            "model": "z-ai/glm-5.2",
                            "base_url": "https://openrouter.ai/api/v1",
                        }
                    }
                }
            }
        )
        provider = cfg.llm_provider.providers["openrouter"]
        assert provider.model == "glm-5.2"
        assert provider.author == "z-ai"

    def test_resolve_provider_config_without_default(self):
        llm = LLMConfig(
            default=None,
            providers={"openai": LLMProviderConfig(model="m1")},
        )
        name, provider = resolve_provider_config(llm)
        assert name == "openai"
        assert provider.model == "m1"

    def test_parses_web_tools(self):
        cfg = _to_config(
            {
                "tools": {
                    "web": {
                        "search_backend": "mock-search",
                        "extract_backend": "mock-extract",
                        "user_agent": "CustomBot/1.0",
                        "search_base_url": "http://localhost:8080",
                        "extract_base_url": "http://localhost:8081",
                        "summary_threshold_chars": 1200,
                    }
                }
            }
        )
        assert cfg.tools.web.search_backend == "mock-search"
        assert cfg.tools.web.extract_backend == "mock-extract"
        assert cfg.tools.web.user_agent == "CustomBot/1.0"
        assert cfg.tools.web.search_base_url == "http://localhost:8080"
        assert cfg.tools.web.extract_base_url == "http://localhost:8081"
        assert cfg.tools.web.summary_threshold_chars == 1200
