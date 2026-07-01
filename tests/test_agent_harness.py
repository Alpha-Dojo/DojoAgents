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


def _make_request(message: str = "", *, dashboard_tab: str | None = None) -> ChatRequest:
    metadata: dict[str, str] = {}
    if dashboard_tab:
        metadata["dashboard_tab"] = dashboard_tab
    return ChatRequest(
        user_id="local",
        session_id="sess-harness",
        channel="dashboard",
        message=message,
        metadata=metadata,
    )


def test_portfolio_harness_repairs_missing_portfolio_id():
    from dojoagents.agent.harness import HarnessLoopState
    from dojoagents.agent.harnesses.portfolio import PortfolioTaskHarness

    harness = PortfolioTaskHarness()
    request = _make_request(dashboard_tab="folio")
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

    response = await loop.run(_make_request("Create a new portfolio named Quality.", dashboard_tab="folio"), event_sink=sink)

    assert response.metadata["stopped"] == "harness_incomplete"
    assert any(event["type"] == "eval_hint" for event in sink.events)
    assert "verification" in response.content.lower() or "verify" in response.content.lower() or "eval" in response.content.lower()


@pytest.mark.asyncio
async def test_portfolio_harness_allows_completion_after_eval_submit():
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
            "data": {
                "id": args["portfolio_id"],
                "holdings": [],
                "candidates": [],
                "name": "Quality",
                "kind": "agent",
            },
        }

    async def submit_eval(args):
        return {
            "content": "accepted",
            "data": {
                "portfolio_id": args["portfolio_id"],
                "task_summary": "Created portfolio",
                "require_kind_agent": True,
                "accepted": True,
            },
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
    registry.register(
        ToolSpec(
            name="portfolio_eval_submit",
            description="Submit eval.",
            parameters={"type": "object", "properties": {"portfolio_id": {"type": "string"}}},
            handler=submit_eval,
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
                tool_calls=[
                    ToolCall(id="call-detail", name="portfolio_read_detail", arguments={"portfolio_id": "p-1"}),
                ],
            ),
            LLMResult(
                content="",
                tool_calls=[
                    ToolCall(
                        id="call-eval",
                        name="portfolio_eval_submit",
                        arguments={
                            "portfolio_id": "p-1",
                            "task_summary": "Created portfolio",
                            "require_kind_agent": True,
                        },
                    ),
                ],
            ),
            LLMResult(content="Verified and ready."),
        ]
    )

    loop = _make_loop(llm=llm, registry=registry, harnesses=[PortfolioTaskHarness()])
    response = await loop.run(_make_request(dashboard_tab="folio"))

    assert response.metadata.get("stopped") is None
    assert response.content == "Verified and ready."


def test_portfolio_harness_blocks_when_eval_candidate_count_not_met():
    from dojoagents.agent.harness import HarnessLoopState
    from dojoagents.agent.harnesses.portfolio import PortfolioTaskHarness

    harness = PortfolioTaskHarness()
    state = HarnessLoopState(request=_make_request(dashboard_tab="folio"))
    state.tool_results.extend(
        [
            ToolResult(
                call_id="call-add",
                name="portfolio_write_add_holding",
                ok=True,
                data={"id": "p-1"},
            ),
            ToolResult(
                call_id="call-detail",
                name="portfolio_read_detail",
                ok=True,
                data={"id": "p-1", "candidates": [{"ticker": "WFC", "market": "us"}]},
            ),
            ToolResult(
                call_id="call-eval",
                name="portfolio_eval_submit",
                ok=True,
                data={
                    "portfolio_id": "p-1",
                    "task_summary": "Add five US dividend stocks",
                    "min_candidate_count": 5,
                },
            ),
        ]
    )

    decision = harness.validate_progress(state)

    assert decision.complete is False
    assert decision.allow_extra_steps is True
    assert any("5" in issue for issue in decision.issues)


def test_portfolio_harness_blocks_delete_tool_during_build():
    from dojoagents.agent.harness import HarnessLoopState
    from dojoagents.agent.harnesses.portfolio import PortfolioTaskHarness

    harness = PortfolioTaskHarness()
    state = HarnessLoopState(request=_make_request(dashboard_tab="folio"))
    state.tool_results.append(
        ToolResult(
            call_id="call-create",
            name="portfolio_write_create",
            ok=True,
            data={"id": "p-1", "kind": "agent"},
            resource_changes=[{"resource": "portfolio", "action": "create", "portfolio_id": "p-1"}],
        )
    )
    message = harness.block_tool_call(
        ToolCall(id="call-del", name="portfolio_write_delete", arguments={"portfolio_id": "p-1"}),
        state,
    )
    assert message is not None
    assert "delete" in message.lower()


