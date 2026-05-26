from __future__ import annotations

import pytest
from dojoagents.agent.loop import AgentLoop
from dojoagents.agent.models import ChatRequest, LLMResult, ToolCall
from dojoagents.agent.providers import StaticLLMProvider
from dojoagents.config.models import AgentConfig
from dojoagents.dojo_extensions.registry import DojoExtensionRegistry
from dojoagents.memory.manager import MemoryManager
from dojoagents.skills.manager import SkillManager
from dojoagents.tools.executor import ToolExecutor
from dojoagents.tools.registry import ToolRegistry, ToolSpec
from dojoagents.tools.sandbox import SandboxPolicy


@pytest.mark.asyncio
async def test_integrated_think_scrubbing():
    # Verify that thinking block tags are scrubbed from stream callback and final LLMResult
    # StaticLLMProvider yields content and streams it in chunks
    llm = StaticLLMProvider(
        [
            LLMResult(
                content="<think>internal logic</think>Here is the clean answer."
            )
        ]
    )

    streamed_deltas = []

    def callback(delta: str):
        streamed_deltas.append(delta)

    loop = AgentLoop(
        llm_provider=llm,
        tool_executor=ToolExecutor(
            ToolRegistry(), SandboxPolicy(timeout_seconds=2)
        ),
        skill_manager=SkillManager([]),
        memory_manager=MemoryManager(),
        extension_registry=DojoExtensionRegistry(),
        config=AgentConfig(
            model="test-model",
            enable_think_scrubbing=True,
            enable_guardrails=False,
            enable_context_compression=False,
        ),
        stream_delta_callback=callback,
    )

    response = await loop.run(
        ChatRequest(user_id="local", session_id="s1", message="Run test.")
    )

    # Check that stream callback did not receive the thinking content
    streamed_text = "".join(streamed_deltas)
    assert "internal logic" not in streamed_text
    assert "<think>" not in streamed_text
    assert "Here is the clean answer." in streamed_text

    # Check that response content is also cleaned
    assert "internal logic" not in response.content
    assert "Here is the clean answer." in response.content


@pytest.mark.asyncio
async def test_integrated_loop_guardrails():
    # Verify that a tool loop gets blocked or halted by guardrails inside AgentLoop
    async def failing_tool(args):
        return {"content": "Error: compilation failed"}

    registry = ToolRegistry()
    registry.register(
        ToolSpec(
            name="fail_tool",
            description="Always fail.",
            parameters={"type": "object"},
            handler=failing_tool,
        )
    )

    # LLM keeps calling the failing tool unchanged
    llm = StaticLLMProvider(
        [
            LLMResult(
                content="",
                tool_calls=[
                    ToolCall(id="c1", name="fail_tool", arguments={"v": 1})
                ],
            ),
            LLMResult(
                content="",
                tool_calls=[
                    ToolCall(id="c2", name="fail_tool", arguments={"v": 1})
                ],
            ),
            LLMResult(
                content="",
                tool_calls=[
                    ToolCall(id="c3", name="fail_tool", arguments={"v": 1})
                ],
            ),
            LLMResult(
                content="",
                tool_calls=[
                    ToolCall(id="c4", name="fail_tool", arguments={"v": 1})
                ],
            ),
            LLMResult(
                content="",
                tool_calls=[
                    ToolCall(id="c5", name="fail_tool", arguments={"v": 1})
                ],
            ),
            LLMResult(content="Done"),
        ]
    )

    # Set exact_failure_block_after low to trigger block/halt quickly
    loop = AgentLoop(
        llm_provider=llm,
        tool_executor=ToolExecutor(registry, SandboxPolicy(timeout_seconds=2)),
        skill_manager=SkillManager([]),
        memory_manager=MemoryManager(),
        extension_registry=DojoExtensionRegistry(),
        config=AgentConfig(
            model="test-model",
            enable_think_scrubbing=False,
            enable_guardrails=True,
            enable_context_compression=False,
            max_iterations=8,
        ),
    )

    # Override guardrails limits to block quickly
    loop.guardrails.exact_failure_block_after = 2

    response = await loop.run(
        ChatRequest(user_id="local", session_id="s1", message="Run loop test.")
    )

    # The guardrail should block the call on the 3rd iteration and halt the loop
    assert response.metadata.get("stopped") == "guardrail_halt"
    assert "Blocked fail_tool" in response.content


@pytest.mark.asyncio
async def test_integrated_history_formatting_and_reasoning():
    # Setup StaticLLMProvider that expects messages to contain reasoning_content and correct tool formats
    llm = StaticLLMProvider(
        [
            LLMResult(
                content="Final output",
                metadata={"reasoning_content": "think link"}
            )
        ]
    )

    loop = AgentLoop(
        llm_provider=llm,
        tool_executor=ToolExecutor(
            ToolRegistry(), SandboxPolicy(timeout_seconds=2)
        ),
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

    # We pass history in metadata
    history = [
        {
            "role": "assistant",
            "content": "some explanation",
            "reasoning_content": "thought chain one",
            "tool_calls": [
                {
                    "id": "call_abc",
                    "type": "function",
                    "function": {"name": "some_tool", "arguments": {"x": 100}}
                }
            ]
        },
        {
            "role": "tool",
            "name": "some_tool",
            "tool_call_id": "call_abc",
            "content": "tool result content"
        }
    ]

    response = await loop.run(
        ChatRequest(
            user_id="local",
            session_id="s1",
            message="What now?",
            metadata={"history": history}
        )
    )

    # Inspect the messages sent to the LLM
    assert len(llm.calls) == 1
    sent_messages = llm.calls[0]["messages"]

    # system message, 2 history messages, and 1 user message
    # Let's check history assistant message:
    assistant_msg = sent_messages[1]
    assert assistant_msg["role"] == "assistant"
    assert assistant_msg["content"] == "some explanation"
    assert assistant_msg["reasoning_content"] == "thought chain one"
    assert assistant_msg["tool_calls"][0]["function"]["arguments"] == '{"x": 100}'

    # Let's check history tool message:
    tool_msg = sent_messages[2]
    assert tool_msg["role"] == "tool"
    assert tool_msg["name"] == "some_tool"
    assert tool_msg["tool_call_id"] == "call_abc"
    assert tool_msg["content"] == "tool result content"
