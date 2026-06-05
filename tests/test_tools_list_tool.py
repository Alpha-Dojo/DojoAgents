# tests/test_tools_list_tool.py
from __future__ import annotations

import json
import pytest

from dojoagents.agent.runtime import Runtime
from dojoagents.agent.models import ToolCall
from dojoagents.tools.registry import ToolRegistry
from dojoagents.tools.executor import ToolExecutor
from dojoagents.tools.sandbox import SandboxPolicy
from dojoagents.tools.tools_list_tool import ToolsListTool


def test_tools_list_tool_discovery():
    """Verify that the tools_list tool is registered in the runtime."""
    runtime = Runtime.from_default_config()
    all_tools = [spec.name for spec in runtime.agent.tool_executor.registry.all()]
    assert "tools_list" in all_tools


@pytest.mark.asyncio
async def test_tools_list_tool_execution():
    """Verify that executing tools_list returns the registered tools schema list."""
    registry = ToolRegistry()
    tools_list_spec = ToolsListTool(registry).get_tool_spec()
    registry.register(tools_list_spec)

    # Register a mock tool as well
    from dojoagents.tools.registry import ToolSpec
    mock_spec = ToolSpec(
        name="test_mock_tool",
        description="A dummy test tool",
        parameters={"type": "object", "properties": {"dummy": {"type": "string"}}},
        handler=lambda args: {"content": "dummy", "metadata": {}}
    )
    registry.register(mock_spec)

    executor = ToolExecutor(registry, SandboxPolicy())
    
    tool_call = ToolCall(
        id="tc-tools-list",
        name="tools_list",
        arguments={}
    )
    
    result = await executor.execute_one(tool_call)
    
    assert result.ok
    assert "tc-tools-list" == result.call_id
    
    # Verify content parses as JSON list
    data = json.loads(result.content)
    assert isinstance(data, list)
    assert len(data) == 2
    
    # Assert specific schemas are returned
    names = [tool["name"] for tool in data]
    assert "tools_list" in names
    assert "test_mock_tool" in names
    
    # Check schema dictionary fields
    mock_tool_entry = next(t for t in data if t["name"] == "test_mock_tool")
    assert mock_tool_entry["description"] == "A dummy test tool"
    assert "dummy" in mock_tool_entry["parameters"]["properties"]
