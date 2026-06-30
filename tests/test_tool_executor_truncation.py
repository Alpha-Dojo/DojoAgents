import pytest

from dojoagents.agent.models import ToolCall
from dojoagents.tools.executor import ToolExecutor
from dojoagents.tools.registry import ToolRegistry, ToolSpec
from dojoagents.tools.sandbox import SandboxPolicy


@pytest.mark.asyncio
async def test_tool_executor_truncates_large_tool_content():
    registry = ToolRegistry()

    async def _big_handler(_args: dict) -> dict:
        return {"content": "z" * 50000}

    registry.register(
        ToolSpec(
            name="big.tool",
            description="returns huge payload",
            parameters={"type": "object", "properties": {}},
            handler=_big_handler,
        )
    )

    executor = ToolExecutor(registry, SandboxPolicy())
    result = await executor.execute_one(ToolCall(id="tc-1", name="big.tool", arguments={}))

    assert result.ok
    assert result.truncated is True
    assert len(result.content) < 50000
    assert "OUTPUT TRUNCATED" in result.content
