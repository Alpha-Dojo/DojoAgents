import asyncio
import time
import pytest
from unittest.mock import MagicMock

from dojoagents.agent.models import ChatRequest, LLMResult
from dojoagents.agent.providers import StaticLLMProvider
from dojoagents.gateway.stream_consumer import GatewayStreamConsumer
from dojoagents.gateway.adapters.base import GatewaySendResult


@pytest.mark.asyncio
async def test_static_llm_provider_streaming_simulation():
    provider = StaticLLMProvider([LLMResult(content="Hello world this is a test response.")])
    
    deltas = []
    def callback(delta: str):
        deltas.append(delta)

    result = await provider.chat(
        messages=[],
        tools=[],
        model="static-model",
        stream=True,
        stream_callback=callback
    )

    assert result.content == "Hello world this is a test response."
    # Since StaticLLMProvider splits content by chunks of 5 characters, we should have multiple deltas
    assert len(deltas) > 1
    assert "".join(deltas) == "Hello world this is a test response."


@pytest.mark.asyncio
async def test_agent_loop_invokes_streaming_callback():
    from dojoagents.agent.loop import AgentLoop
    from dojoagents.config.models import AgentConfig
    from dojoagents.skills.manager import SkillManager
    from dojoagents.memory.manager import MemoryManager
    from dojoagents.tools.executor import ToolExecutor
    from dojoagents.dojo_extensions.registry import DojoExtensionRegistry

    provider = StaticLLMProvider([LLMResult(content="Final Response content")])
    
    tool_executor = MagicMock(spec=ToolExecutor)
    tool_executor.registry = MagicMock()
    tool_executor.registry.schema_list.return_value = []
    
    skill_manager = MagicMock(spec=SkillManager)
    skill_manager.prompt_block.return_value = ""
    memory_manager = MagicMock(spec=MemoryManager)
    memory_manager.build_system_prompt.return_value = ""
    memory_manager.prefetch_all.return_value = ""
    extension_registry = MagicMock(spec=DojoExtensionRegistry)

    config = AgentConfig(model="mock", max_iterations=2)

    deltas = []
    def on_delta(delta: str):
        deltas.append(delta)

    loop = AgentLoop(
        llm_provider=provider,
        tool_executor=tool_executor,
        skill_manager=skill_manager,
        memory_manager=memory_manager,
        extension_registry=extension_registry,
        config=config,
        stream_delta_callback=on_delta
    )

    request = ChatRequest(message="hi", user_id="u1", session_id="s1")
    await loop.run(request)

    assert "".join(deltas) == "Final Response content"


@pytest.mark.asyncio
async def test_gateway_stream_consumer_throttling_and_think_stripping():
    # Mock adapter
    adapter = MagicMock()
    sent_messages = []
    edits = []

    async def mock_send(target, text, *, thread_id=None):
        sent_messages.append(text)
        return GatewaySendResult(success=True, message_id="msg-100")

    async def mock_edit(target, message_id, text, *, thread_id=None):
        edits.append(text)
        return GatewaySendResult(success=True, message_id=message_id)

    adapter.send = mock_send
    adapter.edit = mock_edit

    # Initialize consumer with short edit_interval to keep tests fast
    consumer = GatewayStreamConsumer(
        adapter=adapter,
        target="T1",
        edit_interval=0.05
    )

    await consumer.start()

    # Send chunks, including a thinking block
    consumer.on_delta("Hello! ")
    consumer.on_delta("<think>Thinking step 1...")
    consumer.on_delta("Thinking step 2...</think>")
    consumer.on_delta("Here is the answer.")
    consumer.on_delta("<thought>another thought</thought> Done.")

    # Sleep to allow consumer task to process items
    await asyncio.sleep(0.15)
    await consumer.stop()

    # Verify that the final text sent or edited contains NO thinking blocks
    assert len(sent_messages) == 1
    assert sent_messages[0] == "Hello! "
    
    # Assert that subsequent edits were sent and final text contains no think blocks
    assert len(edits) > 0
    final_text = edits[-1]
    assert "Thinking" not in final_text
    assert "thought" not in final_text
    assert final_text == "Hello! Here is the answer. Done."


@pytest.mark.asyncio
async def test_gateway_runner_streaming_integration(tmp_path):
    from dojoagents.agent.models import AgentResponse
    from dojoagents.gateway.registry import GatewayRegistry, PlatformEntry
    from dojoagents.gateway.runner import GatewayRunner
    from dojoagents.gateway.adapters.base import GatewayEvent, GatewaySendResult

    class StreamingAgent:
        def __init__(self):
            self.stream_delta_callback = None

        async def run(self, request):
            if self.stream_delta_callback:
                self.stream_delta_callback("Streaming ")
                self.stream_delta_callback("<think>internal</think>reply")
            return AgentResponse(content="Streaming reply", session_id=request.session_id)

    class FakeRuntime:
        agent = StreamingAgent()

    class FakeAdapter:
        platform = "test"
        label = "Test"
        def __init__(self, config):
            self.sent = []
            self.edits = []

        async def start(self): pass
        async def stop(self): pass
        def normalize_message(self, payload):
            return GatewayEvent(
                platform="test",
                text=payload["text"],
                target=payload["target"],
                user_id=payload["user_id"],
            )

        async def send(self, target, message, *, thread_id=None):
            self.sent.append(message)
            return GatewaySendResult(success=True, message_id="m-stream")

        async def edit(self, target, message_id, message, *, thread_id=None):
            self.edits.append(message)
            return GatewaySendResult(success=True, message_id=message_id)

    registry = GatewayRegistry()
    registry.register(PlatformEntry("test", "Test", lambda config: FakeAdapter(config)))

    runner = GatewayRunner(
        runtime=FakeRuntime(),
        registry=registry,
        gateway_config={
            "hooks": {"test": {"enabled": True}},
            "session_store": str(tmp_path / "state.db"),
            "pid_file": str(tmp_path / "gateway.pid"),
            "streaming": {"enabled": True, "edit_interval": 0.01}
        }
    )

    await runner.start()
    result = await runner.handle_webhook(
        "test",
        {"text": "hi", "target": "T1", "user_id": "U1"},
    )
    assert result["accepted"] is True

    adapter = runner.adapters["test"]
    assert "Streaming " in adapter.sent
    assert len(adapter.edits) > 0
    assert "internal" not in adapter.edits[-1]
    assert adapter.edits[-1] == "Streaming reply"

    await runner.stop()
