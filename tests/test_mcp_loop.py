"""MCP server lifecycle and portal dispatch tests (S7)."""

from __future__ import annotations

import threading
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import dojoagents.tools.mcp_tool as mcp_tool
from dojoagents.tools.mcp_tool import MCPServerTask, make_mcp_tool_handler, mcp_runtime
from dojoagents.utils.blocking_portal import ThreadedBlockingPortal


def _tool_result(text: str) -> MagicMock:
    content = MagicMock()
    content.text = text
    result = MagicMock()
    result.isError = False
    result.content = [content]
    return result


def test_mcp_runtime_start_and_shutdown_are_idempotent() -> None:
    runtime = mcp_tool.MCPToolRuntime(name="test-mcp-runtime")

    runtime.portal.start()
    first_ident = runtime.portal.loop_thread_ident
    runtime.portal.start()
    assert runtime.portal.running
    assert runtime.portal.loop_thread_ident == first_ident

    runtime.shutdown()
    runtime.shutdown()
    assert not runtime.portal.running
    assert runtime.portal.state == "closed"
    assert [t for t in threading.enumerate() if t.ident == first_ident] == []


def test_mcp_runtime_module_accessor_returns_one_shared_runtime() -> None:
    assert mcp_runtime() is mcp_runtime()


@pytest.mark.asyncio
async def test_mcp_server_task_connect():
    config = {"command": "echo", "args": []}
    task = MCPServerTask("test_server", config)

    mock_session = AsyncMock()
    mock_session.initialize = AsyncMock()
    mock_session.list_tools = AsyncMock(return_value=MagicMock(tools=[]))
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock()

    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=("read_stream", "write_stream"))
    mock_client.__aexit__ = AsyncMock()

    with patch("dojoagents.tools.mcp_tool.stdio_client", return_value=mock_client), \
         patch("dojoagents.tools.mcp_tool.ClientSession", return_value=mock_session):
        await task.connect()
        assert task.session == mock_session


@pytest.mark.asyncio
async def test_mcp_tool_handler_dispatches_through_the_owning_portal():
    portal = ThreadedBlockingPortal(name="test-mcp-bridge")
    portal.start()
    try:
        task = MCPServerTask("portal_server", {})
        task.portal = portal

        observed: dict[str, object] = {}

        async def call_tool(name, *, arguments):
            observed["thread"] = threading.get_ident()
            observed["name"] = name
            observed["arguments"] = arguments
            return _tool_result("portal output")

        task.session = MagicMock()
        task.session.call_tool = call_tool

        handler = make_mcp_tool_handler(task, "hello")
        result = await handler({"message": "test"})

        assert result["content"] == "portal output"
        assert result["metadata"] == {"server": "portal_server", "mcp_tool": "hello"}
        assert observed["thread"] == portal.loop_thread_ident
        assert observed["name"] == "hello"
        assert observed["arguments"] == {"message": "test"}
    finally:
        portal.shutdown()


@pytest.mark.asyncio
async def test_mcp_tool_handler_without_an_owning_portal_runs_inline():
    task = MCPServerTask("my_server", {})
    mock_session = AsyncMock()
    mock_session.call_tool = AsyncMock(return_value=_tool_result("output content"))
    task.session = mock_session

    handler = make_mcp_tool_handler(task, "hello")
    result = await handler({"message": "test"})

    assert result["content"] == "output content"
    assert result["metadata"]["server"] == "my_server"
    mock_session.call_tool.assert_awaited_once_with("hello", arguments={"message": "test"})


@pytest.mark.asyncio
async def test_mcp_tool_handler_reports_a_shut_down_component():
    portal = ThreadedBlockingPortal(name="test-mcp-closed")
    portal.start()
    task = MCPServerTask("closed_server", {})
    task.portal = portal
    task.session = AsyncMock()
    portal.shutdown()

    handler = make_mcp_tool_handler(task, "hello")
    with pytest.raises(Exception, match="no longer accepts calls"):
        await handler({})