def test_portfolio_harness_rejects_delete_during_create_task():
    from dojoagents.agent.harness import HarnessLoopState
    from dojoagents.agent.harnesses.portfolio import PortfolioTaskHarness

    harness = PortfolioTaskHarness()
    state = HarnessLoopState(request=_make_request(dashboard_tab="folio"))
    state.tool_results.extend(
        [
            ToolResult(
                call_id="call-create",
                name="portfolio_write_create",
                ok=True,
                data={"id": "p-1", "kind": "agent"},
                resource_changes=[{"resource": "portfolio", "action": "create", "portfolio_id": "p-1"}],
            ),
            ToolResult(
                call_id="call-delete",
                name="portfolio_write_delete",
                ok=True,
                data={"portfolio_id": "p-1"},
                resource_changes=[{"resource": "portfolio", "action": "delete", "portfolio_id": "p-1"}],
            ),
            ToolResult(
                call_id="call-detail",
                name="portfolio_read_detail",
                ok=True,
                data={"id": "p-1", "kind": "agent", "candidates": [{"ticker": "WFC", "market": "us"}]},
            ),
            ToolResult(
                call_id="call-eval",
                name="portfolio_eval_submit",
                ok=True,
                data={
                    "portfolio_id": "p-1",
                    "task_summary": "Create portfolio",
                    "require_kind_agent": True,
                },
            ),
        ]
    )

    decision = harness.validate_progress(state)

    assert decision.complete is False
    assert any("delete" in issue.lower() for issue in decision.issues)


def test_portfolio_harness_requires_agent_kind_on_create():
    from dojoagents.agent.harness import HarnessLoopState
    from dojoagents.agent.harnesses.portfolio import PortfolioTaskHarness

    harness = PortfolioTaskHarness()
    state = HarnessLoopState(request=_make_request(dashboard_tab="folio"))
    state.tool_results.extend(
        [
            ToolResult(
                call_id="call-create",
                name="portfolio_write_create",
                ok=True,
                data={"id": "p-1", "kind": "agent"},
                resource_changes=[{"resource": "portfolio", "action": "create", "portfolio_id": "p-1"}],
            ),
            ToolResult(
                call_id="call-detail",
                name="portfolio_read_detail",
                ok=True,
                data={"id": "p-1", "kind": "manual", "candidates": []},
            ),
            ToolResult(
                call_id="call-eval",
                name="portfolio_eval_submit",
                ok=True,
                data={
                    "portfolio_id": "p-1",
                    "task_summary": "Create portfolio",
                    "require_kind_agent": True,
                },
            ),
        ]
    )

    decision = harness.validate_progress(state)

    assert decision.complete is False
    assert any("agent" in issue.lower() for issue in decision.issues)


def test_portfolio_harness_completes_delete_without_read_detail():
    from dojoagents.agent.harness import HarnessLoopState
    from dojoagents.agent.harnesses.portfolio import PortfolioTaskHarness

    harness = PortfolioTaskHarness()
    state = HarnessLoopState(request=_make_request(dashboard_tab="folio"))
    state.tool_results.extend(
        [
            ToolResult(
                call_id="call-list",
                name="portfolio_read_list",
                ok=True,
                data=[{"id": "other", "name": "Other"}],
            ),
            ToolResult(
                call_id="call-delete",
                name="portfolio_write_delete",
                ok=True,
                data={"ok": True, "portfolio_id": "p-del"},
                resource_changes=[{"resource": "portfolio", "action": "delete", "portfolio_id": "p-del"}],
            ),
            ToolResult(
                call_id="call-detail",
                name="portfolio_read_detail",
                ok=False,
                error="portfolio not found",
            ),
        ]
    )

    decision = harness.validate_progress(state)

    assert decision.complete is True


@pytest.mark.asyncio
async def test_portfolio_harness_allows_completion_after_delete():
    from dojoagents.agent.harnesses.portfolio import PortfolioTaskHarness

    async def delete_portfolio(args):
        return {
            "content": "deleted",
            "data": {"ok": True, "portfolio_id": args["portfolio_id"]},
            "resource_changes": [
                {"resource": "portfolio", "action": "delete", "portfolio_id": args["portfolio_id"]},
            ],
        }

    registry = ToolRegistry()
    registry.register(
        ToolSpec(
            name="portfolio_write_delete",
            description="Delete portfolio.",
            parameters={"type": "object", "properties": {"portfolio_id": {"type": "string"}}},
            handler=delete_portfolio,
        )
    )

    llm = StaticLLMProvider(
        [
            LLMResult(
                content="",
                tool_calls=[
                    ToolCall(id="call-del", name="portfolio_write_delete", arguments={"portfolio_id": "p-del"}),
                ],
            ),
            LLMResult(content="Portfolio deleted."),
        ]
    )

    loop = _make_loop(llm=llm, registry=registry, harnesses=[PortfolioTaskHarness()])
    response = await loop.run(_make_request("Delete the portfolio.", dashboard_tab="folio"))

    assert response.metadata.get("stopped") is None
    assert response.content == "Portfolio deleted."
