from __future__ import annotations

import json

import pytest
from unittest.mock import AsyncMock, MagicMock

from dojoagents.agent.models import ChatRequest, LLMResult, ToolResult


def _config() -> MagicMock:
    config = MagicMock()
    config.model = "test-model"
    config.max_iterations = 1
    config.enable_guardrails = False
    config.enable_context_compression = False
    config.enable_think_scrubbing = False
    return config


def _loop(stream_event_callback=None, stream_delta_callback=None):
    from dojoagents.agent.loop import AgentLoop
    from dojoagents.plugins import get_plugin_registry

    reg = get_plugin_registry()
    reg._hooks.clear()
    reg._decl_hooks.clear()
    reg._tools.clear()

    llm = AsyncMock()
    llm.chat.return_value = LLMResult(content="plain answer", tool_calls=[])

    executor = MagicMock()
    executor.registry = MagicMock()
    executor.registry.all.return_value = []
    executor.registry.schema_list.return_value = []

    skills = MagicMock()
    skills.prompt_block.return_value = ""

    memory = MagicMock()
    memory.build_system_prompt.return_value = ""
    memory.prefetch_all = AsyncMock(return_value="")
    memory.as_hook_provider = MagicMock(return_value=MagicMock())

    extensions = MagicMock()
    extensions.prompt_context.return_value = ""

    return AgentLoop(
        llm_provider=llm,
        tool_executor=executor,
        skill_manager=skills,
        memory_manager=memory,
        extension_registry=extensions,
        config=_config(),
        stream_delta_callback=stream_delta_callback,
        stream_event_callback=stream_event_callback,
    )


@pytest.mark.asyncio
async def test_text_only_run_emits_structured_lifecycle_events():
    events: list[dict] = []
    deltas: list[str] = []
    loop = _loop(stream_event_callback=events.append, stream_delta_callback=deltas.append)

    response = await loop.run(ChatRequest(message="hello", user_id="u1", session_id="s1"))

    assert response.content == "plain answer"
    assert deltas == ["plain answer"]
    event_types = [event["type"] for event in events]
    assert event_types[0] == "run_started"
    assert "content_delta" in event_types
    assert event_types[-1] == "run_completed"
    assert all(event["run_id"] == response.metadata["run_id"] for event in events)
    assert all(event["session_id"] == "s1" for event in events)


@pytest.mark.asyncio
async def test_bridged_tool_emits_tool_and_valid_graph_events():
    from dojoagents.agent.loop import DojoBridgedTool
    from dojoagents.tools.registry import ToolSpec

    events: list[dict] = []
    graph = {
        "entities": [{"node_id": "ENT_A", "name": "A"}, {"node_id": "ENT_B", "name": "B"}],
        "edges": [{"from": "ENT_A", "to": "ENT_B", "edge_type": "supplies"}],
    }

    executor = MagicMock()
    executor.execute_one = AsyncMock(return_value=ToolResult(
        call_id="call_1",
        name="graph_cli",
        ok=True,
        content="graph ready",
        metadata={
            "graph_visible": True,
            "graph_contract_valid": True,
            "graph": graph,
            "result_stats": {"entities": 2, "edges": 1},
            "tool_meta": {"source": "cli"},
        },
    ))

    spec = ToolSpec(
        name="graph_cli",
        description="Run graph CLI",
        parameters={"type": "object", "properties": {}},
        handler=AsyncMock(),
    )

    tool = DojoBridgedTool(spec, executor, "s1")

    yielded = [
        item async for item in tool.stream(
            {"toolUseId": "call_1", "name": "graph_cli", "input": {"target": "A"}},
            {"run_id": "run_1", "session_id": "s1", "stream_event_callback": events.append},
        )
    ]

    assert yielded
    assert [event["type"] for event in events] == [
        "tool_call_started",
        "tool_call_completed",
        "graph_payload",
    ]
    assert events[1]["payload"]["status"] == "success"
    assert events[2]["payload"]["graph"] == graph
    assert events[2]["payload"]["result_stats"] == {"entities": 2, "edges": 1}


@pytest.mark.asyncio
async def test_invalid_graph_metadata_does_not_emit_graph_payload():
    from dojoagents.agent.loop import DojoBridgedTool
    from dojoagents.tools.registry import ToolSpec

    events: list[dict] = []

    executor = MagicMock()
    executor.execute_one = AsyncMock(return_value=ToolResult(
        call_id="call_1",
        name="graph_cli",
        ok=True,
        content="invalid graph",
        metadata={
            "graph_visible": True,
            "graph_contract_valid": True,
            "graph": {
                "entities": [{"node_id": "ENT_A"}],
                "edges": [{"from": "ENT_A", "to": "MISSING"}],
            },
        },
    ))

    spec = ToolSpec(
        name="graph_cli",
        description="Run graph CLI",
        parameters={"type": "object", "properties": {}},
        handler=AsyncMock(),
    )

    tool = DojoBridgedTool(spec, executor, "s1")
    _ = [
        item async for item in tool.stream(
            {"toolUseId": "call_1", "name": "graph_cli", "input": {}},
            {"run_id": "run_1", "session_id": "s1", "stream_event_callback": events.append},
        )
    ]

    assert [event["type"] for event in events] == ["tool_call_started", "tool_call_completed"]


@pytest.mark.asyncio
async def test_structured_event_callback_failure_does_not_crash_tool_stream():
    from dojoagents.agent.loop import DojoBridgedTool
    from dojoagents.tools.registry import ToolSpec

    def failing_callback(_event: dict) -> None:
        raise RuntimeError("callback failed")

    executor = MagicMock()
    executor.execute_one = AsyncMock(return_value=ToolResult(
        call_id="call_1",
        name="plain_cli",
        ok=True,
        content="done",
    ))

    spec = ToolSpec(
        name="plain_cli",
        description="Run CLI",
        parameters={"type": "object", "properties": {}},
        handler=AsyncMock(),
    )

    tool = DojoBridgedTool(spec, executor, "s1")

    yielded = [
        item async for item in tool.stream(
            {"toolUseId": "call_1", "name": "plain_cli", "input": {}},
            {"run_id": "run_1", "session_id": "s1", "stream_event_callback": failing_callback},
        )
    ]

    assert yielded


@pytest.mark.asyncio
async def test_dashboard_sse_wraps_structured_events_as_dojo_event_delta():
    import asyncio

    from dojoagents.dashboard.sse import stream_completion_chunks

    queue: asyncio.Queue = asyncio.Queue()
    await queue.put({
        "type": "graph_payload",
        "run_id": "run_1",
        "session_id": "s1",
        "time": "2026-06-08T00:00:00+00:00",
        "payload": {"graph": {"entities": [], "edges": []}},
    })
    await queue.put(None)

    lines = [line async for line in stream_completion_chunks(queue, model="m")]
    event_line = next(line for line in lines if "dojo_event" in line)
    payload = json.loads(event_line.removeprefix("data: "))

    assert payload["choices"][0]["delta"]["dojo_event"]["type"] == "graph_payload"
