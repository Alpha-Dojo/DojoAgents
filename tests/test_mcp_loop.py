from __future__ import annotations

import asyncio
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
import dojoagents.tools.mcp_tool as mcp_tool
from dojoagents.tools.mcp_tool import MCPServerTask

def test_mcp_loop_starts():
    mcp_tool._ensure_mcp_loop()
    assert mcp_tool._mcp_loop is not None
    assert mcp_tool._mcp_loop.is_running()

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
