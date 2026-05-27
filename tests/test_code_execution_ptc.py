import pytest
import tempfile
import os
from dojoagents.tools.registry import ToolRegistry
from dojoagents.tools.executor import ToolExecutor
from dojoagents.tools.sandbox import SandboxPolicy
from dojoagents.agent.models import ToolCall
from dojoagents.tools.code_execution_tool import get_code_execution_spec
from dojoagents.tools.terminal_tool import get_terminal_spec

@pytest.mark.asyncio
async def test_code_execution_calls_terminal_via_rpc():
    registry = ToolRegistry()
    policy = SandboxPolicy()
    registry.register(get_terminal_spec(policy))
    
    # 注册 execute_code 核心工具
    spec = get_code_execution_spec(registry, policy)
    registry.register(spec)
    
    executor = ToolExecutor(registry, policy)
    
    # 编写一个 Python 脚本，通过 rpc 调用 terminal 执行 echo 
    code = (
        "import hermes_tools\n"
        "res = hermes_tools.terminal('echo rpc-ok')\n"
        "print('ScriptOut:', res.get('content', '').strip())\n"
    )
    
    tool_call = ToolCall(id="tc-code", name="execute_code", arguments={"code": code})
    result = await executor.execute_one(tool_call)
    assert result.ok
    assert "ScriptOut: rpc-ok" in result.content

@pytest.mark.asyncio
async def test_code_execution_limit_reached():
    from dojoagents.tools.code_execution_tool import handle_code_execution
    registry = ToolRegistry()
    policy = SandboxPolicy()
    registry.register(get_terminal_spec(policy))
    
    # 限制 max_tool_calls 为 1
    code = (
        "import hermes_tools\n"
        "res1 = hermes_tools.terminal('echo ok-1')\n"
        "res2 = hermes_tools.terminal('echo ok-2')\n"
        "print('R1:', res1.get('ok'))\n"
        "print('R2:', res2.get('ok'))\n"
        "print('Err:', res2.get('error'))\n"
    )
    
    res = await handle_code_execution({"code": code}, registry, policy, max_tool_calls=1)
    output = res["content"]
    assert "R1: True" in output
    assert "R2: False" in output
    assert "Tool call limit reached" in output
