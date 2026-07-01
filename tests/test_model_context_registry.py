import json
import time

import pytest

from dojoagents.agent.model_context import ModelContextInfo, ModelContextRegistry
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


@pytest.mark.asyncio
async def test_model_context_registry_fetches_openrouter_models_index_and_matches_author_slug(tmp_path, monkeypatch):
    requested = {}

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "data": [
                    {
                        "id": "other/glm-5.2",
                        "canonical_slug": "other/glm-5.2-20260616",
                        "context_length": 2048,
                        "architecture": {"input_modalities": ["text"], "output_modalities": ["text"]},
                    },
                    {
                        "id": "z-ai/glm-5.2",
                        "canonical_slug": "z-ai/glm-5.2-20260616",
                        "context_length": 1048576,
                        "architecture": {
                            "input_modalities": ["text", "image", "text"],
                            "output_modalities": ["text"],
                        },
                        "top_provider": {"context_length": 1048576},
                    },
                ]
            }

    class FakeAsyncClient:
        def __init__(self, *, timeout):
            requested["timeout"] = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def get(self, url, headers):
            requested["url"] = url
            requested["headers"] = headers
            return FakeResponse()

    import httpx

    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)
    registry = ModelContextRegistry(tmp_path / "limits.json", default_context_window=32768)

    info = await registry.resolve_info(
        "openai",
        LLMProviderConfig(
            model="glm-5.2",
            author="z-ai",
            base_url="https://openrouter.ai/api/v1",
            api_key="test-key",
        ),
    )

    assert requested["url"] == "https://openrouter.ai/api/v1/models"
    assert requested["headers"] == {"Authorization": "Bearer test-key"}
    assert info == ModelContextInfo(
        context_window=1048576,
        input_modalities=("text", "image"),
        output_modalities=("text",),
        canonical_slug="z-ai/glm-5.2-20260616",
        provider_model_id="z-ai/glm-5.2",
        author="z-ai",
        slug="glm-5.2",
    )
    assert (
        await registry.resolve(
            "openai",
            LLMProviderConfig(model="z-ai/glm-5.2", base_url="https://openrouter.ai/api/v1"),
        )
        == 1048576
    )


@pytest.mark.asyncio
async def test_model_context_registry_reads_structured_cache_and_preserves_modalities(tmp_path):
    cache_path = tmp_path / "limits.json"
    cache_path.write_text(
        json.dumps(
            {
                "openai:z-ai/glm-5.2": {
                    "context_window": 1048576,
                    "input_modalities": ["text", "image"],
                    "output_modalities": ["text"],
                    "canonical_slug": "z-ai/glm-5.2-20260616",
                    "provider_model_id": "z-ai/glm-5.2",
                    "author": "z-ai",
                    "slug": "glm-5.2",
                    "updated_at": time.time(),
                }
            }
        ),
        encoding="utf-8",
    )
    registry = ModelContextRegistry(cache_path, default_context_window=32768)

    info = await registry.resolve_info("openai", LLMProviderConfig(model="z-ai/glm-5.2"))
    assert info.supports_input_modality("image")

    registry.note_context_window("openai", "z-ai/glm-5.2", 999999)

    updated = registry.cached_info("openai", "z-ai/glm-5.2")
    assert updated == ModelContextInfo(
        context_window=999999,
        input_modalities=("text", "image"),
        output_modalities=("text",),
        canonical_slug="z-ai/glm-5.2-20260616",
        provider_model_id="z-ai/glm-5.2",
        author="z-ai",
        slug="glm-5.2",
    )


@pytest.mark.asyncio
async def test_model_context_registry_config_override_preserves_openrouter_modalities(tmp_path, monkeypatch):
    calls = []

    async def fake_retrieve(provider_cfg):
        calls.append((provider_cfg.author, provider_cfg.model))
        return ModelContextInfo(
            context_window=1048576,
            input_modalities=("text", "image"),
            output_modalities=("text",),
            canonical_slug="z-ai/glm-5.2-20260616",
            provider_model_id="z-ai/glm-5.2",
            author="z-ai",
            slug="glm-5.2",
        )

    registry = ModelContextRegistry(tmp_path / "limits.json", default_context_window=32768)
    monkeypatch.setattr(registry, "_retrieve_openrouter_info", fake_retrieve)

    info = await registry.resolve_info(
        "openai",
        LLMProviderConfig(
            model="z-ai/glm-5.2",
            base_url="https://openrouter.ai/api/v1",
            context_window=999999,
        ),
    )

    assert info.context_window == 999999
    assert info.supports_input_modality("Image")
    assert registry.cached_info("openai", "z-ai/glm-5.2") == info
    assert calls == [(None, "z-ai/glm-5.2")]
