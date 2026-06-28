import pytest
from unittest.mock import AsyncMock, MagicMock
from dojoagents.agent.loop import AgentLoop
from dojoagents.agent.models import ChatRequest, LLMResult, ToolResult, ToolCall
from dojoagents.plugins import get_plugin_registry


@pytest.fixture(autouse=True)
def _reset_plugin_registry_state() -> None:
    reg = get_plugin_registry()
    reg._hooks.clear()
    reg._decl_hooks.clear()
    reg._tools.clear()
    yield
    reg._hooks.clear()
    reg._decl_hooks.clear()
    reg._tools.clear()


@pytest.mark.asyncio
async def test_agent_loop_hooks_integration():
    reg = get_plugin_registry()

    # Mock LLM provider and other loop deps
    llm = AsyncMock()
    llm.chat.return_value = LLMResult(content="Final response from mock LLM", tool_calls=[])

    executor = MagicMock()
    executor.registry.schema_list.return_value = []

    skills = MagicMock()
    skills.prompt_block.return_value = ""
    memory = MagicMock()
    memory.build_system_prompt.return_value = ""
    memory.prefetch_all = AsyncMock(return_value="")
    memory.sync_turn = AsyncMock(return_value=None)
    extensions = MagicMock()
    extensions.prompt_context.return_value = ""
    config = MagicMock()
    config.max_iterations = 1
    config.enable_guardrails = False
    config.enable_context_compression = False
    config.enable_think_scrubbing = False

    # Register test hooks
    on_start_called = False

    def on_start(session_id, model):
        nonlocal on_start_called
        on_start_called = True

    reg._hooks["on_session_start"] = [on_start]
    reg._hooks["pre_llm_call"] = [lambda session_id, user_message: "injected context"]
    reg._hooks["transform_llm_output"] = [lambda response_text, session_id: response_text + " [appended]"]

    loop = AgentLoop(llm_provider=llm, tool_executor=executor, skill_manager=skills, memory_manager=memory, extension_registry=extensions, config=config)

    req = ChatRequest(message="hello", user_id="user_1", session_id="sess_1", channel="test")
    resp = await loop.run(req)

    assert on_start_called is True
    assert resp.content == "Final response from mock LLM [appended]"

    # Verify pre_llm_call injection in messages passed to llm
    called_msgs = llm.chat.call_args[0][0]
    assert "injected context" in called_msgs[-1]["content"]


@pytest.mark.asyncio
async def test_agent_loop_tool_hooks_integration():
    reg = get_plugin_registry()
    reg._hooks.clear()
    reg._tools.clear()

    # First turn generates a tool call; second turn generates final response
    llm = AsyncMock()
    llm.chat.side_effect = [
        LLMResult(content="I will call example_tool", tool_calls=[ToolCall(id="call_1", name="example_tool", arguments={"param": "hello"})]),
        LLMResult(content="Done processing tool results", tool_calls=[]),
    ]

    # Mock tool executor
    executor = AsyncMock()
    # execute_many returns ToolResult
    executor.execute_many.return_value = [ToolResult(call_id="call_1", name="example_tool", ok=True, content="Original result")]
    executor.registry = MagicMock()
    executor.registry.schema_list.return_value = []

    skills = MagicMock()
    skills.prompt_block.return_value = ""
    memory = MagicMock()
    memory.build_system_prompt.return_value = ""
    memory.prefetch_all = AsyncMock(return_value="")
    memory.sync_turn = AsyncMock(return_value=None)
    extensions = MagicMock()
    extensions.prompt_context.return_value = ""

    config = MagicMock()
    config.max_iterations = 2
    config.enable_guardrails = False
    config.enable_context_compression = False
    config.enable_think_scrubbing = False

    # Track hook calls
    pre_tool_called = False
    post_tool_called = False
    transform_tool_called = False
    post_llm_called = False
    on_end_called = False
    on_end_completed = None

    def on_pre_tool(tool_name, args, session_id, tool_call_id):
        nonlocal pre_tool_called
        pre_tool_called = True
        return None

    def on_post_tool(tool_name, args, result, task_id, session_id, tool_call_id, duration_ms):
        nonlocal post_tool_called
        post_tool_called = True
        assert tool_name == "example_tool"
        assert args == {"param": "hello"}
        assert result == "Original result"
        assert isinstance(duration_ms, int)

    def on_transform_tool(tool_name, args, result, task_id, session_id, tool_call_id, duration_ms):
        nonlocal transform_tool_called
        transform_tool_called = True
        return "Modified result"

    def on_post_llm(session_id, user_message, assistant_response, conversation_history, model, platform):
        nonlocal post_llm_called
        post_llm_called = True
        assert assistant_response == "Done processing tool results"

    def on_end(session_id, completed):
        nonlocal on_end_called
        nonlocal on_end_completed
        on_end_called = True
        on_end_completed = completed

    reg._hooks["pre_tool_call"] = [on_pre_tool]
    reg._hooks["post_tool_call"] = [on_post_tool]
    reg._hooks["transform_tool_result"] = [on_transform_tool]
    reg._hooks["post_llm_call"] = [on_post_llm]
    reg._hooks["on_session_end"] = [on_end]

    loop = AgentLoop(llm_provider=llm, tool_executor=executor, skill_manager=skills, memory_manager=memory, extension_registry=extensions, config=config)

    req = ChatRequest(message="run tool", user_id="user_1", session_id="sess_1", channel="test")
    await loop.run(req)

    assert pre_tool_called is True
    assert post_tool_called is True
    assert transform_tool_called is True
    assert post_llm_called is True
    assert on_end_called is True
    assert on_end_completed is True

    # Check that tool executor received the tool call
    executor.execute_many.assert_called_once()
    # Check that the modified result was appended to the messages sent to the second LLM chat call
    called_msgs = llm.chat.call_args_list[1][0][0]
    # The message list contains the assistant message + tool message
    # Let's find the tool message and check its content
    tool_msg = next(m for m in called_msgs if m.get("role") == "tool")
    assert tool_msg["content"] == "Modified result"


