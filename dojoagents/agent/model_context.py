from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dojoagents.config.models import LLMProviderConfig
from dojoagents.logging import LOGGER

_CACHE_TTL_SECONDS = 7 * 24 * 3600
_OPENROUTER_MODELS_CACHE_KEY = "__openrouter_models__"

# ponytail: pattern table, not exhaustive — override via provider.context_window
_MODEL_FALLBACKS: list[tuple[str, int]] = [
    ("gpt-4o", 128000),
    ("gpt-4.1", 128000),
    ("gpt-4", 128000),
    ("gpt-3.5", 16385),
    ("deepseek", 65536),
    ("qwen", 131072),
    ("moonshot", 131072),
    ("kimi", 131072),
    ("glm", 128000),
    ("claude", 200000),
    ("gemini", 1048576),
]


@dataclass(frozen=True)
class ModelContextInfo:
    context_window: int
    input_modalities: tuple[str, ...] = ()
    output_modalities: tuple[str, ...] = ()
    canonical_slug: str | None = None
    provider_model_id: str | None = None
    author: str | None = None
    slug: str | None = None

    def supports_input_modality(self, modality: str) -> bool:
        return modality.strip().lower() in self.input_modalities

    def with_context_window(self, context_window: int) -> ModelContextInfo:
        return ModelContextInfo(
            context_window=context_window,
            input_modalities=self.input_modalities,
            output_modalities=self.output_modalities,
            canonical_slug=self.canonical_slug,
            provider_model_id=self.provider_model_id,
            author=self.author,
            slug=self.slug,
        )


def _payload_dict(payload: Any) -> dict[str, Any]:
    if payload is None:
        return {}
    if hasattr(payload, "model_dump"):
        dumped = payload.model_dump()
        return dict(dumped) if isinstance(dumped, dict) else {}
    if isinstance(payload, dict):
        return dict(payload)
    return {}


def _openrouter_data(payload: Any) -> dict[str, Any]:
    data = _payload_dict(payload)
    nested = data.get("data")
    return nested if isinstance(nested, dict) else data


def _extract_context_from_model_payload(payload: Any) -> int | None:
    candidates = _openrouter_data(payload)
    for key in ("context_length", "max_model_len", "context_window", "max_context_length"):
        value = candidates.get(key)
        if isinstance(value, int) and value > 0:
            return value
    top_provider = candidates.get("top_provider")
    if isinstance(top_provider, dict):
        value = top_provider.get("context_length")
        if isinstance(value, int) and value > 0:
            return value
    return None


def _clean_modalities(value: Any) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    modalities: list[str] = []
    for item in value:
        if isinstance(item, str) and item.strip():
            modalities.append(item.strip().lower())
    return tuple(dict.fromkeys(modalities))


def _split_openrouter_model_id(model_id: str | None) -> tuple[str, str] | None:
    if not isinstance(model_id, str) or "/" not in model_id:
        return None
    author, slug = model_id.split("/", 1)
    author = author.strip()
    slug = slug.strip()
    if not author or not slug:
        return None
    return author, slug


def _normalize_match_part(value: str | None) -> str:
    return value.strip().lower() if isinstance(value, str) else ""


def _extract_model_info(payload: Any) -> ModelContextInfo | None:
    data = _openrouter_data(payload)
    context_window = _extract_context_from_model_payload(data)
    if context_window is None:
        return None
    architecture = data.get("architecture")
    if not isinstance(architecture, dict):
        architecture = {}
    provider_model_id = data.get("id") if isinstance(data.get("id"), str) else None
    parsed = _split_openrouter_model_id(provider_model_id)
    return ModelContextInfo(
        context_window=context_window,
        input_modalities=_clean_modalities(architecture.get("input_modalities")),
        output_modalities=_clean_modalities(architecture.get("output_modalities")),
        canonical_slug=data.get("canonical_slug") if isinstance(data.get("canonical_slug"), str) else None,
        provider_model_id=provider_model_id,
        author=parsed[0] if parsed else None,
        slug=parsed[1] if parsed else None,
    )


def _fallback_for_model(model_id: str, default: int) -> int:
    lowered = str(model_id).lower()
    for pattern, limit in _MODEL_FALLBACKS:
        if pattern in lowered:
            return limit
    return default


def _is_openrouter_config(provider_cfg: LLMProviderConfig) -> bool:
    base_url = provider_cfg.base_url or ""
    if not isinstance(base_url, str):
        return False
    return "openrouter.ai" in base_url.lower()


def _openrouter_lookup_parts(provider_cfg: LLMProviderConfig) -> tuple[str | None, str | None]:
    model_id = provider_cfg.model
    parsed = _split_openrouter_model_id(model_id)
    author = provider_cfg.author.strip() if isinstance(provider_cfg.author, str) and provider_cfg.author.strip() else None
    if parsed is not None:
        return author or parsed[0], parsed[1]
    slug = model_id.strip() if isinstance(model_id, str) and model_id.strip() else None
    return author, slug


