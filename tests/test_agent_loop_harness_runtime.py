import pytest

from dojoagents.agent.events import AgentEventSink
from dojoagents.agent.loop import AgentLoop
from dojoagents.agent.models import ChatRequest, LLMResult, ToolCall
from dojoagents.agent.providers import StaticLLMProvider
from dojoagents.config.models import AgentConfig
from dojoagents.dojo_extensions.registry import DojoExtensionRegistry
from dojoagents.harnesses.decisions import CompletionDecision, ToolControlDecision
from dojoagents.harnesses.registries.prompts import PromptBlock
from dojoagents.memory.manager import MemoryManager
from dojoagents.sessions.models import SessionPrincipal
from dojoagents.skills.manager import SkillManager
from dojoagents.tools.executor import ToolExecutor
from dojoagents.tools.registry import ToolRegistry, ToolSpec
from dojoagents.tools.sandbox import SandboxPolicy


def test_chat_request_supports_principal_context_without_quant_core_dependency():
    principal = SessionPrincipal("alice", "tenant-a")
    request = ChatRequest(
        message="hello",
        session_id="s1",
        principal=principal,
        channel="api",
        context={"financial": {"market": "us"}},
    )
    legacy = ChatRequest(message="legacy", user_id="bob", session_id="s2")

    assert request.principal is principal
    assert request.user_id == "alice"
    assert request.context["financial"]["market"] == "us"
    assert legacy.principal == SessionPrincipal("bob")


class RecordingProvider(StaticLLMProvider):
    def __init__(self, results, events):
        super().__init__(results)
        self.events = events

    async def chat(self, *args, **kwargs):
        self.events.append("model")
        return await super().chat(*args, **kwargs)


class RecordingHarnessRuntime:
    def __init__(self, events):
        self.events = events

    async def before_turn(self, context):
        self.events.extend(("before_turn", "prompt"))
        return (PromptBlock("core.safety", "core", "safe", "core"),)

    async def transform_calls(self, calls, context):
        self.events.extend(("transform", "revalidate"))
        return tuple(calls)

    async def authorize(self, call, context):
        self.events.extend(("core_safety", "authorize"))
        return ToolControlDecision("allow", "allowed")

    async def present_results(self, results, context):
        self.events.extend(("normalize", "present"))
        return tuple(results)

    async def evaluate_completion(self, context):
        self.events.append("completion")
        return CompletionDecision("complete", "complete")

    async def after_turn(self, context):
        self.events.append("after_turn")


class PoisonLegacyHarness:
    def matches(self, request, state):
        raise AssertionError("legacy harness must not run for a HarnessRuntime turn")


class BlockingHarnessRuntime(RecordingHarnessRuntime):
    async def authorize(self, call, context):
        self.events.extend(("core_safety", "authorize"))
        return ToolControlDecision(
            "block",
            "test_policy_block",
            "Blocked by test Harness policy",
        )


@pytest.mark.asyncio
async def test_agent_loop_runs_domain_neutral_harness_pipeline_in_order():
    events = []

    async def echo(arguments):
        events.append("execute")
        return {"content": arguments["text"]}

    tools = ToolRegistry()
    tools.register(
        ToolSpec(
            "echo",
            "echo",
            {"type": "object", "properties": {"text": {"type": "string"}}},
            echo,
        )
    )
    provider = RecordingProvider(
        [
            LLMResult("", [ToolCall("call-1", "echo", {"text": "ok"})]),
            LLMResult("done"),
        ],
        events,
    )
    loop = AgentLoop(
        llm_provider=provider,
        tool_executor=ToolExecutor(tools, SandboxPolicy(timeout_seconds=2)),
        skill_manager=SkillManager([]),
        memory_manager=MemoryManager(),
        extension_registry=DojoExtensionRegistry(),
        config=AgentConfig(model="test-model", enable_guardrails=False, enable_context_compression=False),
        harness_runtime=RecordingHarnessRuntime(events),
        task_harnesses=[PoisonLegacyHarness()],
    )

    response = await loop.run(ChatRequest(message="echo", session_id="s1", principal=SessionPrincipal("alice")))

    assert response.content == "done"
    assert events == [
        "before_turn",
        "prompt",
        "model",
        "transform",
        "revalidate",
        "core_safety",
        "authorize",
        "execute",
        "normalize",
        "present",
        "model",
        "completion",
        "after_turn",
    ]


@pytest.mark.asyncio
async def test_harness_block_emits_matching_terminal_tool_result():
    events = []
    executed = False

    async def echo(arguments):
        nonlocal executed
        executed = True
        return {"content": arguments["text"]}

    tools = ToolRegistry()
    tools.register(
        ToolSpec(
            "echo",
            "echo",
            {"type": "object", "properties": {"text": {"type": "string"}}},
            echo,
        )
    )
    provider = RecordingProvider(
        [
            LLMResult("", [ToolCall("call-blocked", "echo", {"text": "no"})]),
            LLMResult("handled"),
        ],
        events,
    )
    loop = AgentLoop(
        llm_provider=provider,
        tool_executor=ToolExecutor(tools, SandboxPolicy(timeout_seconds=2)),
        skill_manager=SkillManager([]),
        memory_manager=MemoryManager(),
        extension_registry=DojoExtensionRegistry(),
        config=AgentConfig(
            model="test-model",
            enable_guardrails=False,
            enable_context_compression=False,
        ),
        harness_runtime=BlockingHarnessRuntime(events),
    )
    sink = AgentEventSink(run_id="run-blocked", session_id="s1")

    response = await loop.run(
        ChatRequest(
            message="echo",
            session_id="s1",
            principal=SessionPrincipal("alice"),
        ),
        event_sink=sink,
    )

    tool_events = [event for event in sink.events if event["type"] in {"tool_start", "tool_result"}]
    assert response.content == "handled"
    assert executed is False
    assert [event["type"] for event in tool_events] == [
        "tool_start",
        "tool_result",
    ]
    assert tool_events[0]["call_id"] == tool_events[1]["call_id"] == "call-blocked"
    assert tool_events[1]["ok"] is False
    assert tool_events[1]["error"] == "Blocked by test Harness policy"
