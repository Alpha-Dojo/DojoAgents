import asyncio
from pathlib import Path

import pytest
from unittest.mock import AsyncMock, patch

from dojoagents.agent.loop import AgentLoop
from dojoagents.agent.events import AgentEventSink
from dojoagents.agent.models import ChatRequest, LLMResult
from dojoagents.agent.providers import StaticLLMProvider
from dojoagents.config.models import AgentConfig, SessionRuntimeConfig, SessionsConfig, StoreProviderConfig
from dojoagents.dojo_extensions.registry import DojoExtensionRegistry
from dojoagents.harnesses.base import HarnessDescriptor
from dojoagents.memory.manager import MemoryManager
from dojoagents.sessions.blobs.file import FileBlobStore
from dojoagents.sessions.models import (
    ContextUsageQuery,
    HistoryQuery,
    SessionListQuery,
    SessionPrincipal,
    TurnQuery,
    UsageQuery,
)
from dojoagents.sessions.service import SessionService
from dojoagents.sessions.errors import SessionLeaseLostError
from dojoagents.sessions.stores.file import FileSessionStore
from dojoagents.skills.manager import SkillManager
from dojoagents.tools.executor import ToolExecutor
from dojoagents.tools.registry import ToolRegistry
from dojoagents.tools.sandbox import SandboxPolicy


class FailingProvider:
    name = "failing"

    async def chat(self, *args, **kwargs):
        raise RuntimeError("model failed")


class BlockingProvider:
    name = "blocking"

    def __init__(self):
        self.started = asyncio.Event()
        self.release = asyncio.Event()

    async def chat(self, *args, **kwargs):
        self.started.set()
        await self.release.wait()
        return LLMResult("hello")


async def _service(tmp_path, *, runtime_config=None):
    store = FileSessionStore(tmp_path / "sessions", cursor_secret=b"secret")
    blobs = FileBlobStore(tmp_path / "blobs")
    config = SessionsConfig(
        store=StoreProviderConfig(options={"root": str(tmp_path / "sessions")}),
        blob_store=StoreProviderConfig(options={"root": str(tmp_path / "blobs")}),
        runtime=runtime_config or SessionRuntimeConfig(),
    )
    service = SessionService(store=store, blob_store=blobs, config=config)
    await service.startup()
    return service


def _loop(provider, service):
    loop = AgentLoop(
        llm_provider=provider,
        tool_executor=ToolExecutor(ToolRegistry(), SandboxPolicy(timeout_seconds=2)),
        skill_manager=SkillManager([]),
        memory_manager=MemoryManager(),
        extension_registry=DojoExtensionRegistry(),
        config=AgentConfig(model="test-model", enable_guardrails=False, enable_context_compression=False),
        session_service=service,
        harness_descriptor=HarnessDescriptor("minimal", "1", "Minimal"),
    )
    config = getattr(service, "config", None)
    store_root = getattr(getattr(config, "store", None), "options", {}).get("root")
    if store_root:
        loop.model_context_registry.cache_path = Path(store_root) / "model_limits.json"
    return loop


@pytest.mark.asyncio
async def test_success_commits_one_canonical_turn_and_terminal_run(tmp_path):
    service = await _service(tmp_path)
    principal = SessionPrincipal("alice")
    loop = _loop(StaticLLMProvider([LLMResult("hello")]), service)

    response = await loop.run(ChatRequest("hi", session_id="s1", principal=principal))

    sessions = await service.list_sessions(principal, SessionListQuery())
    turns = await service.turns(principal, "s1", TurnQuery())
    runs = await service.list_runs(principal, "s1")
    history = await service.history(principal, "s1", HistoryQuery())
    usage = await service.usage(principal, "s1", UsageQuery())
    context_usage = await service.context_usage(
        principal,
        "s1",
        ContextUsageQuery(),
    )
    assert response.content == "hello"
    assert sessions.items[0].harness_id == "minimal"
    assert len(turns.items) == 1
    assert turns.items[0].input == {"message": "hi", "context": {}}
    assert turns.items[0].output == {"content": "hello"}
    assert [message.role for message in history.items] == ["user", "assistant"]
    assert runs[0].status == "completed"
    assert response.metadata["usage"]["total_tokens"] > 0
    assert usage.calls == 1
    assert usage.records[0].turn_id == turns.items[0].turn_id
    assert usage.records[0].category == "agent_inference"
    assert usage.records[0].quality == "estimated"
    assert context_usage.latest is not None
    assert context_usage.latest.invocation_id == usage.records[0].invocation_id
    assert {item.category for item in context_usage.latest.components} >= {
        "system_prompt",
        "conversation",
    }
    await service.shutdown()


@pytest.mark.asyncio
async def test_model_exception_marks_canonical_run_failed(tmp_path):
    service = await _service(tmp_path)
    principal = SessionPrincipal("alice")
    loop = _loop(FailingProvider(), service)

    with pytest.raises(RuntimeError, match="model failed"):
        await loop.run(ChatRequest("hi", session_id="s1", principal=principal))

    runs = await service.list_runs(principal, "s1")
    usage = await service.usage(principal, "s1", UsageQuery())
    assert len(runs) == 1
    assert runs[0].status == "failed"
    assert usage.calls == 1
    assert usage.records[0].status == "failed"
    assert usage.records[0].quality == "unavailable"
    await service.shutdown()