def _should_lookup_openrouter_info(provider_cfg: LLMProviderConfig) -> bool:
    author, slug = _openrouter_lookup_parts(provider_cfg)
    if not slug:
        return False
    return bool(author or _is_openrouter_config(provider_cfg))


class ModelContextRegistry:
    def __init__(
        self,
        cache_path: str | Path = "~/.dojo/agents/model_limits.json",
        *,
        default_context_window: int = 32768,
    ) -> None:
        self.cache_path = Path(cache_path).expanduser()
        self.default_context_window = default_context_window
        self._cache: dict[str, Any] = {}
        self._load_cache_file()

    def _load_cache_file(self) -> None:
        if not self.cache_path.exists():
            self._cache = {}
            return
        try:
            self._cache = json.loads(self.cache_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            self._cache = {}

    def _save_cache_file(self) -> None:
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        self.cache_path.write_text(json.dumps(self._cache, ensure_ascii=False, indent=2), encoding="utf-8")

    def _cache_key(self, provider_name: str, model_id: str) -> str:
        return f"{provider_name}:{model_id}"

    def _read_cache_info(self, key: str) -> ModelContextInfo | None:
        entry = self._cache.get(key)
        if not isinstance(entry, dict):
            return None
        if time.time() - float(entry.get("updated_at", 0)) > _CACHE_TTL_SECONDS:
            return None
        value = entry.get("context_window")
        if not isinstance(value, int) or value <= 0:
            return None
        return ModelContextInfo(
            context_window=int(value),
            input_modalities=_clean_modalities(entry.get("input_modalities")),
            output_modalities=_clean_modalities(entry.get("output_modalities")),
            canonical_slug=entry.get("canonical_slug") if isinstance(entry.get("canonical_slug"), str) else None,
            provider_model_id=entry.get("provider_model_id") if isinstance(entry.get("provider_model_id"), str) else None,
            author=entry.get("author") if isinstance(entry.get("author"), str) else None,
            slug=entry.get("slug") if isinstance(entry.get("slug"), str) else None,
        )

    def _read_cache(self, key: str) -> int | None:
        info = self._read_cache_info(key)
        return info.context_window if info is not None else None

    def _write_cache_info(self, key: str, info: ModelContextInfo) -> None:
        self._cache[key] = {
            "context_window": int(info.context_window),
            "input_modalities": list(info.input_modalities),
            "output_modalities": list(info.output_modalities),
            "canonical_slug": info.canonical_slug,
            "provider_model_id": info.provider_model_id,
            "author": info.author,
            "slug": info.slug,
            "updated_at": time.time(),
        }
        self._save_cache_file()

    def _write_cache(self, key: str, context_window: int) -> None:
        self._write_cache_info(key, ModelContextInfo(context_window=context_window))

    def _model_info_to_cache_entry(self, info: ModelContextInfo) -> dict[str, Any]:
        return {
            "context_window": int(info.context_window),
            "input_modalities": list(info.input_modalities),
            "output_modalities": list(info.output_modalities),
            "canonical_slug": info.canonical_slug,
            "provider_model_id": info.provider_model_id,
            "author": info.author,
            "slug": info.slug,
        }

    def _model_info_from_cache_entry(self, entry: Any) -> ModelContextInfo | None:
        if not isinstance(entry, dict):
            return None
        value = entry.get("context_window")
        if not isinstance(value, int) or value <= 0:
            return None
        return ModelContextInfo(
            context_window=value,
            input_modalities=_clean_modalities(entry.get("input_modalities")),
            output_modalities=_clean_modalities(entry.get("output_modalities")),
            canonical_slug=entry.get("canonical_slug") if isinstance(entry.get("canonical_slug"), str) else None,
            provider_model_id=entry.get("provider_model_id") if isinstance(entry.get("provider_model_id"), str) else None,
            author=entry.get("author") if isinstance(entry.get("author"), str) else None,
            slug=entry.get("slug") if isinstance(entry.get("slug"), str) else None,
        )

    def _read_openrouter_models_cache(self) -> list[ModelContextInfo] | None:
        entry = self._cache.get(_OPENROUTER_MODELS_CACHE_KEY)
        if not isinstance(entry, dict):
            return None
        if time.time() - float(entry.get("updated_at", 0)) > _CACHE_TTL_SECONDS:
            return None
        models = entry.get("models")
        if not isinstance(models, list):
            return None
        infos = [info for info in (self._model_info_from_cache_entry(item) for item in models) if info is not None]
        return infos or None

    def _write_openrouter_models_cache(self, infos: list[ModelContextInfo]) -> None:
        updated_at = time.time()
        self._cache[_OPENROUTER_MODELS_CACHE_KEY] = {
            "models": [self._model_info_to_cache_entry(info) for info in infos],
            "updated_at": updated_at,
        }
        for info in infos:
            if info.provider_model_id:
                self._cache[self._cache_key("openrouter", info.provider_model_id)] = {
                    **self._model_info_to_cache_entry(info),
                    "updated_at": updated_at,
                }
        self._save_cache_file()

    def _match_openrouter_info(self, infos: list[ModelContextInfo], provider_cfg: LLMProviderConfig, provider_name: str) -> ModelContextInfo | None:
        if provider_name == "model-router":
            author = None
            slug = provider_cfg.model.split("/")[-1] if provider_cfg.model else None
        else:
            author, slug = _openrouter_lookup_parts(provider_cfg)

        if not slug:
            return None
        expected_author = _normalize_match_part(author) if author else None
        expected_slug = _normalize_match_part(slug)
        for info in infos:
            if _normalize_match_part(info.slug) != expected_slug:
                continue
            if expected_author and _normalize_match_part(info.author) != expected_author:
                continue
            return info
        return None

    async def _retrieve_openrouter_info(self, provider_cfg: LLMProviderConfig, provider_name: str) -> ModelContextInfo | None:
        if provider_name == "model-router":
            should_lookup = True
        else:
            should_lookup = _should_lookup_openrouter_info(provider_cfg)

        if not provider_cfg.model or not should_lookup:
            return None

        cached_models = self._read_openrouter_models_cache()
        if cached_models:
            match = self._match_openrouter_info(cached_models, provider_cfg, provider_name)
            if match:
                return match

        try:
            import httpx

            url = "https://openrouter.ai/api/v1/models"
            headers: dict[str, str] = {}
            if provider_cfg.api_key:
                headers["Authorization"] = f"Bearer {provider_cfg.api_key}"
            async with httpx.AsyncClient(timeout=10.0) as http:
                response = await http.get(url, headers=headers)
                response.raise_for_status()
                payload = response.json()
            data = payload.get("data") if isinstance(payload, dict) else None
            if not isinstance(data, list):
                return None
            infos = [info for info in (_extract_model_info(item) for item in data) if info is not None and info.author and info.slug]
            if not infos:
                return None
            self._write_openrouter_models_cache(infos)
            return self._match_openrouter_info(infos, provider_cfg, provider_name)
        except Exception:
            LOGGER.debug("OpenRouter model list lookup failed for %s", provider_cfg.model, exc_info=True)
            return None

    async def resolve(
        self,
        provider_name: str,
        provider_cfg: LLMProviderConfig,
    ) -> int:
        info = await self.resolve_info(provider_name, provider_cfg)
        return info.context_window

    async def resolve_info(
        self,
        provider_name: str,
        provider_cfg: LLMProviderConfig,
    ) -> ModelContextInfo:
        model_id = provider_cfg.model
        openrouter_info = await self._retrieve_openrouter_info(provider_cfg, provider_name)
        if provider_cfg.context_window and provider_cfg.context_window > 0:
            override = int(provider_cfg.context_window)
            if not model_id:
                return ModelContextInfo(context_window=override)
            cache_key = self._cache_key(provider_name, model_id)
            if openrouter_info is not None:
                info = openrouter_info.with_context_window(override)
                self._write_cache_info(cache_key, info)
                return info
            cached = self._read_cache_info(cache_key)
            if cached is not None:
                return cached.with_context_window(override)
            return ModelContextInfo(context_window=override)
        if not model_id:
            return ModelContextInfo(context_window=self.default_context_window)

        cache_key = self._cache_key(provider_name, model_id)
        cached = self._read_cache_info(cache_key)
        if cached is not None:
            return cached

        if openrouter_info is not None:
            self._write_cache_info(cache_key, openrouter_info)
            return openrouter_info

        fallback = _fallback_for_model(model_id, self.default_context_window)
        info = ModelContextInfo(context_window=fallback)
        self._write_cache_info(cache_key, info)
        return info

    def note_context_window(self, provider_name: str, model_id: str, context_window: int) -> None:
        if context_window <= 0:
            return
        key = self._cache_key(provider_name, model_id)
        cached = self._read_cache_info(key)
        if cached is not None:
            self._write_cache_info(
                key,
                ModelContextInfo(
                    context_window=context_window,
                    input_modalities=cached.input_modalities,
                    output_modalities=cached.output_modalities,
                    canonical_slug=cached.canonical_slug,
                    provider_model_id=cached.provider_model_id,
                    author=cached.author,
                    slug=cached.slug,
                ),
            )
            return
        self._write_cache(key, context_window)

    def cached_info(self, provider_name: str, model_id: str) -> ModelContextInfo | None:
        return self._read_cache_info(self._cache_key(provider_name, model_id))
