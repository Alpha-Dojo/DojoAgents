import pytest

from dojoagents.agent.models import ToolCall
from dojoagents.harnesses.capabilities import ToolAuthorizerSpec, ToolTransformerSpec
from dojoagents.harnesses.decisions import ToolControlDecision
from dojoagents.harnesses.registries.policies import PolicyRegistry


@pytest.mark.asyncio
async def test_transform_precedes_revalidation_and_authorization_cannot_weaken_core():
    events = []

    async def transform(call, context):
        events.append("transform")
        return ToolCall(call.id, "danger", dict(call.arguments))

    async def validate(call):
        events.append(f"validate:{call.name}")

    async def core(call, context):
        events.append("core")
        return ToolControlDecision("block", "core_block")

    async def harness_allow(call, context):
        events.append("harness")
        return ToolControlDecision("allow", "harness_allow")

    registry = PolicyRegistry(
        authorizers=(ToolAuthorizerSpec("allow", "harness:test", authorizer=harness_allow),),
        transformers=(ToolTransformerSpec("rename", "harness:test", transformer=transform),),
    )
    calls = await registry.transform_calls((ToolCall("1", "safe", {}),), object(), revalidate=validate)
    decision = await registry.authorize(calls[0], object(), core_authorizer=core)

    assert calls[0].name == "danger"
    assert decision == ToolControlDecision("block", "core_block")
    assert events == ["transform", "validate:danger", "core"]


@pytest.mark.asyncio
async def test_harness_can_further_restrict_and_exceptions_are_structured_failures():
    async def core(call, context):
        return ToolControlDecision("allow", "core_allow")

    async def harness_block(call, context):
        return ToolControlDecision("block", "risk_limit")

    restricted = PolicyRegistry(authorizers=(ToolAuthorizerSpec("risk", "harness:test", authorizer=harness_block),))
    decision = await restricted.authorize(ToolCall("1", "trade", {}), object(), core_authorizer=core)
    assert decision.code == "risk_limit"

    async def broken(call, context):
        raise RuntimeError("secret internals")

    failing = PolicyRegistry(authorizers=(ToolAuthorizerSpec("broken", "harness:test", authorizer=broken),))
    decision = await failing.authorize(ToolCall("1", "trade", {}), object(), core_authorizer=core)
    assert decision.action == "halt"
    assert decision.code == "harness_policy_error"
    assert "secret internals" not in decision.message
