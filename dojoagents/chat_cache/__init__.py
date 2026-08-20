from __future__ import annotations

import copy
import importlib
import inspect
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol, runtime_checkable

from dojoagents.agent.models import ChatRequest
from dojoagents.config.models import ChatCacheConfig
from dojoagents.logging import LOGGER

_MARKERS = {
    "run_id": "$cache.run_id",
    "session_id": "$cache.session_id",
    "turn_id": "$cache.turn_id",
    "invocation_id": "$cache.invocation_id",
    "timestamp": "$cache.timestamp",
}


@dataclass(frozen=True)
class CacheHealth:
    healthy: bool
    detail: str = ""


@dataclass(frozen=True)
class CacheContext:
    provider: str
    model: str
    base_url_origin: str
    harness_id: str
    harness_version: str
    harness_state_schema_version: int


@dataclass(frozen=True)
class CachePlan:
    cache_id: str
    pattern_id: str
    locale: str
    ttl_seconds: int
    revision: str
    max_event_count: int = 5000
    max_entry_bytes: int = 4 * 1024 * 1024


@dataclass(frozen=True)
class CachedChat:
    cache_id: str
    pattern_id: str
    locale: str
    model_id: str
    response_content: str
    response_metadata: dict[str, Any]
    events: tuple[dict[str, Any], ...]
    created_at: datetime
    expires_at: datetime


@runtime_checkable
class ChatCache(Protocol):
    async def startup(self) -> None:
        raise NotImplementedError

    async def health(self) -> CacheHealth:
        raise NotImplementedError

    async def shutdown(self) -> None:
        raise NotImplementedError

    async def prepare(self, request: ChatRequest, context: CacheContext) -> CachePlan | None:
        raise NotImplementedError

    async def get(self, plan: CachePlan) -> CachedChat | None:
        raise NotImplementedError

    async def put(self, plan: CachePlan, value: CachedChat) -> None:
        raise NotImplementedError

    async def bind_run(self, plan: CachePlan, run_id: str, session_id: str, turn_id: str, replayed_at: datetime) -> None:
        raise NotImplementedError


def _template_runtime_ids(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): (_MARKERS[str(key)] if str(key) in {"run_id", "session_id", "turn_id", "invocation_id"} else _template_runtime_ids(item)) for key, item in value.items()}
    if isinstance(value, list):
        return [_template_runtime_ids(item) for item in value]
    if isinstance(value, tuple):
        return [_template_runtime_ids(item) for item in value]
    return copy.deepcopy(value)


def event_template(payload: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(payload)
    if str(result.get("type") or "") in {"token_usage", "turn_usage", "context_usage_snapshot"}:
        result = _template_runtime_ids(result)
    for key, marker in _MARKERS.items():
        if key in result:
            result[key] = marker
    return result


def _materialize_value(value: Any, replacements: dict[str, str]) -> Any:
    if isinstance(value, dict):
        return {str(key): _materialize_value(item, replacements) for key, item in value.items()}
    if isinstance(value, list):
        return [_materialize_value(item, replacements) for item in value]
    if isinstance(value, str) and value in replacements:
        return replacements[value]
    return copy.deepcopy(value)


def materialize_event_template(
    payload: dict[str, Any],
    *,
    run_id: str,
    session_id: str,
    turn_id: str,
    cache_id: str,
    source_created_at: datetime,
    replayed_at: datetime | None = None,
) -> dict[str, Any]:
    now = (replayed_at or datetime.now(UTC)).astimezone(UTC).isoformat()
    result = _materialize_value(
        payload,
        {
            "$cache.run_id": run_id,
            "$cache.session_id": session_id,
            "$cache.turn_id": turn_id,
            "$cache.invocation_id": f"{run_id}:cache:invocation",
            "$cache.timestamp": now,
        },
    )
    result["run_id"] = run_id
    result["session_id"] = session_id
    result["timestamp"] = now
    result["cache"] = {
        "hit": True,
        "cache_id": cache_id,
        "source_created_at": source_created_at.isoformat(),
    }
    return result


class CacheEventCollector:
    def __init__(self, plan: CachePlan) -> None:
        self.plan = plan
        self.events: list[dict[str, Any]] = []
        self.size_bytes = 0
        self.overflowed = False

    def __call__(self, event: Any) -> None:
        if self.overflowed:
            return
        payload = event_template(event.to_dict())
        size = len(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8"))
        if len(self.events) + 1 > self.plan.max_event_count or self.size_bytes + size > self.plan.max_entry_bytes:
            self.events.clear()
            self.size_bytes = 0
            self.overflowed = True
            return
        self.events.append(payload)
        self.size_bytes += size


def _load_factory(path: str):
    if ":" not in path:
        raise ValueError("chat cache factory must use module:attribute syntax")
    module_name, attribute = path.split(":", 1)
    factory = getattr(importlib.import_module(module_name), attribute)
    if not callable(factory):
        raise TypeError(f"configured chat cache factory {path!r} is not callable")
    return factory


async def create_chat_cache(config: ChatCacheConfig) -> ChatCache | None:
    if not config.enabled:
        return None
    if config.store.provider == "none" or not config.store.factory:
        raise ValueError("enabled chat cache requires an external store factory")
    cache = _load_factory(config.store.factory)(copy.deepcopy(config.store.options))
    if inspect.isawaitable(cache):
        cache = await cache
    if not isinstance(cache, ChatCache):
        raise TypeError(f"chat cache factory for provider {config.store.provider!r} returned an incompatible object")
    await cache.startup()
    health = await cache.health()
    if not health.healthy:
        LOGGER.warning("Chat cache provider %s is unhealthy: %s", config.store.provider, health.detail)
    return cache


async def shutdown_chat_cache(cache: ChatCache | None) -> None:
    if cache is None:
        return
    try:
        await cache.shutdown()
    except Exception:
        LOGGER.exception("Failed to shut down chat cache %s", type(cache).__name__)


__all__ = [
    "CacheContext",
    "CacheEventCollector",
    "CacheHealth",
    "CachePlan",
    "CachedChat",
    "ChatCache",
    "create_chat_cache",
    "event_template",
    "materialize_event_template",
    "shutdown_chat_cache",
]
