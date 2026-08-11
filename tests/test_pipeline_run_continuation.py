"""Regression: pipeline step 2 must not reuse a completed durable run_id or emit early done."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from unittest.mock import MagicMock

import pytest

from dojoagents.agent.events import AgentEventSink
from dojoagents.agent.models import AgentResponse, ChatRequest
from dojoagents.agent.session_run import CanonicalAgentRun, _durable_run_id
from dojoagents.config.models import SessionRuntimeConfig, SessionsConfig
from dojoagents.harnesses.base import HarnessDescriptor
from dojoagents.sessions.blobs.file import FileBlobStore
from dojoagents.sessions.models import SessionPrincipal
from dojoagents.sessions.service import SessionService
from dojoagents.sessions.stores.file import FileSessionStore
from dojoagents.tasks.runtime_helpers import run_agent_with_tasks


def test_durable_run_id_suffixes_pipeline_steps() -> None:
    sink = AgentEventSink(run_id="run-outer", session_id="s1")
    assert _durable_run_id(event_sink=sink, metadata={}) == "run-outer"
    assert _durable_run_id(event_sink=sink, metadata={"pipeline": {"id": "p", "step": 1}}) == "run-outer"
    assert _durable_run_id(event_sink=sink, metadata={"pipeline": {"id": "p", "step": 2}}) == "run-outer:step:2"


@pytest.mark.asyncio
async def test_canonical_run_allows_pipeline_step_two_after_commit(tmp_path) -> None:
    service = SessionService(
        store=FileSessionStore(tmp_path / "sessions", cursor_secret=b"secret"),
        blob_store=FileBlobStore(tmp_path / "blobs"),
        config=SessionsConfig(runtime=SessionRuntimeConfig(lease_seconds=90)),
    )
    await service.startup()
    principal = SessionPrincipal("alice")
    sink = AgentEventSink(run_id="run-shared", session_id="sess-pipe")
    descriptor = HarnessDescriptor("financial", "1.0.0", "Financial")

    step1 = ChatRequest(
        message="step 1",
        principal=principal,
        session_id="sess-pipe",
        channel="dashboard",
        metadata={"pipeline": {"id": "daily-market-events", "step": 1}},
    )
    run1 = await CanonicalAgentRun.begin(
        service,
        step1,
        descriptor,
        model="test",
        agent_id="dojo-agent",
        event_sink=sink,
    )
    assert run1.coordinator.run_id == "run-shared"
    await run1.commit(AgentResponse(content="done-1", session_id="sess-pipe"))
    assert (await service.get_run(principal, "run-shared")).status == "completed"

    step2 = ChatRequest(
        message="Continue pipeline daily-market-events step 2: event-trigger",
        principal=principal,
        session_id="sess-pipe",
        channel="dashboard",
        metadata={"pipeline": {"id": "daily-market-events", "step": 2}},
    )
    run2 = await CanonicalAgentRun.begin(
        service,
        step2,
        descriptor,
        model="test",
        agent_id="dojo-agent",
        event_sink=sink,
    )
    assert run2.coordinator.run_id == "run-shared:step:2"
    await run2.commit(AgentResponse(content="done-2", session_id="sess-pipe"))
    assert (await service.get_run(principal, "run-shared:step:2")).status == "completed"


@dataclass
class _FakeAdvance:
    next_request: ChatRequest | None = None
    validation_errors: list[str] = field(default_factory=list)
    completed: bool = False


@pytest.mark.asyncio
async def test_run_agent_with_tasks_completes_single_step_pipeline() -> None:
    sink = AgentEventSink(run_id="run-outer", session_id="s1")
    calls: list[str] = []

    step1 = ChatRequest(
        message="/pipeline daily-market-events 2026-07-27",
        user_id="u1",
        session_id="s1",
        channel="dashboard",
        metadata={
            "pipeline": {"id": "daily-market-events", "step": 1, "params": {"trading_date": "2026-07-27"}},
            "active_task": {"task_id": "event-trigger"},
        },
    )

    class Router:
        def preprocess(self, request: ChatRequest) -> ChatRequest:
            return request

    class PipelineRunner:
        def maybe_advance(self, request: ChatRequest, response: AgentResponse) -> _FakeAdvance:
            return _FakeAdvance(completed=True)

    async def fake_run(request: ChatRequest, *, event_sink: Any = None) -> AgentResponse:
        task_id = request.metadata["active_task"]["task_id"]
        calls.append(task_id)
        assert bool(request.metadata.get("pipeline"))
        if event_sink is not None:
            event_sink.delta(f"content-{task_id}")
        return AgentResponse(content=f"ok-{task_id}", session_id=request.session_id, metadata={"tool_trace": []})

    runtime = MagicMock()
    runtime.command_router = Router()
    runtime.pipeline_runner = PipelineRunner()

    response = await run_agent_with_tasks(runtime, step1, run_agent=fake_run, event_sink=sink)
    assert calls == ["event-trigger"]
    assert response.content == "ok-event-trigger"
    assert response.metadata.get("pipeline_completed") is True
    types = [event["type"] for event in sink.events]
    assert types.count("done") == 1
    assert types[-1] == "done"
    assert "delta" in types
    assert "phase" in types
