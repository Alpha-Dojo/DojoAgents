import pytest
from dojoagents.tools.registry import ToolRegistry
from dojoagents.tools.executor import ToolExecutor
from dojoagents.tools.sandbox import SandboxPolicy
from dojoagents.agent.models import ToolCall
from dojoagents.tools.terminal_tool import get_terminal_spec

@pytest.mark.asyncio
async def test_integrated_terminal_tool_call():
    registry = ToolRegistry()
    spec = get_terminal_spec(SandboxPolicy())
    registry.register(spec)
    
    executor = ToolExecutor(registry, SandboxPolicy())
    tool_call = ToolCall(id="tc-1", name="terminal", arguments={"command": "echo 'dojo terminal test'"})
    
    result = await executor.execute_one(tool_call)
    assert result.ok
    assert "dojo terminal test" in result.content

@pytest.mark.asyncio
async def test_terminal_tool_sanitization_and_truncation():
    registry = ToolRegistry()
    spec = get_terminal_spec(SandboxPolicy())
    registry.register(spec)
    
    executor = ToolExecutor(registry, SandboxPolicy())
    
    # 验证含有 ANSI 控制符的彩色大输出被过滤并截断
    command = "echo '\x1b[31mred\x1b[0m text' && python3 -c 'print(\"x\" * 40000)'"
    tool_call = ToolCall(id="tc-2", name="terminal", arguments={"command": command})
    
    result = await executor.execute_one(tool_call)
    assert result.ok
    # 验证 ANSI 颜色代码已被剔除
    assert "\x1b[31m" not in result.content
    assert "red text" in result.content
    # 验证输出已经被截断
    assert "OUTPUT TRUNCATED" in result.content
    assert len(result.content) < 40000
