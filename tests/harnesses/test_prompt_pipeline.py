import pytest

from dojoagents.harnesses.capabilities import PromptContributorSpec
from dojoagents.harnesses.errors import CapabilityConflictError
from dojoagents.harnesses.registries.prompts import PromptRegistry


@pytest.mark.asyncio
async def test_prompt_pipeline_has_immutable_core_first_and_fixed_phase_order():
    registry = PromptRegistry(
        (
            PromptContributorSpec("skill", "harness:test", phase="skills", contributor=lambda ctx: "skills"),
            PromptContributorSpec("identity-b", "harness:test", priority=2, phase="identity", contributor=lambda ctx: "b"),
            PromptContributorSpec("identity-a", "harness:test", priority=2, phase="identity", contributor=lambda ctx: "a"),
            PromptContributorSpec("memory", "harness:test", phase="memory", contributor=lambda ctx: "memory"),
        )
    )

    blocks = await registry.compose(object(), core_safety="immutable safety")

    assert [block.block_id for block in blocks] == ["core.safety", "identity-a", "identity-b", "skill", "memory"]
    assert blocks[0].content == "immutable safety"
    assert blocks[0].source == "core"


@pytest.mark.asyncio
async def test_prompt_pipeline_rejects_duplicate_or_reserved_block_ids():
    duplicate = PromptRegistry(
        (
            PromptContributorSpec("same", "harness:a", contributor=lambda ctx: "a"),
            PromptContributorSpec("same", "plugin:b", contributor=lambda ctx: "b"),
        )
    )
    with pytest.raises(CapabilityConflictError, match=r"same.*harness:a.*plugin:b"):
        await duplicate.compose(object(), core_safety="safe")

    reserved = PromptRegistry((PromptContributorSpec("core.safety", "harness:a", contributor=lambda ctx: "replace"),))
    with pytest.raises(CapabilityConflictError, match="core.safety"):
        await reserved.compose(object(), core_safety="safe")
