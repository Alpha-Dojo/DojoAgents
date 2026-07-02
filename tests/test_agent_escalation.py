from __future__ import annotations

import pytest

from dojoagents.agent.escalation import (
    AgentEscalationError,
    STOP_CODE_NEEDS_USER_INPUT,
    escalation_metadata,
    find_user_input_escalation,
)
from dojoagents.agent.harness import HarnessDecision, HarnessLoopState
from dojoagents.agent.harnesses.portfolio import PortfolioTaskHarness
from dojoagents.agent.models import ChatRequest, ToolResult
from dojoagents.tools.executor import ToolExecutor
from dojoagents.tools.registry import ToolRegistry, ToolSpec
from dojoagents.tools.sandbox import SandboxPolicy


def test_executor_preserves_escalation_metadata() -> None:
    async def handler(_args: dict) -> dict:
        raise AgentEscalationError(
            "capital_budget_exceeded",
            "Capital budget exceeded",
            context={"shortfall": 850000.0},
            recoverable_by_agent=False,
        )

    registry = ToolRegistry()
    registry.register(
        ToolSpec(
            name="portfolio_write_create_orders",
            description="test",
            parameters={"type": "object", "properties": {}},
            handler=handler,
        )
    )
    executor = ToolExecutor(registry, SandboxPolicy(timeout_seconds=2))

    import asyncio
    from dojoagents.agent.models import ToolCall

    result = asyncio.run(
        executor.execute_one(
            ToolCall(id="call-1", name="portfolio_write_create_orders", arguments={}),
            session_id="sess",
        )
    )

    assert result.ok is False
    assert result.error == "Capital budget exceeded"
    assert result.metadata["escalation"]["code"] == "capital_budget_exceeded"
    assert result.metadata["escalation"]["requires_user_input"] is True


def test_find_user_input_escalation_returns_latest_signal() -> None:
    result = ToolResult(
        call_id="call-1",
        name="portfolio_write_create_orders",
        ok=False,
        error="Capital budget exceeded",
        metadata=escalation_metadata(
            AgentEscalationError(
                "capital_budget_exceeded",
                "Capital budget exceeded",
                context={"shortfall": 1.0},
            ),
            source_tool="portfolio_write_create_orders",
        ),
    )
    signal = find_user_input_escalation([result])
    assert signal is not None
    assert signal.code == "capital_budget_exceeded"


def test_portfolio_harness_stops_auto_recovery_on_capital_escalation() -> None:
    harness = PortfolioTaskHarness()
    request = ChatRequest(user_id="u", session_id="s", channel="dashboard", message="建仓")
    state = HarnessLoopState(request=request)
    state.tool_results.append(
        ToolResult(
            call_id="call-orders",
            name="portfolio_write_create_orders",
            ok=False,
            error="Capital budget exceeded",
            metadata=escalation_metadata(
                AgentEscalationError(
                    "capital_budget_exceeded",
                    "Capital budget exceeded — cn: shortfall 850000",
                    context={
                        "native_market": "cn",
                        "shortfall": 850000.0,
                        "user_options": ["Raise cn initial capital"],
                    },
                    recoverable_by_agent=False,
                ),
                source_tool="portfolio_write_create_orders",
            ),
        )
    )

    decision = harness.validate_progress(state)

    assert decision.complete is False
    assert decision.stop_code == STOP_CODE_NEEDS_USER_INPUT
    assert decision.allow_extra_steps is False
    assert decision.escalation_code == "capital_budget_exceeded"


def test_portfolio_harness_blocks_retry_after_capital_escalation() -> None:
    harness = PortfolioTaskHarness()
    request = ChatRequest(user_id="u", session_id="s", channel="dashboard", message="建仓")
    state = HarnessLoopState(request=request)
    state.tool_results.append(
        ToolResult(
            call_id="call-orders",
            name="portfolio_write_create_orders",
            ok=False,
            error="Capital budget exceeded",
            metadata=escalation_metadata(
                AgentEscalationError("capital_budget_exceeded", "Capital budget exceeded"),
                source_tool="portfolio_write_create_orders",
            ),
        )
    )

    from dojoagents.agent.models import ToolCall

    blocked = harness.block_tool_call(
        ToolCall(id="call-2", name="portfolio_write_create_orders", arguments={}),
        state,
    )

    assert blocked is not None
    assert "Blocked portfolio_write_create_orders" in blocked


def test_portfolio_harness_user_input_recovery_prompt_is_localized() -> None:
    harness = PortfolioTaskHarness()
    decision = HarnessDecision(
        complete=False,
        stop_code=STOP_CODE_NEEDS_USER_INPUT,
        allow_extra_steps=False,
        issues=["Capital budget exceeded"],
        next_steps=["Raise cn initial capital"],
    )

    zh = harness.build_recovery_prompt(decision, "zh")
    en = harness.build_recovery_prompt(decision, "en")

    assert "需用户确认" in zh
    assert "Needs user input" in en
    assert "Raise cn initial capital" in en
