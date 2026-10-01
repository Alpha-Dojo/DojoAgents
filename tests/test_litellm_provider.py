"""Tests for the LiteLLM provider, its runtime wiring and model-context lookup."""

import sys
import types
from unittest.mock import AsyncMock, MagicMock

import pytest

from dojoagents.agent.context_length import ContextLengthExceededError
from dojoagents.agent.litellm_provider import LiteLLMProvider, litellm_context_info
from dojoagents.agent.model_context import ModelContextRegistry
from dojoagents.agent.runtime import Runtime
from dojoagents.config.loader import ConfigStore, _provider_config, resolve_provider_config
from dojoagents.config.models import AgentsConfig, LLMConfig, LLMProviderConfig


class _ContextWindowExceededError(Exception):
    pass


@pytest.fixture
def fake_litellm(monkeypatch):
    module = types.ModuleType("litellm")
    module.provider_list = ["openai", "anthropic", "azure", "bedrock", "vertex_ai", "gemini"]
    module.acompletion = AsyncMock()
    module.exceptions = types.SimpleNamespace(ContextWindowExceededError=_ContextWindowExceededError)
    module.get_model_info = MagicMock(side_effect=Exception("unknown model"))
    monkeypatch.setitem(sys.modules, "litellm", module)
    return module


def _message(content="hello", tool_calls=None):
    return MagicMock(content=content, tool_calls=tool_calls, reasoning_content=None, model_extra=None)


def _response(message, usage=None):
    return MagicMock(choices=[MagicMock(message=message)], usage=usage)


class TestModelRouting:
    def test_author_is_rejoined_with_the_model(self, fake_litellm):
        provider = LiteLLMProvider(author="anthropic")
        assert provider._resolve_model("claude-sonnet-4-5") == "anthropic/claude-sonnet-4-5"
        assert provider._resolve_model("anthropic/claude-sonnet-4-5") == "anthropic/claude-sonnet-4-5"

    def test_endpoint_routes_keep_their_route(self, fake_litellm):
        provider = LiteLLMProvider(base_url="https://my-azure.openai.azure.com", author="azure")
        assert provider._resolve_model("gpt-4o-deployment") == "azure/gpt-4o-deployment"

    def test_direct_route_without_base_url_is_untouched(self, fake_litellm):
        assert LiteLLMProvider()._resolve_model("gpt-4.1-mini") == "gpt-4.1-mini"


class TestChat:
    @pytest.mark.asyncio
    async def test_non_stream_call_shape_and_usage(self, fake_litellm):
        usage = MagicMock(prompt_tokens=11, completion_tokens=7, total_tokens=18)
        fake_litellm.acompletion.return_value = _response(_message("hi"), usage)
        provider = LiteLLMProvider(author="anthropic")

        result = await provider.chat([{"role": "user", "content": "hi"}], [], model="claude-sonnet-4-5")

        kwargs = fake_litellm.acompletion.call_args.kwargs
        assert kwargs["model"] == "anthropic/claude-sonnet-4-5"
        assert kwargs["drop_params"] is True
        # No tools and no credentials: nothing sent that LiteLLM would forward.
        assert "tools" not in kwargs
        assert "api_key" not in kwargs and "api_base" not in kwargs
        assert result.content == "hi"
        assert result.metadata["provider"] == "litellm"
        assert result.metadata["usage"] == {"prompt_tokens": 11, "completion_tokens": 7, "total_tokens": 18}

    @pytest.mark.asyncio
    async def test_missing_api_key_still_calls_litellm(self, fake_litellm):
        fake_litellm.acompletion.return_value = _response(_message("from env credentials"))
        result = await LiteLLMProvider().chat([], [], model="bedrock/anthropic.claude-v2")
        assert result.content == "from env credentials"
        fake_litellm.acompletion.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_credentials_endpoint_headers_and_tools(self, fake_litellm):
        tool_call = MagicMock(id="call_1", model_extra=None)
        tool_call.function = MagicMock(arguments='{"ticker": "AAPL"}', model_extra=None)
        tool_call.function.name = "get_quote"
        fake_litellm.acompletion.return_value = _response(_message(None, [tool_call]))
        provider = LiteLLMProvider(
            api_key="sk-azure",
            base_url="https://my-resource.openai.azure.com",
            author="azure",
            extra_headers={"X-Team": "quant"},
        )
        tools = [{"name": "get_quote", "description": "Quote", "parameters": {"type": "object", "properties": {}}}]

        result = await provider.chat([], tools, model="gpt-4o-deployment")

        kwargs = fake_litellm.acompletion.call_args.kwargs
        assert kwargs["model"] == "azure/gpt-4o-deployment"
        assert kwargs["api_key"] == "sk-azure"
        assert kwargs["api_base"] == "https://my-resource.openai.azure.com"
        assert kwargs["extra_headers"] == {"X-Team": "quant"}
        assert kwargs["tools"] == [{"type": "function", "function": tools[0]}]
        assert [(call.id, call.name, call.arguments) for call in result.tool_calls] == [("call_1", "get_quote", {"ticker": "AAPL"})]

    @pytest.mark.asyncio
    async def test_drop_params_can_be_overridden(self, fake_litellm):
        fake_litellm.acompletion.return_value = _response(_message())
        await LiteLLMProvider(completion_kwargs={"drop_params": False, "num_retries": 2}).chat([], [], model="gpt-4.1")
        kwargs = fake_litellm.acompletion.call_args.kwargs
        assert kwargs["drop_params"] is False
        assert kwargs["num_retries"] == 2

    @pytest.mark.asyncio
    async def test_stream_assembles_reasoning_tools_and_usage(self, fake_litellm):
        def chunk(content=None, reasoning=None, tool_calls=None, usage=None, choices=True):
            delta = MagicMock(content=content, reasoning_content=reasoning, tool_calls=tool_calls, model_extra=None)
            return MagicMock(choices=[MagicMock(delta=delta)] if choices else [], usage=usage)

        tc_first = MagicMock(index=0, id="call_1", model_extra=None)
        tc_first.function = MagicMock(arguments='{"tick', model_extra=None)
        tc_first.function.name = "get_quote"
        tc_rest = MagicMock(index=0, id=None, model_extra=None)
        tc_rest.function = MagicMock(arguments='er": "MSFT"}', model_extra=None)
        tc_rest.function.name = None
        chunks = [
            chunk(reasoning="thinking"),
            chunk(content="Checking "),
            chunk(tool_calls=[tc_first]),
            chunk(tool_calls=[tc_rest]),
            chunk(usage=MagicMock(prompt_tokens=20, completion_tokens=5, total_tokens=25), choices=False),
        ]

        async def stream():
            for item in chunks:
                yield item

        fake_litellm.acompletion.return_value = stream()
        streamed: list[str] = []

        result = await LiteLLMProvider().chat([], [], model="gpt-4.1", stream=True, stream_callback=streamed.append)

        assert fake_litellm.acompletion.call_args.kwargs["stream_options"] == {"include_usage": True}
        assert streamed == ["Checking "]
        assert result.metadata["reasoning_content"] == "thinking"
        assert result.metadata["usage"]["total_tokens"] == 25
        assert [(call.name, call.arguments) for call in result.tool_calls] == [("get_quote", {"ticker": "MSFT"})]

    @pytest.mark.asyncio
    async def test_context_window_error_is_translated(self, fake_litellm):
        fake_litellm.acompletion.side_effect = _ContextWindowExceededError(
            "This model's maximum context length is 8192 tokens. However, you requested 9000 tokens"
        )
        with pytest.raises(ContextLengthExceededError) as excinfo:
            await LiteLLMProvider().chat([], [], model="gpt-4")
        assert excinfo.value.max_context == 8192
        assert excinfo.value.requested_tokens == 9000


