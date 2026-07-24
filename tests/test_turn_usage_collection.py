from __future__ import annotations

from types import SimpleNamespace

import pytest

from dojoagents.agent.models import LLMResult
from dojoagents.agent.usage import (
    MeteredLLMProvider,
    UsageCollector,
    bind_usage_collector,
    usage_scope,
)


class RecordingCoordinator:
    def __init__(self) -> None:
        self.records = []
        self.context_snapshots = []

    async def append_usage(self, records):
        self.records.extend(records)
        return tuple(records)

    async def append_context_usage(self, snapshots):
        self.context_snapshots.extend(snapshots)
        return tuple(snapshots)


class UsageProvider:
    name = "test-provider"

    async def chat(self, messages, tools, *, model, **kwargs):
        return LLMResult(
            content="answer",
            metadata={
                "usage": {
                    "prompt_tokens": 12,
                    "completion_tokens": 4,
                    "total_tokens": 16,
                    "reasoning_tokens": 2,
                }
            },
        )


@pytest.mark.asyncio
async def test_metered_provider_persists_each_invocation_and_groups_turn_usage():
    coordinator = RecordingCoordinator()
    collector = UsageCollector(
        session_uid="session-uid",
        run_id="run-1",
        turn_id="turn-1",
        harness_id="financial",
        coordinator=coordinator,
    )
    provider = MeteredLLMProvider(UsageProvider())

    with bind_usage_collector(collector):
        await provider.chat(
            [{"role": "user", "content": "one"}],
            [],
            model="model-a",
        )
        with usage_scope("turn_intent", "turn_intent.financial"):
            await provider.chat(
                [{"role": "user", "content": "classify"}],
                [],
                model="model-a",
            )

    assert len(coordinator.records) == 2
    assert [item.invocation_index for item in coordinator.records] == [1, 2]
    assert [item.category for item in coordinator.records] == [
        "agent_inference",
        "turn_intent",
    ]
    assert all(item.quality == "actual" for item in coordinator.records)
    assert len(coordinator.context_snapshots) == 2
    assert all(item.actual_input_tokens == 12 for item in coordinator.context_snapshots)
    assert collector.summary()["totals"]["total_tokens"] == 32
    assert collector.summary()["coverage"]["actual_calls"] == 2


class NoUsageProvider:
    name = "no-usage"

    async def chat(self, messages, tools, *, model, **kwargs):
        return SimpleNamespace(content="estimated response", metadata={})


@pytest.mark.asyncio
async def test_metered_provider_marks_locally_counted_usage_as_estimated():
    collector = UsageCollector(
        session_uid="session-uid",
        run_id="run-1",
        turn_id="turn-1",
    )
    with bind_usage_collector(collector):
        await MeteredLLMProvider(NoUsageProvider()).chat(
            [{"role": "user", "content": "estimate this request"}],
            [],
            model="model-a",
        )

    assert collector.records[0].quality == "estimated"
    assert collector.records[0].effective_total_tokens > 0
