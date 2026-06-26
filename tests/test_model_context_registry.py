import pytest

from dojoagents.agent.model_context import ModelContextRegistry
from dojoagents.config.models import LLMProviderConfig


@pytest.mark.asyncio
async def test_model_context_registry_prefers_config_override(tmp_path):
    registry = ModelContextRegistry(tmp_path / "limits.json", default_context_window=32768)
    value = await registry.resolve(
        "openai",
        LLMProviderConfig(model="gpt-4.1", context_window=99999),
    )
    assert value == 99999


@pytest.mark.asyncio
async def test_model_context_registry_uses_fallback_table(tmp_path):
    registry = ModelContextRegistry(tmp_path / "limits.json", default_context_window=32768)
    value = await registry.resolve("deepseek", LLMProviderConfig(model="deepseek-chat"))
    assert value == 65536
