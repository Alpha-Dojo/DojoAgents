from __future__ import annotations

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock
from dojoagents.tools.mcp_tool import _run_on_mcp_loop, make_mcp_tool_handler, MCPServerTask

@pytest.mark.asyncio
async def test_run_on_mcp_loop():
    async def sample_coro():
        await asyncio.sleep(0.01)
        return "success"
    res = await _run_on_mcp_loop(sample_coro())
    assert res == "success"

@pytest.mark.asyncio
async def test_make_mcp_tool_handler_success():
    task = MCPServerTask("my_server", {})
    mock_session = AsyncMock()
    
    # Mock the CallToolResult from MCP session
    mock_content = MagicMock()
    mock_content.text = "output content"
    mock_result = MagicMock()
    mock_result.isError = False
    mock_result.content = [mock_content]
    
    mock_session.call_tool = AsyncMock(return_value=mock_result)
    task.session = mock_session
    
    handler = make_mcp_tool_handler(task, "hello")
    res = await handler({"message": "test"})
    assert res["content"] == "output content"
    assert res["metadata"]["server"] == "my_server"
