from __future__ import annotations

from dojoagents.agent.context_usage import (
    PromptContextSource,
    build_context_snapshot,
    context_snapshot_projection,
    reconcile_context_snapshot,
)
from dojoagents.agent.loop import strands_to_dojo_messages


def _snapshot(messages, tools=(), sources=()):
    return build_context_snapshot(
        snapshot_id="snapshot-1",
        session_uid="session-uid",
        run_id="run-1",
        turn_id="turn-1",
        invocation_id="invocation-1",
        invocation_index=1,
        agent_id="dojo-agent",
        harness_id="financial",
        provider="provider-a",
        model="model-a",
        messages=messages,
        tools=tools,
        prompt_sources=sources,
        context_window_tokens=1000,
    )


def test_context_snapshot_attributes_prompt_tools_and_conversation():
    sources = (
        PromptContextSource(
            "identity",
            "identity",
            "You are the agent.",
            "harness:test",
        ),
        PromptContextSource(
            "rules",
            "harness_instructions",
            "Follow these detailed rules. " * 4,
            "harness:test",
        ),
        PromptContextSource(
            "skills",
            "skills",
            "Available skill instructions. " * 4,
            "core:skill-manager",
        ),
    )
    system = "\n\n".join(item.content for item in sources)
    snapshot = _snapshot(
        [
            {"role": "system", "content": system},
            {"role": "user", "content": "Analyze this portfolio. " * 4},
        ],
        tools=(
            {
                "name": "portfolio_read",
                "description": "Read portfolio details. " * 4,
                "parameters": {
                    "type": "object",
                    "properties": {"portfolio_id": {"type": "string"}},
                },
            },
        ),
        sources=sources,
    )

    categories = {item.category for item in snapshot.components}
    assert categories == {
        "system_prompt",
        "rules",
        "skills",
        "tool_definitions",
        "conversation",
    }
    assert not snapshot.manifest_mismatch
    assert snapshot.estimated_input_tokens == sum(item.estimated_tokens for item in snapshot.components)


def test_context_snapshot_does_not_double_count_mismatched_system_manifest():
    snapshot = _snapshot(
        [{"role": "system", "content": "actual system text"}],
        sources=(
            PromptContextSource(
                "identity",
                "identity",
                "different manifest",
                "harness:test",
            ),
        ),
    )

    assert snapshot.manifest_mismatch
    assert len(snapshot.components) == 1
    assert snapshot.components[0].category == "other"


def test_provider_reconciliation_keeps_estimates_and_exposes_overhead():
    snapshot = _snapshot([{"role": "user", "content": "long conversation text " * 20}])
    reconciled = reconcile_context_snapshot(
        snapshot,
        actual_input_tokens=snapshot.estimated_input_tokens + 25,
        status="succeeded",
    )
    projection = context_snapshot_projection(reconciled)

    assert projection is not None
    assert projection["used_tokens_source"] == "provider_actual"
    assert projection["reconciliation_delta_tokens"] == 25
    assert any(item["category"] == "protocol_overhead" and item["tokens"] == 25 for item in projection["breakdown"])


def test_plugin_orchestration_context_is_subagent_definition():
    snapshot = _snapshot(
        [
            {
                "role": "user",
                "content": ("Please solve this." "\n\n[Plugin Context]\n" "You have specialist agents that you can delegate tasks to. " * 4),
            }
        ]
    )

    assert {item.category for item in snapshot.components} == {
        "conversation",
        "subagent_definitions",
    }


def test_strands_system_messages_reach_provider_for_memory_attribution():
    messages = strands_to_dojo_messages(
        [
            {
                "role": "system",
                "content": [{"text": "retrieved memory"}],
            },
            {"role": "user", "content": [{"text": "question"}]},
        ],
        "base prompt",
    )

    assert messages[:2] == [
        {"role": "system", "content": "base prompt"},
        {"role": "system", "content": "retrieved memory"},
    ]


def test_uploaded_file_context_is_not_hidden_in_conversation():
    snapshot = _snapshot(
        [
            {
                "role": "user",
                "content": ("Analyze it." "\n\n## Attached Files\n" "- `holdings.csv` (csv) → `/safe/holdings.csv`\n"),
            }
        ]
    )

    assert {item.category for item in snapshot.components} == {
        "conversation",
        "attachments",
    }
