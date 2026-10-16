from unittest.mock import patch

import pytest

from dojoagents.agent.provider_profiles import (
    MINIMAL_OPENAI_COMPATIBLE,
    OPENAI_COMPATIBLE,
    OPENAI_NATIVE,
    ModelCatalog,
    ModelIdPolicy,
    resolve_provider_profile,
)
from dojoagents.agent.provider_contracts import ProviderRequest
from dojoagents.agent.provider_request import OpenAIRequestAdapter
from dojoagents.config.loader import _to_config
from dojoagents.config.models import LLMProviderConfig


def test_named_wire_profiles_have_distinct_explicit_behavior() -> None:
    assert OPENAI_COMPATIBLE.message_name_policy == "omit"
    assert OPENAI_COMPATIBLE.stream_usage_policy == "include"
    assert OPENAI_NATIVE.message_name_policy == "omit"
    assert OPENAI_NATIVE.stream_usage_policy == "include"
    assert MINIMAL_OPENAI_COMPATIBLE.message_name_policy == "omit"
    assert MINIMAL_OPENAI_COMPATIBLE.stream_usage_policy == "unsupported"


def test_openai_native_omits_internal_tool_name_from_wire_payload() -> None:
    resolved = resolve_provider_profile(
        "openai",
        LLMProviderConfig(base_url="https://api.openai.com/v1"),
    )
    internal_message = {
        "role": "tool",
        "name": "quote",
        "tool_call_id": "call-1",
        "content": "123.4",
    }

    payload = OpenAIRequestAdapter(resolved.wire_policy).build(
        ProviderRequest(
            model="gpt-4.1",
            messages=(internal_message,),
        )
    )

    assert "name" not in payload["messages"][0]
    assert internal_message["name"] == "quote"


def test_direct_and_loaded_openai_configs_resolve_the_same_native_preset() -> None:
    direct = LLMProviderConfig(base_url="https://api.openai.com/v1")
    loaded = _to_config(
        {
            "llm_provider": {
                "providers": {
                    "openai": {"base_url": "https://api.openai.com/v1"},
                }
            }
        }
    ).llm_provider.providers["openai"]

    assert direct.compatibility_profile is None
    assert resolve_provider_profile("openai", direct) == resolve_provider_profile(
        "openai",
        loaded,
    )


def test_unknown_provider_defaults_to_compatible_wire_and_as_is_model() -> None:
    resolved = resolve_provider_profile("custom", LLMProviderConfig())

    assert resolved.wire_policy == OPENAI_COMPATIBLE
    assert resolved.model_id_policy is ModelIdPolicy.AS_IS
    assert resolved.model_catalog == ModelCatalog.NONE.value


@pytest.mark.parametrize(
    ("name", "expected_policy", "expected_catalog"),
    [
        ("openrouter", ModelIdPolicy.AUTHOR_PREFIX, ModelCatalog.OPENROUTER.value),
        ("orcarouter", ModelIdPolicy.AUTHOR_PREFIX, ModelCatalog.ORCAROUTER.value),
        ("atlascloud", ModelIdPolicy.AS_IS, ModelCatalog.NONE.value),
    ],
)
def test_provider_presets_resolve_model_and_catalog_independently(
    name,
    expected_policy,
    expected_catalog,
) -> None:
    resolved = resolve_provider_profile(name, LLMProviderConfig())

    assert resolved.wire_policy == OPENAI_COMPATIBLE
    assert resolved.model_id_policy is expected_policy
    assert resolved.model_catalog == expected_catalog


def test_explicit_config_overrides_model_policy_and_wire_profile() -> None:
    resolved = resolve_provider_profile(
        "openrouter",
        LLMProviderConfig(
            compatibility_profile="minimal_openai_compatible",
            model_id_policy="as_is",
        ),
    )

    assert resolved.wire_policy == MINIMAL_OPENAI_COMPATIBLE
    assert resolved.model_id_policy is ModelIdPolicy.AS_IS
    assert resolved.model_catalog == ModelCatalog.OPENROUTER.value


def test_legacy_router_url_fallback_is_explicit_and_warns_once() -> None:
    config = LLMProviderConfig(
        base_url="https://legacy-openrouter.example.openrouter.ai/v1",
    )

    with patch("dojoagents.logging.LOGGER.warning") as warning:
        first = resolve_provider_profile("legacy-custom", config)
        second = resolve_provider_profile("legacy-custom", config)

    assert first == second
    assert first.model_id_policy is ModelIdPolicy.AUTHOR_PREFIX
    assert first.model_catalog == ModelCatalog.OPENROUTER.value
    warning.assert_called_once()


def test_named_preset_wins_over_a_mismatched_legacy_router_url() -> None:
    config = LLMProviderConfig(
        base_url="https://api.orcarouter.ai/v1",
    )

    resolved = resolve_provider_profile("openrouter", config)

    assert resolved.model_id_policy is ModelIdPolicy.AUTHOR_PREFIX
    assert resolved.model_catalog == ModelCatalog.OPENROUTER.value


def test_explicit_model_policy_disables_legacy_url_inference() -> None:
    config = LLMProviderConfig(
        base_url="https://openrouter.ai/api/v1",
        model_id_policy="as_is",
    )

    resolved = resolve_provider_profile("custom", config)

    assert resolved.model_id_policy is ModelIdPolicy.AS_IS
    assert resolved.model_catalog == ModelCatalog.NONE.value


def test_url_classification_uses_the_hostname_not_substring_matches() -> None:
    misleading_openai = _to_config(
        {
            "llm_provider": {
                "providers": {
                    "openai": {
                        "base_url": "https://api.openai.com.evil.example/v1",
                    }
                }
            }
        }
    ).llm_provider.providers["openai"]
    query_only_router = LLMProviderConfig(
        base_url="https://gateway.example/v1?upstream=openrouter.ai",
    )

    assert misleading_openai.compatibility_profile == "openai_compatible"
    assert resolve_provider_profile(
        "custom",
        query_only_router,
    ).model_catalog == ModelCatalog.NONE.value


def test_loader_validates_and_preserves_explicit_profile_fields() -> None:
    config = _to_config(
        {
            "llm_provider": {
                "providers": {
                    "custom": {
                        "model": "model-a",
                        "compatibility_profile": "openai_native",
                        "model_id_policy": "author_prefix",
                    }
                }
            }
        }
    )
    provider = config.llm_provider.providers["custom"]

    assert provider.compatibility_profile == "openai_native"
    assert provider.model_id_policy == "author_prefix"

    with pytest.raises(ValueError, match="compatibility_profile"):
        _to_config(
            {
                "llm_provider": {
                    "providers": {
                        "custom": {"compatibility_profile": "invalid"},
                    }
                }
            }
        )


def test_loader_applies_native_preset_only_to_the_official_openai_endpoint() -> None:
    official = _to_config(
        {
            "llm_provider": {
                "providers": {
                    "openai": {
                        "model": "gpt-4.1",
                        "base_url": "https://api.openai.com/v1",
                    }
                }
            }
        }
    ).llm_provider.providers["openai"]
    custom = _to_config(
        {
            "llm_provider": {
                "providers": {
                    "openai": {
                        "model": "model-a",
                        "base_url": "https://strict.example/v1",
                    }
                }
            }
        }
    ).llm_provider.providers["openai"]

    assert official.compatibility_profile == "openai_native"
    assert custom.compatibility_profile == "openai_compatible"
    with pytest.raises(ValueError, match="model_id_policy"):
        _to_config(
            {
                "llm_provider": {
                    "providers": {
                        "custom": {"model_id_policy": "invalid"},
                    }
                }
            }
        )
