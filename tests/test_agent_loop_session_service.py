import asyncio

import pytest
from unittest.mock import AsyncMock, patch

from dojoagents.agent.loop import AgentLoop
from dojoagents.agent.events import AgentEventSink
from dojoagents.agent.models import ChatRequest, LLMResult
from dojoagents.agent.providers import StaticLLMProvider
from dojoagents.config.models import AgentConfig, SessionsConfig, StoreProviderConfig
from dojoagents.dojo_extensions.registry import DojoExtensionRegistry
from dojoagents.harnesses.base import HarnessDescriptor
from dojoagents.memory.manager import MemoryManager
from dojoagents.sessions.blobs.file import FileBlobStore
from dojoagents.sessions.models import HistoryQuery, SessionListQuery, SessionPrincipal, TurnQuery
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


async def _service(tmp_path):
    store = FileSessionStore(tmp_path / "sessions", cursor_secret=b"secret")
    blobs = FileBlobStore(tmp_path / "blobs")
    config = SessionsConfig(
        store=StoreProviderConfig(options={"root": str(tmp_path / "sessions")}),
        blob_store=StoreProviderConfig(options={"root": str(tmp_path / "blobs")}),
    )
    service = SessionService(store=store, blob_store=blobs, config=config)
    await service.startup()
    return service


def _loop(provider, service):
    return AgentLoop(
        llm_provider=provider,
        tool_executor=ToolExecutor(ToolRegistry(), SandboxPolicy(timeout_seconds=2)),
        skill_manager=SkillManager([]),
        memory_manager=MemoryManager(),
        extension_registry=DojoExtensionRegistry(),
        config=AgentConfig(model="test-model", enable_guardrails=False, enable_context_compression=False),
        session_service=service,
        harness_descriptor=HarnessDescriptor("minimal", "1", "Minimal"),
    )


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
    assert response.content == "hello"
    assert sessions.items[0].harness_id == "minimal"
    assert len(turns.items) == 1
    assert turns.items[0].input == {"message": "hi", "context": {}}
    assert turns.items[0].output == {"content": "hello"}
    assert [message.role for message in history.items] == ["user", "assistant"]
    assert runs[0].status == "completed"
    await service.shutdown()


@pytest.mark.asyncio
async def test_model_exception_marks_canonical_run_failed(tmp_path):
    service = await _service(tmp_path)
    principal = SessionPrincipal("alice")
    loop = _loop(FailingProvider(), service)

    with pytest.raises(RuntimeError, match="model failed"):
        await loop.run(ChatRequest("hi", session_id="s1", principal=principal))

    runs = await service.list_runs(principal, "s1")
    assert len(runs) == 1
    assert runs[0].status == "failed"
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
    sink = AgentEventSink(run_id="run-external", session_id="s1")

    await loop.run(
        ChatRequest("hi", session_id="s1", principal=principal),
        event_sink=sink,
    )

    runs = await service.list_runs(principal, "s1")
    events = await service.read_events(principal, "run-external", after_seq=0, limit=100)
    assert runs[0].run_id == "run-external"
    assert events.items
    assert all(event.payload["run_id"] == "run-external" for event in events.items)
    await service.shutdown()
