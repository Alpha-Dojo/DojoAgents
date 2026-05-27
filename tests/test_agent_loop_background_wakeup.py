import pytest
import asyncio
from dojoagents.agent.loop import AgentLoop
from dojoagents.agent.models import ChatRequest, LLMResult, ToolCall
from dojoagents.agent.providers import StaticLLMProvider
from dojoagents.config.models import AgentConfig
from dojoagents.dojo_extensions.registry import DojoExtensionRegistry
from dojoagents.memory.manager import MemoryManager
from dojoagents.skills.manager import SkillManager
from dojoagents.tools.executor import ToolExecutor
from dojoagents.tools.registry import ToolRegistry
from dojoagents.tools.sandbox import SandboxPolicy
from dojoagents.tools.terminal_tool import get_terminal_spec
from dojoagents.tools.process_registry import process_registry

@pytest.mark.asyncio
async def test_agent_loop_background_wakeup_flow():
    # 1. Setup tool registry with terminal tool
    registry = ToolRegistry()
    policy = SandboxPolicy(allowed_commands=["echo", "sleep"])
    registry.register(get_terminal_spec(policy))
    
    # 2. Setup StaticLLMProvider:
    # Turn 1: Calls terminal in background, then gets confirmation of starting
    # Turn 2: Receives completion notification and answers "Finished"
    llm = StaticLLMProvider(
        [
            LLMResult(
                content="",
                tool_calls=[
                    ToolCall(
                        id="tc-bg",
                        name="terminal",
                        arguments={
                            "command": "echo 'bg-task-finished'",
                            "background": True,
                            "notify_on_complete": True
                        }
                    )
                ]
            ),
            LLMResult(
                content="Job started in background."
            ),
            LLMResult(
                content="Job completed. I see the output: bg-task-finished"
            )
        ]
    )
    
    loop = AgentLoop(
        llm_provider=llm,
        tool_executor=ToolExecutor(registry, policy),
        skill_manager=SkillManager([]),
        memory_manager=MemoryManager(),
        extension_registry=DojoExtensionRegistry(),
        config=AgentConfig(
            model="test-model",
            enable_think_scrubbing=False,
            enable_guardrails=False,
            enable_context_compression=False,
        ),
    )
    
    # Turn 1: Submit request
    session_key = "cli:test_target:user123"
    request = ChatRequest(
        user_id="user123",
        session_id=session_key,
        message="Start a background job."
    )
    
    response = await loop.run(request)
    assert "Job started in background" in response.content
    
    # 3. Wait for the background task to complete and put the event in the queue
    # The command is instant (echo), so it should finish quickly.
    event = None
    for _ in range(20):
        if not process_registry.completion_queue.empty():
            event = process_registry.completion_queue.get_nowait()
            break
        await asyncio.sleep(0.1)
        
    assert event is not None
    assert event["session_key"] == session_key
    assert "bg-task-finished" in event["output"]
    assert event["exit_code"] == 0
    
    # 4. Simulate GatewayRunner/Watcher constructing the synthetic event
    exit_code = event.get("exit_code", 0)
    cmd = event.get("command", "")
    sid = event.get("session_id", "")
    output = event.get("output", "").strip()
    
    synth_text = (
        f"[IMPORTANT: Background process {sid} completed "
        f"(exit code {exit_code}).\n"
        f"Command: {cmd}\n"
        f"Output:\n{output}]"
    )
    
    # Turn 2: Run agent loop again with the synthetic completion message
    request2 = ChatRequest(
        user_id="user123",
        session_id=session_key,
        message=synth_text
    )
    
    response2 = await loop.run(request2)
    assert "Job completed. I see the output: bg-task-finished" in response2.content
