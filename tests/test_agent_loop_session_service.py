import asyncio
import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from unittest.mock import AsyncMock, patch

from dojoagents.agent.loop import AgentLoop
from dojoagents.agent.events import AgentEventSink
from dojoagents.agent.models import ChatRequest, LLMResult, ToolCall
from dojoagents.agent.providers import StaticLLMProvider
from dojoagents.config.models import (
    AgentConfig,
    SessionRuntimeConfig,
    SessionsConfig,
    StoreProviderConfig,
)
from dojoagents.dojo_extensions.registry import DojoExtensionRegistry
from dojoagents.harnesses.base import HarnessDescriptor
from dojoagents.memory.manager import MemoryManager
from dojoagents.sessions.blobs.file import FileBlobStore
from dojoagents.sessions.models import (
    BeginRunCommand,
    ContextUsageQuery,
    HistoryQuery,
    SessionCreateSpec,
    SessionListQuery,
    SessionPrincipal,
    TurnQuery,
    UsageQuery,
)
from dojoagents.sessions.compat.strands import strands_to_canonical
from dojoagents.sessions.service import SessionService
from dojoagents.sessions.errors import SessionLeaseLostError
from dojoagents.sessions.stores.file import FileSessionStore
from dojoagents.skills.manager import SkillManager
from dojoagents.tools.executor import ToolExecutor
from dojoagents.tools.registry import ToolRegistry, ToolSpec
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
        config=AgentConfig(
            model="test-model",
            enable_guardrails=False,
            enable_context_compression=False,
        ),
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

    response = await loop.run(
        ChatRequest(
            "hi",
            session_id="s1",
            principal=principal,
            runtime_content=[{"type": "text", "text": "transient runtime content"}],
        )
    )

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
    assert history.items[0].content == [{"type": "text", "text": "hi"}]
    assert "transient runtime content" not in repr(turns.items)
    assert "transient runtime content" not in repr(history.items)
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
async def test_canonical_history_persists_and_replays_complete_tool_transcript(
    tmp_path,
):
    service = await _service(tmp_path)
    principal = SessionPrincipal("alice")
    provider = StaticLLMProvider(
        [
            LLMResult(
                content="",
                tool_calls=[ToolCall(id="call-1", name="quote", arguments={"ticker": "AAPL"})],
            ),
            LLMResult(content="AAPL is 123.4"),
            LLMResult(content="follow-up complete"),
        ]
    )
    loop = _loop(provider, service)

    async def quote(args):
        return {"content": "123.4"}

    loop.tool_executor.registry.register(
        ToolSpec(
            name="quote",
            description="Return a quote.",
            parameters={"type": "object", "properties": {"ticker": {"type": "string"}}},
            handler=quote,
        )
    )

    await loop.run(ChatRequest("price?", session_id="s1", principal=principal))
    history = await service.history(principal, "s1", HistoryQuery())

    assert [message.role for message in history.items] == [
        "user",
        "assistant",
        "user",
        "assistant",
    ]
    assert history.items[1].content[0] == {
        "type": "tool_use",
        "id": "call-1",
        "name": "quote",
        "input": {"ticker": "AAPL"},
    }
    assert history.items[2].content[0]["type"] == "tool_result"
    assert history.items[2].content[0]["tool_use_id"] == "call-1"
    assert history.items[2].content[0]["name"] == "quote"
    assert history.items[2].content[0]["content"] == [{"type": "text", "text": "123.4"}]
    message_paths = sorted((tmp_path / "sessions" / "session_s1" / "agents" / "agent_dojo-agent" / "messages").glob("message_*.json"))
    assert [path.name for path in message_paths] == [
        "message_1.json",
        "message_2.json",
        "message_3.json",
        "message_4.json",
    ]
    state = json.loads((tmp_path / "sessions" / "state.json").read_text(encoding="utf-8"))["data"]
    assert "messages" not in state

    await loop.run(ChatRequest("and now?", session_id="s1", principal=principal))
    replayed = provider.calls[2]["messages"]
    replayed_tool_call = next(message for message in replayed if message.get("role") == "assistant" and message.get("tool_calls"))
    replayed_tool_result = next(message for message in replayed if message.get("role") == "tool")
    assert replayed_tool_call["tool_calls"][0]["id"] == "call-1"
    assert replayed_tool_result == {
        "role": "tool",
        "name": "quote",
        "tool_call_id": "call-1",
        "content": "123.4",
    }
    await service.shutdown()


@pytest.mark.asyncio
async def test_parallel_tools_commit_transcript_once_at_turn_end(tmp_path):
    service = await _service(tmp_path)
    principal = SessionPrincipal("alice")
    provider = StaticLLMProvider(
        [
            LLMResult(
                content="",
                tool_calls=[
                    ToolCall(
                        id=f"call-{index}",
                        name="quote",
                        arguments={"ticker": ticker, "delay": delay},
                    )
                    for index, (ticker, delay) in enumerate(
                        (
                            ("AAPL", 0.04),
                            ("MSFT", 0.01),
                            ("NVDA", 0.03),
                            ("GOOG", 0.02),
                        ),
                        start=1,
                    )
                ],
            ),
            LLMResult(
                content="",
                tool_calls=[
                    ToolCall(
                        id="call-5",
                        name="quote",
                        arguments={"ticker": "AMZN", "delay": 0.0},
                    )
                ],
            ),
            LLMResult(content="batch complete"),
        ]
    )
    loop = _loop(provider, service)

    async def quote(args):
        await asyncio.sleep(args["delay"])
        return {"content": args["ticker"]}

    loop.tool_executor.registry.register(
        ToolSpec(
            name="quote",
            description="Return a quote.",
            parameters={"type": "object"},
            handler=quote,
        )
    )

    original_append = service._store.append_run_messages
    with patch.object(
        service._store,
        "append_run_messages",
        wraps=original_append,
    ) as append_messages:
        response = await loop.run(ChatRequest("prices?", session_id="s-parallel", principal=principal))
    history = await service.history(principal, "s-parallel", HistoryQuery())

    assert response.content == "batch complete"
    assert append_messages.await_count == 1
    assert [message.role for message in history.items] == [
        "user",
        "assistant",
        "user",
        "assistant",
        "user",
        "assistant",
    ]
    assert {block["tool_use_id"] for message in history.items if message.role == "user" for block in message.content if block["type"] == "tool_result"} == {
        "call-1",
        "call-2",
        "call-3",
        "call-4",
        "call-5",
    }
    tools = await service.load_run_tools(
        principal,
        (await service.list_runs(principal, "s-parallel"))[0].run_id,
    )
    assert len(tools) == 5
    assert all(item.state == "succeeded" for item in tools)
    await service.shutdown()


