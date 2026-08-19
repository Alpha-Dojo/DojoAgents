from dataclasses import asdict
from datetime import datetime
from pathlib import Path

import pytest

from dojoagents.agent.events import AgentEventSink
from dojoagents.agent.loop import AgentLoop
from dojoagents.agent.models import ChatRequest, LLMResult
from dojoagents.agent.providers import StaticLLMProvider
from dojoagents.chat_cache import CacheContext, CacheHealth, CachePlan, CachedChat, create_chat_cache, event_template, shutdown_chat_cache
from dojoagents.config.loader import _to_config
from dojoagents.config.models import AgentConfig, AgentsConfig, ChatCacheConfig, SessionRuntimeConfig, SessionsConfig, StoreProviderConfig
from dojoagents.dojo_extensions.registry import DojoExtensionRegistry
from dojoagents.harnesses.base import HarnessDescriptor
from dojoagents.memory.manager import MemoryManager
from dojoagents.sessions.blobs.file import FileBlobStore
from dojoagents.sessions.models import HistoryQuery, SessionPrincipal, TurnQuery, UsageQuery
from dojoagents.sessions.service import SessionService
from dojoagents.sessions.stores.file import FileSessionStore
from dojoagents.skills.manager import SkillManager
from dojoagents.tools.executor import ToolExecutor
from dojoagents.tools.registry import ToolRegistry
from dojoagents.tools.sandbox import SandboxPolicy


class MemoryChatCache:
    def __init__(self) -> None:
        self.value: CachedChat | None = None
        self.bindings: list[tuple[str, str, str, str, datetime]] = []
        self.started = False
        self.stopped = False
        self.contexts: list[CacheContext] = []

    async def startup(self) -> None:
        self.started = True

    async def health(self) -> CacheHealth:
        return CacheHealth(True)

    async def shutdown(self) -> None:
        self.stopped = True

    async def prepare(self, request: ChatRequest, context: CacheContext) -> CachePlan | None:
        self.contexts.append(context)
        if request.metadata.get("history"):
            return None
        return CachePlan(
            cache_id="cc1_shared",
            pattern_id="public.en",
            locale="en",
            ttl_seconds=60,
            revision="1",
            max_event_count=100,
            max_entry_bytes=100_000,
        )

    async def get(self, plan: CachePlan) -> CachedChat | None:
        return self.value

    async def put(self, plan: CachePlan, value: CachedChat) -> None:
        self.value = value

    async def bind_run(self, plan: CachePlan, run_id: str, session_id: str, turn_id: str, replayed_at: datetime) -> None:
        self.bindings.append((plan.cache_id, run_id, session_id, turn_id, replayed_at))


_FACTORY_CACHE: MemoryChatCache | None = None


def create_test_chat_cache(_options):
    global _FACTORY_CACHE
    _FACTORY_CACHE = MemoryChatCache()
    return _FACTORY_CACHE


async def _service(tmp_path: Path) -> SessionService:
    store = FileSessionStore(tmp_path / "sessions", cursor_secret=b"secret")
    blobs = FileBlobStore(tmp_path / "blobs")
    config = SessionsConfig(
        store=StoreProviderConfig(options={"root": str(tmp_path / "sessions")}),
        blob_store=StoreProviderConfig(options={"root": str(tmp_path / "blobs")}),
        runtime=SessionRuntimeConfig(),
        sync_memory=False,
    )
    service = SessionService(store=store, blob_store=blobs, config=config)
    await service.startup()
    return service


def _loop(provider, service: SessionService, cache: MemoryChatCache) -> AgentLoop:
    loop = AgentLoop(
        llm_provider=provider,
        tool_executor=ToolExecutor(ToolRegistry(), SandboxPolicy(timeout_seconds=2)),
        skill_manager=SkillManager([]),
        memory_manager=MemoryManager(),
        extension_registry=DojoExtensionRegistry(),
        config=AgentConfig(model="test-model", enable_guardrails=False, enable_context_compression=False),
        session_service=service,
        harness_descriptor=HarnessDescriptor("minimal", "1", "Minimal"),
        chat_cache=cache,
    )
    loop.model_context_registry.cache_path = Path(service.config.store.options["root"]) / "model_limits.json"
    return loop


