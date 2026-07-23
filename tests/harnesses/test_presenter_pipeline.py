import pytest

from dojoagents.agent.models import ToolResult
from dojoagents.harnesses.capabilities import FlowPolicySpec, ResultPresenterSpec
from dojoagents.harnesses.decisions import CompletionDecision
from dojoagents.harnesses.errors import CapabilityConflictError
from dojoagents.harnesses.registries.policies import PolicyRegistry
from dojoagents.harnesses.registries.presenters import PresenterRegistry


@pytest.mark.asyncio
async def test_presenters_match_and_run_deterministically_after_core_result_shape():
    async def add_first(result, context):
        result.metadata["order"] = ["first"]
        return result

    async def add_second(result, context):
        result.metadata["order"].append("second")
        return result

    registry = PresenterRegistry(
        (
            ResultPresenterSpec("second", "harness:test", priority=1, presenter=add_second, match_kinds=("chart",)),
            ResultPresenterSpec("first", "harness:test", priority=2, presenter=add_first, match_kinds=("chart",)),
        )
    )
    result = ToolResult("1", "quote", True, data={"rows": []}, metadata={"kind": "chart"})

    presented = await registry.present((result,), object())

    assert isinstance(presented[0], ToolResult)
    assert presented[0].metadata["order"] == ["first", "second"]


def test_presenter_registry_rejects_overlapping_exclusive_matchers():
    with pytest.raises(CapabilityConflictError, match=r"chart.*harness:a.*plugin:b"):
        PresenterRegistry(
            (
                ResultPresenterSpec("one", "harness:a", match_kinds=("chart",), exclusive=True),
                ResultPresenterSpec("two", "plugin:b", match_kinds=("chart",), exclusive=True),
            )
        )


@pytest.mark.asyncio
async def test_completion_recovery_is_bounded_by_agent_hard_cap():
    async def recover(context):
        return CompletionDecision("recover", "missing_evidence", max_extra_turns=8)

    registry = PolicyRegistry(flow=(FlowPolicySpec("evidence", "harness:test", policy=recover),))
    decision = await registry.evaluate_completion(object(), hard_max_extra_turns=3)

    assert decision.action == "recover"
    assert decision.max_extra_turns == 3
