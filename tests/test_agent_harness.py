from __future__ import annotations

import pytest

from dojoagents.agent.events import AgentEventSink
from dojoagents.agent.models import ChatRequest, LLMResult, ToolCall, ToolResult
from dojoagents.agent.providers import StaticLLMProvider
from dojoagents.config.models import AgentConfig
from dojoagents.dojo_extensions.registry import DojoExtensionRegistry
from dojoagents.memory.manager import MemoryManager
from dojoagents.skills.manager import SkillManager
from dojoagents.tools.executor import ToolExecutor
from dojoagents.tools.registry import ToolRegistry, ToolSpec
from dojoagents.tools.sandbox import SandboxPolicy


def _make_loop(*, llm, registry, harnesses):
    from dojoagents.agent.loop import AgentLoop

    return AgentLoop(
        llm_provider=llm,
        tool_executor=ToolExecutor(registry, SandboxPolicy(timeout_seconds=2)),
        skill_manager=SkillManager([]),
        memory_manager=MemoryManager(),
        extension_registry=DojoExtensionRegistry(),
        config=AgentConfig(
            model="test-model",
            enable_think_scrubbing=False,
            enable_guardrails=False,
            enable_context_compression=False,
            max_iterations=6,
        ),
        task_harnesses=harnesses,
    )


def _make_request(message: str) -> ChatRequest:
    return ChatRequest(
        user_id="local",
        session_id="sess-harness",
        channel="dashboard",
        message=message,
    )


def test_portfolio_harness_repairs_missing_portfolio_id():
    from dojoagents.agent.harness import HarnessLoopState
    from dojoagents.agent.harnesses.portfolio import PortfolioTaskHarness

    harness = PortfolioTaskHarness()
    request = _make_request("Create a portfolio and add holdings.")
    state = HarnessLoopState(request=request)
    state.tool_results.append(
        ToolResult(
            call_id="call-create",
            name="portfolio_write_create",
            ok=True,
            data={"id": "p-123", "name": "Quality"},
            resource_changes=[
                {"resource": "portfolio", "action": "create", "portfolio_id": "p-123"},
            ],
        )
    )

    [repaired] = harness.repair_tool_calls(
        [
            ToolCall(
                id="call-add",
                name="portfolio_write_add_holding",
                arguments={"ticker": "0700", "market": "hk"},
            )
        ],
        state,
    )

    assert repaired.arguments["portfolio_id"] == "p-123"


@pytest.mark.asyncio
async def test_portfolio_harness_emits_eval_hint_and_blocks_incomplete_completion():
    from dojoagents.agent.harnesses.portfolio import PortfolioTaskHarness

    async def create_portfolio(args):
        return {
            "content": "created",
            "data": {"id": "p-1", "name": args["name"]},
            "resource_changes": [
                {"resource": "portfolio", "action": "create", "portfolio_id": "p-1"},
            ],
        }

    registry = ToolRegistry()
    registry.register(
        ToolSpec(
            name="portfolio_write_create",
            description="Create portfolio.",
            parameters={"type": "object", "properties": {"name": {"type": "string"}}},
            handler=create_portfolio,
        )
    )

    llm = StaticLLMProvider(
        [
            LLMResult(
                content="",
                tool_calls=[ToolCall(id="call-create", name="portfolio_write_create", arguments={"name": "Quality"})],
            ),
            LLMResult(content="The portfolio is complete."),
        ]
    )

    loop = _make_loop(llm=llm, registry=registry, harnesses=[PortfolioTaskHarness()])
    sink = AgentEventSink(run_id="run-1", session_id="sess-harness")

    response = await loop.run(_make_request("Create a new portfolio named Quality."), event_sink=sink)

    assert response.metadata["stopped"] == "harness_incomplete"
    assert any(event["type"] == "eval_hint" for event in sink.events)
    assert "verification" in response.content.lower() or "verify" in response.content.lower()


@pytest.mark.asyncio
async def test_portfolio_harness_allows_completion_after_verification_tool():
    from dojoagents.agent.harnesses.portfolio import PortfolioTaskHarness

    async def create_portfolio(args):
        return {
            "content": "created",
            "data": {"id": "p-1", "name": args["name"]},
            "resource_changes": [
                {"resource": "portfolio", "action": "create", "portfolio_id": "p-1"},
            ],
        }

    async def get_detail(args):
        return {
            "content": "verified",
            "data": {"id": args["portfolio_id"], "holdings": [], "name": "Quality"},
        }

    registry = ToolRegistry()
    registry.register(
        ToolSpec(
            name="portfolio_write_create",
            description="Create portfolio.",
            parameters={"type": "object", "properties": {"name": {"type": "string"}}},
            handler=create_portfolio,
        )
    )
    registry.register(
        ToolSpec(
            name="portfolio_read_detail",
            description="Verify portfolio detail.",
            parameters={"type": "object", "properties": {"portfolio_id": {"type": "string"}}},
            handler=get_detail,
        )
    )

    llm = StaticLLMProvider(
        [
            LLMResult(
                content="",
                tool_calls=[ToolCall(id="call-create", name="portfolio_write_create", arguments={"name": "Quality"})],
            ),
            LLMResult(
                content="",
                tool_calls=[ToolCall(id="call-detail", name="portfolio_read_detail", arguments={})],
            ),
            LLMResult(content="Verified and ready."),
        ]
    )

    loop = _make_loop(llm=llm, registry=registry, harnesses=[PortfolioTaskHarness()])
    response = await loop.run(_make_request("Create a new portfolio named Quality and verify it."))

    assert response.metadata.get("stopped") is None
    assert response.content == "Verified and ready."
