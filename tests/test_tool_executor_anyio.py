from __future__ import annotations

import anyio
import pytest

from dojoagents.agent.models import ToolCall
from dojoagents.tools.executor import ToolExecutor
from dojoagents.tools.registry import ToolRegistry, ToolSpec
from dojoagents.tools.sandbox import SandboxPolicy


def _executor(handler, *, timeout: float = 1.0, policy: SandboxPolicy | None = None) -> ToolExecutor:
    registry = ToolRegistry()
    registry.register(
        ToolSpec(
            name="test.tool",
            description="test",
            parameters={"type": "object", "properties": {}},
            handler=handler,
        )
    )
    return ToolExecutor(registry, policy or SandboxPolicy(timeout_seconds=timeout))


@pytest.mark.asyncio
async def test_tool_executor_preserves_success_and_error_shapes() -> None:
    async def success(_arguments: dict) -> dict:
        return {"content": "ok"}

    async def failure(_arguments: dict) -> dict:
        raise ValueError("broken")

    call = ToolCall(id="call-1", name="test.tool", arguments={})
    succeeded = await _executor(success).execute_one(call)
    failed = await _executor(failure).execute_one(call)

    assert succeeded.ok is True
    assert succeeded.content == "ok"
    assert failed.ok is False
    assert failed.error == "broken"


@pytest.mark.asyncio
async def test_tool_timeout_cancels_and_finishes_handler() -> None:
    finalized = anyio.Event()

    async def handler(_arguments: dict) -> dict:
        try:
            await anyio.sleep_forever()
        finally:
            finalized.set()

    result = await _executor(handler, timeout=0.01).execute_one(
        ToolCall(id="call-timeout", name="test.tool", arguments={})
    )

    assert result.ok is False
    assert "timed out after" in result.error
    assert finalized.is_set()


@pytest.mark.asyncio
async def test_external_cancellation_propagates_and_stops_handler() -> None:
    started = anyio.Event()
    finalized = anyio.Event()
    returned = False

    async def handler(_arguments: dict) -> dict:
        try:
            started.set()
            await anyio.sleep_forever()
        finally:
            finalized.set()

    async def invoke() -> None:
        nonlocal returned
        await _executor(handler).execute_one(ToolCall(id="call-cancel", name="test.tool", arguments={}))
        returned = True

    async with anyio.create_task_group() as task_group:
        task_group.start_soon(invoke)
        await started.wait()
        task_group.cancel_scope.cancel()

    assert finalized.is_set()
    assert returned is False


@pytest.mark.asyncio
async def test_grouped_tool_error_is_structured_without_exception_group_leak() -> None:
    async def handler(_arguments: dict) -> dict:
        raise ExceptionGroup("tool failures", [ValueError("first"), RuntimeError("second")])

    result = await _executor(handler).execute_one(
        ToolCall(id="call-group", name="test.tool", arguments={})
    )

    assert result.ok is False
    assert "tool failures" in result.error


@pytest.mark.asyncio
async def test_execute_many_keeps_other_results_when_one_tool_fails() -> None:
    async def handler(arguments: dict) -> dict:
        if arguments.get("fail"):
            raise ValueError("one failed")
        return {"content": str(arguments["value"])}

    executor = _executor(handler)
    results = await executor.execute_many(
        [
            ToolCall(id="one", name="test.tool", arguments={"value": 1}),
            ToolCall(id="bad", name="test.tool", arguments={"fail": True}),
            ToolCall(id="three", name="test.tool", arguments={"value": 3}),
        ]
    )

    assert [result.ok for result in results] == [True, False, True]
    assert [result.content for result in (results[0], results[2])] == ["1", "3"]


@pytest.mark.asyncio
async def test_sandbox_check_still_runs_before_handler() -> None:
    handler_called = False

    async def handler(_arguments: dict) -> dict:
        nonlocal handler_called
        handler_called = True
        return {"content": "unexpected"}

    class DenyingPolicy:
        timeout_seconds = 1.0

        def check_tool(self, _tool_name: str) -> None:
            raise PermissionError("denied")

    result = await _executor(handler, policy=DenyingPolicy()).execute_one(
        ToolCall(id="call-denied", name="test.tool", arguments={})
    )

    assert result.ok is False
    assert result.error == "denied"
    assert handler_called is False
