from __future__ import annotations

import pytest
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock
from dojoagents.config.loader import ConfigStore
from dojoagents.agent.runtime import Runtime

def test_runtime_registers_mcp_tools():
    content = """
version: 1
mcp_servers:
  test_filesystem:
    command: "mock_cmd"
    args: []
    enabled: true
"""
    # Mock the connection and listing of tools
    mock_tool = MagicMock()
    mock_tool.name = "read_file"
    mock_tool.description = "Read a file"
    mock_tool.inputSchema = {"type": "object", "properties": {}}
    
    mock_task = MagicMock()
    mock_task.tools = [mock_tool]
    mock_task.connect = AsyncMock()
    
    with tempfile.TemporaryDirectory() as tmpdir:
        cfg_file = Path(tmpdir) / "agents.yaml"
        cfg_file.write_text(content, encoding="utf-8")
        store = ConfigStore(path=cfg_file)
        
        with patch("dojoagents.tools.mcp_tool.MCPServerTask", return_value=mock_task):
            runtime = Runtime.from_config_store(store)
            spec = runtime.agent.tool_executor.registry.get("mcp_test_filesystem_read_file")
            assert spec is not None
            assert spec.description == "Read a file"
