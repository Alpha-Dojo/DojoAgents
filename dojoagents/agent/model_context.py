from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from dojoagents.config.models import LLMProviderConfig
from dojoagents.logging import LOGGER

_CACHE_TTL_SECONDS = 7 * 24 * 3600

# ponytail: pattern table, not exhaustive — override via provider.context_window
_MODEL_FALLBACKS: list[tuple[str, int]] = [
    ("gpt-4o", 128000),
    ("gpt-4.1", 128000),
    ("gpt-4", 128000),
    ("gpt-3.5", 16385),
    ("deepseek", 128000),
    ("qwen", 131072),
    ("moonshot", 131072),
    ("kimi", 131072),
    ("glm", 128000),
    ("claude", 200000),
    ("gemini", 1048576),
]


def _extract_context_from_model_payload(payload: Any) -> int | None:
    if payload is None:
        return None
    candidates: dict[str, Any] = {}
    if hasattr(payload, "model_dump"):
        candidates = payload.model_dump()
    elif isinstance(payload, dict):
        candidates = payload
    else:
        return None
    for key in ("context_length", "max_model_len", "context_window", "max_context_length"):
        value = candidates.get(key)
        if isinstance(value, int) and value > 0:
            return value
    return None


def _fallback_for_model(model_id: str, default: int) -> int:
    lowered = str(model_id).lower()
    for pattern, limit in _MODEL_FALLBACKS:
        if pattern in lowered:
            return limit
    return default


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

    def _read_cache(self, key: str) -> int | None:
        entry = self._cache.get(key)
        if not isinstance(entry, dict):
            return None
        if time.time() - float(entry.get("updated_at", 0)) > _CACHE_TTL_SECONDS:
            return None
        value = entry.get("context_window")
        return int(value) if isinstance(value, int) and value > 0 else None

    def _write_cache(self, key: str, context_window: int) -> None:
        self._cache[key] = {"context_window": context_window, "updated_at": time.time()}
        self._save_cache_file()

    async def resolve(
        self,
        provider_name: str,
        provider_cfg: LLMProviderConfig,
        *,
        client: Any | None = None,
    ) -> int:
        model_id = provider_cfg.model
        if provider_cfg.context_window and provider_cfg.context_window > 0:
            return int(provider_cfg.context_window)

        cache_key = self._cache_key(provider_name, model_id)
        cached = self._read_cache(cache_key)
        if cached is not None:
            return cached

        if client is not None and provider_cfg.api_key:
            try:
                model = await client.models.retrieve(model_id)
                resolved = _extract_context_from_model_payload(model)
                if resolved:
                    self._write_cache(cache_key, resolved)
                    return resolved
            except Exception:
                LOGGER.debug("model context API lookup failed for %s/%s", provider_name, model_id, exc_info=True)
            try:
                models = await client.models.list()
                data = getattr(models, "data", None) or []
                for item in data:
                    item_id = getattr(item, "id", None) or (item.get("id") if isinstance(item, dict) else None)
                    if item_id == model_id:
                        resolved = _extract_context_from_model_payload(item)
                        if resolved:
                            self._write_cache(cache_key, resolved)
                            return resolved
            except Exception:
                LOGGER.debug("model list context lookup failed for %s/%s", provider_name, model_id, exc_info=True)

        fallback = _fallback_for_model(model_id, self.default_context_window)
        self._write_cache(cache_key, fallback)
        return fallback

    def note_context_window(self, provider_name: str, model_id: str, context_window: int) -> None:
        if context_window <= 0:
            return
        self._write_cache(self._cache_key(provider_name, model_id), context_window)