@pytest.mark.asyncio
async def test_cancelled_before_tool_call_skips_durable_tool_finish(tmp_path):
    service = await _service(tmp_path)
    principal = SessionPrincipal("alice")
    provider = StaticLLMProvider(
        [
            LLMResult(
                content="",
                tool_calls=[
                    ToolCall(
                        id="call-blocked",
                        name="execute_code",
                        arguments={"code": "print('blocked')"},
                    )
                ],
            ),
            LLMResult(content="answered from image"),
        ]
    )
    loop = _loop(provider, service)
    sink = AgentEventSink(run_id="run-blocked", session_id="s-blocked")

    response = await loop.run(
        ChatRequest(
            "read image",
            session_id="s-blocked",
            principal=principal,
            runtime_content=[
                {
                    "type": "image_url",
                    "image_url": {"url": "data:image/png;base64,aQ=="},
                }
            ],
        ),
        event_sink=sink,
    )

    assert response.content == "answered from image"
    assert (await service.get_run(principal, "run-blocked")).status == "completed"
    assert await service.load_run_tools(principal, "run-blocked") == ()
    history = await service.history(principal, "s-blocked", HistoryQuery())
    assert any(block.get("type") == "tool_result" for message in history.items for block in (message.content if isinstance(message.content, list) else ()))
    await service.shutdown()


@pytest.mark.asyncio
async def test_durable_history_replaces_empty_request_history(tmp_path):
    service = await _service(tmp_path)
    principal = SessionPrincipal("alice")
    provider = StaticLLMProvider([LLMResult("first reply"), LLMResult("second reply")])
    loop = _loop(provider, service)

    await loop.run(
        ChatRequest(
            "first question",
            session_id="s1",
            principal=principal,
            metadata={"history": [{"role": "assistant", "content": "imported context"}]},
        )
    )
    assert any(message.get("role") == "assistant" and message.get("content") == "imported context" for message in provider.calls[0]["messages"])
    await loop.run(
        ChatRequest(
            "follow-up",
            session_id="s1",
            principal=principal,
            metadata={"history": []},
        )
    )

    assert any(message.get("role") == "assistant" and message.get("content") == "first reply" for message in provider.calls[1]["messages"])
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
async def test_suspended_recoverable_run_replays_from_durable_user_message(tmp_path):
    service = await _service(tmp_path)
    principal = SessionPrincipal("alice")
    session = await service.create_session(
        principal,
        SessionCreateSpec("s-recover", "minimal", "1", 1),
    )
    initial = strands_to_canonical(
        {"role": "user", "content": [{"text": "resume me"}]},
        session_uid=session.session_uid,
        session_id=session.session_id,
        agent_id="dojo-agent",
        sequence=0,
    )
    initial = replace(
        initial,
        message_id="turn-recover:message:0",
        run_id="run-recover",
        turn_id="turn-recover",
        state="pending",
        boundary_kind="user_input",
    )
    await service.begin_run_with_lease(
        principal,
        BeginRunCommand(
            "s-recover",
            "run-recover",
            "test-model",
            "idem-recover",
            "worker-1",
            recoverable=True,
            request={"schema_version": 1, "message": "resume me"},
            deadline_at=datetime.now(UTC) + timedelta(minutes=5),
            initial_messages=(initial,),
        ),
    )
    request = ChatRequest(
        "resume me",
        session_id="s-recover",
        principal=principal,
        metadata={
            "run_id": "run-recover",
            "turn_id": "turn-recover",
            "idempotency_key": "idem-recover",
            "_run_holder_id": "worker-1",
            "_run_control": {},
        },
    )
    provider = BlockingProvider()
    task = asyncio.create_task(_loop(provider, service).run(request))
    await asyncio.wait_for(provider.started.wait(), timeout=2)
    request.metadata["_run_control"]["suspending"] = True
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    recovered = await _loop(
        StaticLLMProvider([LLMResult("recovered")]),
        service,
    ).run(
        ChatRequest(
            "resume me",
            session_id="s-recover",
            principal=principal,
            metadata={
                "run_id": "run-recover",
                "turn_id": "turn-recover",
                "idempotency_key": "idem-recover",
                "_run_holder_id": "worker-2",
                "_dojo_recovering": True,
                "_recovery_original_message": "resume me",
                "_run_control": {},
            },
        )
    )

    assert recovered.content == "recovered"
    history = await service.history(principal, "s-recover", HistoryQuery())
    assert [item.role for item in history.items] == ["user", "assistant"]
    assert history.items[0].content == [{"type": "text", "text": "resume me"}]
    assert history.items[1].content == [{"type": "text", "text": "recovered"}]
    assert (await service.get_run(principal, "run-recover")).status == "completed"
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
