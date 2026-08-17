import pytest

from dojoagents.harnesses.base import HarnessDescriptor, validate_harness
from dojoagents.harnesses.decisions import CompletionDecision, ToolControlDecision
from dojoagents.harnesses.errors import InvalidHarnessError


@pytest.mark.parametrize("field", ["id", "version", "display_name"])
def test_descriptor_rejects_blank_required_fields(field):
    values = {"id": "financial", "version": "1.0", "display_name": "Financial"}
    values[field] = " "

    with pytest.raises(ValueError, match=field):
        HarnessDescriptor(**values)


class ValidHarness:
    descriptor = HarnessDescriptor("test", "1.0", "Test")

    def configure(self, builder, context):
        return None

    async def startup(self, context):
        return None

    async def shutdown(self, context):
        return None


def test_harness_contract_requires_sync_configure_and_async_lifecycle():
    validate_harness(ValidHarness())

    class AsyncConfigure(ValidHarness):
        async def configure(self, builder, context):
            return None

    class SyncStartup(ValidHarness):
        def startup(self, context):
            return None

    with pytest.raises(InvalidHarnessError, match="configure"):
        validate_harness(AsyncConfigure())
    with pytest.raises(InvalidHarnessError, match="startup"):
        validate_harness(SyncStartup())


def test_decisions_validate_actions_codes_and_recovery_bound():
    assert ToolControlDecision("allow", "tool_allowed").action == "allow"
    assert CompletionDecision("recover", "missing_eval", max_extra_turns=2).max_extra_turns == 2
    with pytest.raises(ValueError, match="action"):
        ToolControlDecision("override_sandbox", "bad")
    with pytest.raises(ValueError, match="code"):
        CompletionDecision("complete", " ")
    with pytest.raises(ValueError, match="max_extra_turns"):
        CompletionDecision("recover", "bad_budget", max_extra_turns=101)