class TestConfigAndRuntime:
    def test_routed_model_keeps_its_route_through_the_loader(self, fake_litellm):
        cfg = _provider_config("litellm", {"model": "bedrock/us.anthropic.claude-sonnet-4-5"})
        assert (cfg.author, cfg.model) == ("bedrock", "us.anthropic.claude-sonnet-4-5")
        assert LiteLLMProvider.from_config(cfg)._resolve_model(cfg.model) == "bedrock/us.anthropic.claude-sonnet-4-5"

    def test_unrouted_model_has_no_default_author(self, fake_litellm):
        cfg = _provider_config("litellm", {"model": "gpt-4.1-mini"})
        assert cfg.author is None
        assert LiteLLMProvider.from_config(cfg)._resolve_model(cfg.model) == "gpt-4.1-mini"

    def test_runtime_selects_the_litellm_provider(self, fake_litellm):
        config = AgentsConfig(
            llm_provider=LLMConfig(
                default="litellm",
                providers={"litellm": LLMProviderConfig(model="claude-sonnet-4-5", author="anthropic")},
            )
        )
        store = MagicMock(spec=ConfigStore)
        store.snapshot.return_value = config

        rt = Runtime.from_config_store(store)

        assert isinstance(rt.agent.llm_provider, LiteLLMProvider)
        assert rt.agent.llm_provider.author == "anthropic"
        name, _ = resolve_provider_config(config.llm_provider)
        assert name == "litellm"


class TestModelContext:
    def test_context_info_from_litellm_model_map(self, fake_litellm):
        fake_litellm.get_model_info = MagicMock(return_value={"max_input_tokens": 200000, "supports_vision": True})
        assert litellm_context_info("anthropic/claude-sonnet-4-5") == (200000, ("text", "image"))
        fake_litellm.get_model_info = MagicMock(return_value={"max_input_tokens": 64000, "supports_vision": False})
        assert litellm_context_info("deepseek/deepseek-chat") == (64000, ("text",))

    def test_unknown_models_fall_back(self, fake_litellm):
        assert litellm_context_info("my-alias") is None

    @pytest.mark.asyncio
    async def test_registry_uses_litellm_and_skips_openrouter(self, fake_litellm, tmp_path, monkeypatch):
        fake_litellm.get_model_info = MagicMock(return_value={"max_input_tokens": 200000, "supports_vision": True})
        registry = ModelContextRegistry(tmp_path / "limits.json")
        openrouter = AsyncMock(return_value=None)
        monkeypatch.setattr(registry, "_retrieve_openrouter_info", openrouter)

        info = await registry.resolve_info("litellm", LLMProviderConfig(model="claude-sonnet-4-5", author="anthropic"))

        assert info.context_window == 200000
        assert info.supports_input_modality("image")
        fake_litellm.get_model_info.assert_called_once_with("anthropic/claude-sonnet-4-5")
        openrouter.assert_not_awaited()


class TestDashboardModelOptions:
    @pytest.mark.asyncio
    async def test_litellm_is_available_without_an_api_key(self):
        from dojoagents.dashboard.routers.model_options import list_model_options

        store = MagicMock()
        store.snapshot.return_value = AgentsConfig(
            llm_provider=LLMConfig(
                default="litellm",
                providers={"litellm": LLMProviderConfig(model="claude-sonnet-4-5", models=("claude-sonnet-4-5",), author="anthropic")},
            )
        )

        response = await list_model_options(store=store)

        option = response.models[0]
        assert option.provider == "litellm"
        assert option.label.startswith("LiteLLM")
        assert option.available is True
