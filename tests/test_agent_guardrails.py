from __future__ import annotations

import json
from dojoagents.agent.guardrails import (
    ToolCallGuardrailController,
    append_toolguard_guidance,
    toolguard_synthetic_result,
)


def test_guardrails_failures():
    controller = ToolCallGuardrailController(
        exact_failure_warn_after=2,
        exact_failure_block_after=4,
        same_tool_failure_warn_after=3,
        same_tool_failure_halt_after=5,
    )

    args = {"cmd": "npm test"}

    # First call: OK (no failures yet)
    decision = controller.before_call("terminal", args)
    assert decision.action == "allow"

    # Call fails
    decision = controller.after_call("terminal", args, "Error: test failed", failed=True)
    assert decision.action == "allow"  # Count = 1

    # Second call
    decision = controller.before_call("terminal", args)
    assert decision.action == "allow"

    # Call fails again -> warn (exact_failure_warn_after = 2)
    decision = controller.after_call("terminal", args, "Error: test failed", failed=True)
    assert decision.action == "warn"
    assert decision.code == "repeated_exact_failure_warning"

    # Third call with DIFFERENT arguments -> exact count doesn't increment, but same tool count becomes 3
    args2 = {"cmd": "pytest"}
    decision = controller.before_call("terminal", args2)
    assert decision.action == "allow"
    decision = controller.after_call("terminal", args2, "Error: test failed", failed=True)
    assert decision.action == "warn"
    assert decision.code == "same_tool_failure_warning"

    # Fourth call to the same failing signature -> block (exact_failure_block_after = 4)
    # Note: args has failed 2 times, args2 has failed 1 time.
    # Let's make args fail 2 more times to hit exact_failure_block_after (4).
    controller.after_call("terminal", args, "Error: test failed", failed=True)  # Count = 3
    decision = controller.before_call("terminal", args)
    assert decision.action == "allow"
    controller.after_call("terminal", args, "Error: test failed", failed=True)  # Count = 4
    decision = controller.before_call("terminal", args)
    assert decision.action == "block"
    assert decision.code == "repeated_exact_failure_block"


def test_guardrails_no_progress():
    controller = ToolCallGuardrailController(
        no_progress_warn_after=2, no_progress_block_after=2
    )

    args = {"path": "config.json"}

    # First read returns content A
    decision = controller.before_call("read_file", args)
    assert decision.action == "allow"
    decision = controller.after_call("read_file", args, "content A", failed=False)
    assert decision.action == "allow"  # repeat_count = 1

    # Second read returns content A again -> warn (repeat_count = 2)
    decision = controller.before_call("read_file", args)
    assert decision.action == "allow"
    decision = controller.after_call("read_file", args, "content A", failed=False)
    assert decision.action == "warn"
    assert decision.code == "idempotent_no_progress_warning"

    # Third read -> block because repeat_count is 2 >= no_progress_block_after (2)
    decision = controller.before_call("read_file", args)
    assert decision.action == "block"
    assert decision.code == "idempotent_no_progress_block"


def test_append_guidance_and_synthetic_result():
    controller = ToolCallGuardrailController(exact_failure_block_after=2)
    args = {"cmd": "invalid"}

    # Get a warn decision
    controller.after_call("terminal", args, "error", failed=True)
    warn_decision = controller.after_call("terminal", args, "error", failed=True)

    guided = append_toolguard_guidance("original result", warn_decision)
    assert "original result" in guided
    assert "Tool loop warning" in guided

    # Get a block decision (args has failed 2 times, exact_failure_block_after is 2)
    block_decision = controller.before_call("terminal", args)

    synth = toolguard_synthetic_result(block_decision)
    assert synth["metadata"]["ok"] is False
    assert synth["metadata"]["stopped"] == "block"
    content = json.loads(synth["content"])
    assert "error" in content
    assert "guardrail" in content