def test_event_template_preserves_public_tool_data_timestamps() -> None:
    template = event_template(
        {
            "type": "tool_result",
            "run_id": "source-run",
            "session_id": "source-session",
            "timestamp": "event-time",
            "data": {"timestamp": "market-time", "run_id": "public-domain-value"},
        }
    )

    assert template["run_id"] == "$cache.run_id"
    assert template["session_id"] == "$cache.session_id"
    assert template["timestamp"] == "$cache.timestamp"
    assert template["data"] == {"timestamp": "market-time", "run_id": "public-domain-value"}


def test_chat_cache_config_is_disabled_by_default_and_accepts_external_factory() -> None:
    assert AgentsConfig().chat_cache.enabled is False
    raw = asdict(AgentsConfig())
    raw["chat_cache"] = {
        "enabled": True,
        "store": {
            "provider": "redis",
            "factory": "project.cache:create",
            "options": {"default_ttl_seconds": 43200, "max_entries": 10000},
        },
    }

    config = _to_config(raw)

    assert config.chat_cache.enabled is True
    assert config.chat_cache.store.provider == "redis"
    assert config.chat_cache.store.factory == "project.cache:create"
    assert config.chat_cache.store.options["max_entries"] == 10000

    raw["chat_cache"]["enabled"] = "false"
    with pytest.raises(ValueError, match="must be a boolean"):
        _to_config(raw)


@pytest.mark.asyncio
async def test_external_chat_cache_factory_lifecycle() -> None:
    cache = await create_chat_cache(
        ChatCacheConfig(
            enabled=True,
            store=StoreProviderConfig(
                provider="memory",
                factory=f"{__name__}:create_test_chat_cache",
            ),
        )
    )

    assert cache is _FACTORY_CACHE
    assert cache.started is True
    await shutdown_chat_cache(cache)
    assert cache.stopped is True


@pytest.mark.asyncio
async def test_cache_hit_is_shared_across_principals_and_replays_into_new_canonical_run(tmp_path: Path) -> None:
    service = await _service(tmp_path)
    provider = StaticLLMProvider([LLMResult("shared answer")])
    cache = MemoryChatCache()
    provider.base_url = "https://user:password@llm.example:8443/v1?api_key=secret"
    loop = _loop(provider, service, cache)
    alice = SessionPrincipal("alice", "tenant-a")
    bob = SessionPrincipal("bob", "tenant-b")

    first = await loop.run(
        ChatRequest("public question", session_id="session-a", principal=alice),
        event_sink=AgentEventSink(run_id="run-a", session_id="session-a"),
    )
    second = await loop.run(
        ChatRequest("public question", session_id="session-b", principal=bob),
        event_sink=AgentEventSink(run_id="run-b", session_id="session-b"),
    )

    assert first.content == second.content == "shared answer"
    assert {context.base_url_origin for context in cache.contexts} == {"https://llm.example:8443"}
    assert len(provider.calls) == 1
    assert cache.value is not None
    assert "run-a" not in repr(cache.value.events)
    assert "session-a" not in repr(cache.value.events)
    assert len(cache.bindings) == 1
    assert cache.bindings[0][:3] == ("cc1_shared", "run-b", "session-b")
    assert cache.bindings[0][3].startswith("turn-")
    assert isinstance(cache.bindings[0][4], datetime)
    assert second.metadata["cache"]["hit"] is True
    assert second.metadata["cache"]["cache_id"] == "cc1_shared"

    runs = await service.list_runs(bob, "session-b")
    events = await service.read_events(bob, "run-b", after_seq=0, limit=100)
    history = await service.history(bob, "session-b", HistoryQuery())
    turns = await service.turns(bob, "session-b", TurnQuery())
    usage = await service.usage(bob, "session-b", UsageQuery())
    assert runs[0].status == "completed"
    assert [message.role for message in history.items] == ["user", "assistant"]
    assert turns.items[0].output == {"content": "shared answer"}
    assert turns.items[0].completion["cache"] == {"hit": True, "cache_id": "cc1_shared"}
    assert events.items
    assert all(event.payload["run_id"] == "run-b" for event in events.items)
    assert all(event.payload["session_id"] == "session-b" for event in events.items)
    cached_events = [event for event in events.items if "cache" in event.payload]
    assert cached_events
    assert all(event.payload["cache"]["hit"] is True for event in cached_events)
    assert usage.calls == 0
    await service.shutdown()