@pytest.mark.asyncio
async def test_agent_loop_tool_blocking_integration():
    reg = get_plugin_registry()
    reg._hooks.clear()
    reg._tools.clear()

    # First turn generates a tool call
    llm = AsyncMock()
    llm.chat.return_value = LLMResult(content="I will call example_tool", tool_calls=[ToolCall(id="call_1", name="example_tool", arguments={"param": "hello"})])

    # Mock tool executor: execute_many should NOT be called
    executor = AsyncMock()
    executor.registry = MagicMock()
    executor.registry.schema_list.return_value = []

    skills = MagicMock()
    skills.prompt_block.return_value = ""
    memory = MagicMock()
    memory.build_system_prompt.return_value = ""
    memory.prefetch_all = AsyncMock(return_value="")
    memory.sync_turn = AsyncMock(return_value=None)
    extensions = MagicMock()
    extensions.prompt_context.return_value = ""

    config = MagicMock()
    config.max_iterations = 2
    config.enable_guardrails = False
    config.enable_context_compression = False
    config.enable_think_scrubbing = False

    # pre_tool_call hook blocks
    def on_pre_tool_block(tool_name, args, session_id, tool_call_id):
        return {"action": "block", "message": "Access denied by plugin"}

    reg._hooks["pre_tool_call"] = [on_pre_tool_block]

    loop = AgentLoop(llm_provider=llm, tool_executor=executor, skill_manager=skills, memory_manager=memory, extension_registry=extensions, config=config)

    req = ChatRequest(message="run tool", user_id="user_1", session_id="sess_1", channel="test")
    resp = await loop.run(req)

    # Tool executor should NOT have been called
    executor.execute_many.assert_not_called()

    # It should abort and return the block message
    assert resp.content == "Access denied by plugin"


@pytest.mark.asyncio
async def test_agent_loop_declarative_plugin_interception():
    reg = get_plugin_registry()
    reg._hooks.clear()
    reg._tools.clear()
    reg._decl_hooks.clear()

    # Register mock declarative hook command for pre_tool_call
    reg._decl_hooks["pre_tool_call"] = [
        {
            "plugin_name": "mock_guardian",
            "plugin_path": ".",
            "command": 'echo \'{"action": "block", "message": "Access denied by guardian script"}\'',
            "matcher": None,
            "async": False,
        }
    ]

    llm = AsyncMock()
    llm.chat.return_value = LLMResult(content="calling tool", tool_calls=[ToolCall(id="call_1", name="some_tool", arguments={})])

    executor = AsyncMock()
    executor.registry = MagicMock()
    executor.registry.schema_list.return_value = []

    skills = MagicMock()
    skills.prompt_block.return_value = ""
    memory = MagicMock()
    memory.build_system_prompt.return_value = ""
    memory.prefetch_all = AsyncMock(return_value="")
    memory.sync_turn = AsyncMock(return_value=None)
    extensions = MagicMock()
    extensions.prompt_context.return_value = ""

    config = MagicMock()
    config.max_iterations = 2
    config.enable_guardrails = False
    config.enable_context_compression = False
    config.enable_think_scrubbing = False

    loop = AgentLoop(llm_provider=llm, tool_executor=executor, skill_manager=skills, memory_manager=memory, extension_registry=extensions, config=config)

    req = ChatRequest(message="run", user_id="user_1", session_id="sess_1", channel="test")
    resp = await loop.run(req)

    assert resp.content == "Access denied by guardian script"
    executor.execute_many.assert_not_called()
