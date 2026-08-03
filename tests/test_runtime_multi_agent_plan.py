"""Tests for Runtime multi-agent and planning integration."""

from unittest.mock import MagicMock

from dojoagents.config.models import AgentsConfig, LLMConfig, LLMProviderConfig, MultiAgentConfig, PlanConfig
from dojoagents.config.loader import ConfigStore
from dojoagents.agent.gemini_provider import GeminiNativeProvider
from dojoagents.agent.providers import OpenAICompatibleProvider
from dojoagents.agent.runtime import Runtime


def _make_store(config: AgentsConfig | None = None):
    store = MagicMock(spec=ConfigStore)
    store.snapshot.return_value = config or AgentsConfig()
    return store


class TestRuntimeMultiAgentDisabled:
    def test_no_delegation_tool_when_disabled(self):
        rt = Runtime.from_config_store(_make_store())
        tool_names = [s.name for s in rt.agent.tool_executor.registry.all()]
        assert "delegate_task" not in tool_names


class TestRuntimePlanningDisabled:
    def test_no_plan_tools_when_disabled(self):
        rt = Runtime.from_config_store(_make_store())
        tool_names = [s.name for s in rt.agent.tool_executor.registry.all()]
        assert "create_plan" not in tool_names
        assert "execute_plan" not in tool_names


class TestRuntimeGeminiProvider:
    def test_gemini_runtime_uses_native_provider(self):
        config = AgentsConfig(
            llm_provider=LLMConfig(
                default="gemini",
                providers={
                    "gemini": LLMProviderConfig(
                        model="gemini-2.5-pro",
                        base_url="https://generativelanguage.googleapis.com/v1beta/openai",
                        api_key="test-key",
                        api_key_env="GEMINI_API_KEY",
                    )
                },
            )
        )
        rt = Runtime.from_config_store(_make_store(config))
        assert isinstance(rt.agent.llm_provider, GeminiNativeProvider)


class TestRuntimeOpenAICompatibleProvider:
    def test_runtime_preserves_provider_routing_and_output_limit(self):
        config = AgentsConfig(
            llm_provider=LLMConfig(
                default="model-router",
                providers={
                    "model-router": LLMProviderConfig(
                        model="glm-5.2",
                        author="z-ai",
                        base_url="https://openrouter.ai/api/v1",
                        api_key="test-key",
                        context_window=1_048_576,
                        max_tokens=384_000,
                    )
                },
            )
        )

        rt = Runtime.from_config_store(_make_store(config))

        assert isinstance(rt.agent.llm_provider, OpenAICompatibleProvider)
        assert rt.agent.llm_provider.name == "model-router"
        assert rt.agent.llm_provider.author == "z-ai"
        assert rt.agent.llm_provider.max_tokens == 384_000
        assert rt.agent.provider_config.context_window == 1_048_576


class TestRuntimeMultiAgentEnabled:
    def test_delegation_tool_registered(self):
        config = AgentsConfig(multi_agent=MultiAgentConfig(enabled=True))
        rt = Runtime.from_config_store(_make_store(config))
        tool_names = [s.name for s in rt.agent.tool_executor.registry.all()]
        assert "delegate_task" in tool_names


class TestRuntimePlanningEnabled:
    def test_plan_tools_registered(self):
        config = AgentsConfig(planning=PlanConfig(enabled=True))
        rt = Runtime.from_config_store(_make_store(config))
        tool_names = [s.name for s in rt.agent.tool_executor.registry.all()]
        assert "create_plan" in tool_names
        assert "execute_plan" in tool_names
        assert "revise_plan" in tool_names


class TestRuntimePlanHookWired:
    def test_plan_activation_hook_set(self):
        config = AgentsConfig(planning=PlanConfig(enabled=True))
        rt = Runtime.from_config_store(_make_store(config))
        assert rt.agent._plan_activation_hook is not None


class TestRuntimeHookRegistration:
    def test_multi_agent_hook_in_plugin_registry(self):
        from dojoagents.plugins import get_plugin_registry

        config = AgentsConfig(multi_agent=MultiAgentConfig(enabled=True))
        plugin_registry = get_plugin_registry()
        pre_count_before = len(plugin_registry._hooks.get("pre_llm_call", []))
        Runtime.from_config_store(_make_store(config))
        pre_count_after = len(plugin_registry._hooks.get("pre_llm_call", []))
        assert pre_count_after > pre_count_before

    def test_multi_agent_hook_not_registered_when_disabled(self):
        from dojoagents.plugins import get_plugin_registry

        config = AgentsConfig()
        plugin_registry = get_plugin_registry()
        pre_count_before = len(plugin_registry._hooks.get("pre_llm_call", []))
        Runtime.from_config_store(_make_store(config))
        pre_count_after = len(plugin_registry._hooks.get("pre_llm_call", []))
        assert pre_count_after == pre_count_before
