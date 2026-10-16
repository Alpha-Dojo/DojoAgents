from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Literal
from urllib.parse import urlparse

from dojoagents.agent.provider_contracts import OpenAIRequestPolicy


class CompatibilityProfile(StrEnum):
    OPENAI_COMPATIBLE = "openai_compatible"
    OPENAI_NATIVE = "openai_native"
    MINIMAL_OPENAI_COMPATIBLE = "minimal_openai_compatible"


class ModelIdPolicy(StrEnum):
    AS_IS = "as_is"
    AUTHOR_PREFIX = "author_prefix"


class ModelCatalog(StrEnum):
    OPENAI = "openai"
    OPENROUTER = "openrouter"
    ORCAROUTER = "orcarouter"
    NONE = "none"


OPENAI_COMPATIBLE = OpenAIRequestPolicy(
    message_name_policy="omit",
    empty_tools_policy="omit",
    stream_usage_policy="include",
)
OPENAI_NATIVE = OpenAIRequestPolicy(
    # The generated OpenAI chat schema does not allow a top-level `name` on
    # tool messages.  Keep internal speaker/tool names in session state, but
    # omit them from the official OpenAI wire shape just as we do for strict
    # compatible gateways.
    message_name_policy="omit",
    empty_tools_policy="omit",
    stream_usage_policy="include",
)
MINIMAL_OPENAI_COMPATIBLE = OpenAIRequestPolicy(
    message_name_policy="omit",
    empty_tools_policy="omit",
    stream_usage_policy="unsupported",
)

_WIRE_PROFILES = {
    CompatibilityProfile.OPENAI_COMPATIBLE: OPENAI_COMPATIBLE,
    CompatibilityProfile.OPENAI_NATIVE: OPENAI_NATIVE,
    CompatibilityProfile.MINIMAL_OPENAI_COMPATIBLE: MINIMAL_OPENAI_COMPATIBLE,
}


@dataclass(frozen=True)
class ProviderProfilePreset:
    compatibility_profile: CompatibilityProfile
    model_id_policy: ModelIdPolicy
    model_catalog: ModelCatalog


@dataclass(frozen=True)
class ResolvedProviderProfile:
    wire_policy: OpenAIRequestPolicy
    model_id_policy: ModelIdPolicy
    model_catalog: Literal["openai", "openrouter", "orcarouter", "none"]


_PROVIDER_PRESETS = {
    "openai": ProviderProfilePreset(
        CompatibilityProfile.OPENAI_NATIVE,
        ModelIdPolicy.AS_IS,
        ModelCatalog.OPENAI,
    ),
    "openrouter": ProviderProfilePreset(
        CompatibilityProfile.OPENAI_COMPATIBLE,
        ModelIdPolicy.AUTHOR_PREFIX,
        ModelCatalog.OPENROUTER,
    ),
    "orcarouter": ProviderProfilePreset(
        CompatibilityProfile.OPENAI_COMPATIBLE,
        ModelIdPolicy.AUTHOR_PREFIX,
        ModelCatalog.ORCAROUTER,
    ),
    "model-router": ProviderProfilePreset(
        CompatibilityProfile.OPENAI_COMPATIBLE,
        ModelIdPolicy.AUTHOR_PREFIX,
        ModelCatalog.OPENROUTER,
    ),
    "atlascloud": ProviderProfilePreset(
        CompatibilityProfile.OPENAI_COMPATIBLE,
        ModelIdPolicy.AS_IS,
        ModelCatalog.NONE,
    ),
}

_LEGACY_URL_WARNED: set[tuple[str, str]] = set()


def _url_hostname(base_url: Any) -> str:
    text = str(base_url or "").strip()
    if not text:
        return ""
    return (urlparse(text).hostname or "").lower()


def provider_profile_preset(provider_name: str) -> ProviderProfilePreset | None:
    return _PROVIDER_PRESETS.get(str(provider_name or "").strip().lower())


def _effective_preset(
    provider_name: str,
    base_url: Any,
) -> ProviderProfilePreset | None:
    """Resolve a named preset without misclassifying a custom OpenAI gateway."""

    normalized_name = str(provider_name or "").strip().lower()
    preset = provider_profile_preset(normalized_name)
    if preset is None:
        return None
    if normalized_name == "openai":
        hostname = _url_hostname(base_url)
        if hostname and hostname != "api.openai.com":
            return None
    return preset


def preset_compatibility_profile(
    provider_name: str,
    base_url: Any,
) -> CompatibilityProfile | None:
    """Return a wire preset only when the config still identifies that preset."""

    preset = _effective_preset(provider_name, base_url)
    return preset.compatibility_profile if preset is not None else None


def _legacy_router_catalog(base_url: Any) -> ModelCatalog | None:
    hostname = _url_hostname(base_url)
    if hostname == "orcarouter.ai" or hostname.endswith(".orcarouter.ai"):
        return ModelCatalog.ORCAROUTER
    if hostname == "openrouter.ai" or hostname.endswith(".openrouter.ai"):
        return ModelCatalog.OPENROUTER
    return None


def _warn_legacy_url_fallback(provider_name: str, base_url: str) -> None:
    from dojoagents.logging import LOGGER

    key = (provider_name, base_url)
    if key in _LEGACY_URL_WARNED:
        return
    _LEGACY_URL_WARNED.add(key)
    LOGGER.warning(
        "Provider %s uses deprecated Router URL inference; set "
        "model_id_policy and use a named Router preset before the next migration cycle",
        provider_name,
    )


def resolve_provider_profile(
    provider_name: str,
    config: Any,
) -> ResolvedProviderProfile:
    """Resolve wire, model-ID, and catalog behavior without network probing."""

    normalized_name = str(provider_name or "").strip().lower()
    base_url = getattr(config, "base_url", None)
    preset = _effective_preset(normalized_name, base_url)

    raw_profile = getattr(config, "compatibility_profile", None)
    if raw_profile is None:
        profile = preset.compatibility_profile if preset else CompatibilityProfile.OPENAI_COMPATIBLE
    else:
        try:
            profile = CompatibilityProfile(str(raw_profile).strip().lower())
        except ValueError as exc:
            raise ValueError(f"Unsupported compatibility_profile: {raw_profile!r}") from exc

    raw_model_policy = getattr(config, "model_id_policy", None)
    if raw_model_policy is not None:
        try:
            model_policy = ModelIdPolicy(str(raw_model_policy).strip().lower())
        except ValueError as exc:
            raise ValueError(f"Unsupported model_id_policy: {raw_model_policy!r}") from exc
    elif preset is not None:
        model_policy = preset.model_id_policy
    else:
        model_policy = ModelIdPolicy.AS_IS

    catalog = preset.model_catalog if preset is not None else ModelCatalog.NONE
    legacy_catalog = _legacy_router_catalog(base_url)
    if preset is None and raw_model_policy is None and legacy_catalog is not None:
        catalog = legacy_catalog
        model_policy = ModelIdPolicy.AUTHOR_PREFIX
        _warn_legacy_url_fallback(
            normalized_name or "custom",
            str(base_url or ""),
        )

    return ResolvedProviderProfile(
        wire_policy=_WIRE_PROFILES[profile],
        model_id_policy=model_policy,
        model_catalog=catalog.value,
    )