@pytest.mark.asyncio
async def test_lease_loss_stops_without_attempting_another_terminal_write():
    canonical = AsyncMock()
    canonical.request = ChatRequest("hi", session_id="s1", principal=SessionPrincipal("alice"))
    canonical.event_sink = None
    canonical.commit.side_effect = SessionLeaseLostError("lost")
    loop = _loop(StaticLLMProvider([LLMResult("hello")]), service=object())

    with patch("dojoagents.agent.session_run.CanonicalAgentRun.begin", return_value=canonical):
        with pytest.raises(SessionLeaseLostError):
            await loop.run(canonical.request)

    canonical.fail.assert_not_awaited()
    canonical.cancel.assert_not_awaited()


@pytest.mark.asyncio
async def test_cancelled_turn_uses_cancel_terminal_path_only():
    canonical = AsyncMock()
    canonical.request = ChatRequest("hi", session_id="s1", principal=SessionPrincipal("alice"))
    canonical.event_sink = None
    loop = _loop(StaticLLMProvider([LLMResult("hello")]), service=object())
    loop._run_core = AsyncMock(side_effect=asyncio.CancelledError())

    with patch("dojoagents.agent.session_run.CanonicalAgentRun.begin", return_value=canonical):
        with pytest.raises(asyncio.CancelledError):
            await loop.run(canonical.request)

    canonical.cancel.assert_awaited_once()
    canonical.fail.assert_not_awaited()


@pytest.mark.asyncio
async def test_external_event_sink_and_canonical_run_share_one_run_id(tmp_path):
    service = await _service(tmp_path)
    principal = SessionPrincipal("alice")
    loop = _loop(StaticLLMProvider([LLMResult("hello")]), service)
    emitted = []
    sink = AgentEventSink(
        run_id="run-external",
        session_id="s1",
        emit=emitted.append,
    )

    await loop.run(
        ChatRequest("hi", session_id="s1", principal=principal),
        event_sink=sink,
    )

    runs = await service.list_runs(principal, "s1")
    events = await service.read_events(principal, "run-external", after_seq=0, limit=100)
    assert runs[0].run_id == "run-external"
    assert events.items
    assert all(event.payload["run_id"] == "run-external" for event in events.items)
    assert len(emitted) == len(sink.events)
    assert len(events.items) == len(sink.events)
    event_types = [event.event_type for event in events.items]
    assert event_types.count("context_usage_snapshot") == 2
    assert event_types[-2:] == ["turn_usage", "done"]
    await service.shutdown()


@pytest.mark.asyncio
async def test_canonical_events_are_persisted_before_run_completes(tmp_path):
    service = await _service(tmp_path)
    principal = SessionPrincipal("alice")
    provider = BlockingProvider()
    loop = _loop(provider, service)
    sink = AgentEventSink(run_id="run-live", session_id="s1")

    task = asyncio.create_task(
        loop.run(
            ChatRequest("hi", session_id="s1", principal=principal),
            event_sink=sink,
        )
    )
    await asyncio.wait_for(provider.started.wait(), timeout=2)

    page = None
    for _ in range(100):
        page = await service.read_events(principal, "run-live", after_seq=0, limit=100)
        if page.items:
            break
        await asyncio.sleep(0.01)

    assert page is not None
    assert page.items
    assert (await service.get_run(principal, "run-live")).status == "running"

    provider.release.set()
    response = await asyncio.wait_for(task, timeout=2)
    assert response.content == "hello"
    assert (await service.get_run(principal, "run-live")).status == "completed"
    await service.shutdown()


@pytest.mark.asyncio
async def test_canonical_heartbeat_keeps_long_run_lease_alive(tmp_path):
    service = await _service(
        tmp_path,
        runtime_config=SessionRuntimeConfig(
            lease_seconds=1,
            heartbeat_seconds=0,
            event_batch_size=20,
        ),
    )
    principal = SessionPrincipal("alice")
    provider = BlockingProvider()
    loop = _loop(provider, service)

    task = asyncio.create_task(
        loop.run(
            ChatRequest("hi", session_id="s1", principal=principal),
            event_sink=AgentEventSink(run_id="run-heartbeat", session_id="s1"),
        )
    )
    await asyncio.wait_for(provider.started.wait(), timeout=2)
    await asyncio.sleep(1.2)
    provider.release.set()

    response = await asyncio.wait_for(task, timeout=2)
    assert response.content == "hello"
    assert (await service.get_run(principal, "run-heartbeat")).status == "completed"
    await service.shutdown()


@pytest.mark.asyncio
async def test_canonical_heartbeat_converts_cancel_request_to_terminal_cancel(tmp_path):
    service = await _service(
        tmp_path,
        runtime_config=SessionRuntimeConfig(
            lease_seconds=3,
            heartbeat_seconds=0,
            event_batch_size=20,
        ),
    )
    principal = SessionPrincipal("alice")
    provider = BlockingProvider()
    loop = _loop(provider, service)

    task = asyncio.create_task(
        loop.run(
            ChatRequest("hi", session_id="s1", principal=principal),
            event_sink=AgentEventSink(run_id="run-cancel-live", session_id="s1"),
        )
    )
    await asyncio.wait_for(provider.started.wait(), timeout=2)
    await service.request_cancel(principal, "run-cancel-live")

    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(task, timeout=2)

    run = await service.get_run(principal, "run-cancel-live")
    events = await service.read_events(principal, "run-cancel-live", after_seq=0, limit=100)
    usage = await service.usage(principal, "s1", UsageQuery())
    assert run.status == "cancelled"
    assert usage.calls == 1
    assert usage.records[0].status == "cancelled"
    assert events.items[-1].event_type == "error"
    assert events.items[-1].payload["code"] == "cancelled"
    await service.shutdown()
