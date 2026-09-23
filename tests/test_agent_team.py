"""Run-scoped mailbox contract tests without a product-specific store."""

from __future__ import annotations

import asyncio
import hashlib
from dataclasses import replace

import pytest

from dojoagents.multi_agent.mailbox import AgentAddress, AgentEnvelope, AgentInstance
from dojoagents.multi_agent.team import AgentTeam, ROOT_INSTANCE, bind_agent_team, bind_agent_tool_call, get_agent_team_tool_specs, reset_agent_team, reset_agent_tool_call
from dojoagents.agent.events import AgentEventSink
from dojoagents.agent.loop import AgentLoop
from dojoagents.agent.models import ChatRequest, LLMResult, ToolCall
from dojoagents.agent.providers import StaticLLMProvider
from dojoagents.config.models import AgentConfig
from dojoagents.dojo_extensions.registry import DojoExtensionRegistry
from dojoagents.memory.manager import MemoryManager
from dojoagents.skills.manager import SkillManager
from dojoagents.tools.executor import ToolExecutor
from dojoagents.tools.registry import ToolRegistry
from dojoagents.tools.sandbox import SandboxPolicy


class Store:
    def __init__(self):
        self.instances = {}
        self.messages = []

    async def create(self, instance, *, idempotency_key):
        self.instances.setdefault(instance.address.instance_id, instance)
        return self.instances[instance.address.instance_id]

    async def send(self, sender, recipient, message_type, content, *, idempotency_key, in_reply_to=None, artifact_refs=()):
        for message, key in self.messages:
            if key == (sender, idempotency_key):
                if message.content != content:
                    raise ValueError("agent_message_idempotency_conflict")
                return message
        envelope = AgentEnvelope(
            f"message-{len(self.messages) + 1}",
            "run-1",
            sender,
            recipient,
            message_type,
            content,
            1 + sum(item.sender_instance_id == sender for item, _ in self.messages),
            1 + sum(item.recipient_instance_id == recipient for item, _ in self.messages),
            in_reply_to,
        )
        self.messages.append((envelope, (sender, idempotency_key)))
        return envelope

    async def receive(self, recipient, *, after_sequence, limit):
        return tuple(item for item, _ in self.messages if item.recipient_instance_id == recipient and item.recipient_sequence > after_sequence)[:limit]

    async def list_instances(self):
        return tuple(self.instances.values())

    async def set_status(self, instance_id, status):
        if instance_id in self.instances:
            self.instances[instance_id] = replace(self.instances[instance_id], status=status)

    async def complete(self, instance_id, content, *, failed=False):
        self.instances[instance_id] = replace(self.instances[instance_id], status="failed" if failed else "completed")
        return await self.send(instance_id, ROOT_INSTANCE, "error" if failed else "result", content, idempotency_key="complete")

    async def checkpoint(self, instance_id, messages, consumed_sequence):
        self.instances[instance_id] = replace(self.instances[instance_id], last_consumed_sequence=consumed_sequence)

    async def cancel_active(self):
        for key, instance in self.instances.items():
            if instance.status not in {"completed", "failed", "cancelled"}:
                self.instances[key] = replace(instance, status="cancelled")


@pytest.mark.asyncio
async def test_spawn_wait_and_complete_only_after_child_returns():
    store = Store()
    allow_finish = asyncio.Event()

    async def run_child(instance):
        assert (await team.receive(caller=instance.address.instance_id))[0].type == "task"
        await allow_finish.wait()
        return "done"

    team = AgentTeam("run-1", store, run_child, allowed_roles=frozenset({"research"}))
    root = bind_agent_team(team, ROOT_INSTANCE)
    call = bind_agent_tool_call("call-1")
    try:
        specs = {item.name: item for item in get_agent_team_tool_specs()}
        spawned = await specs["agent.spawn"].handler({"role_id": "research", "task": "analyze"})
        instance_id = spawned["data"]["instance_id"]
        assert (await team.wait((instance_id,), caller=ROOT_INSTANCE, timeout_seconds=0))["status"] == "timeout"
        allow_finish.set()
        result = await team.wait((instance_id,), caller=ROOT_INSTANCE, timeout_seconds=2)
        assert result["messages"][0].content == "done"
        assert result["instances"][instance_id] == "completed"
    finally:
        reset_agent_tool_call(call)
        reset_agent_team(root)
        await team.close()


@pytest.mark.asyncio
async def test_context_is_required_and_wait_cycles_fail_closed():
    store = Store()
    team = AgentTeam("run-1", store, lambda _: None, allowed_roles=frozenset({"research"}))
    spec = {item.name: item for item in get_agent_team_tool_specs()}["agent.send"]
    assert (await spec.handler({"to_instance_id": "root", "type": "question", "content": "x"}))["data"]["code"] == "agent_team_context_missing"
    instance = AgentInstance(AgentAddress("run-1", "child"), ROOT_INSTANCE, "research", "task")
    store.instances["child"] = instance
    team._waiting[ROOT_INSTANCE] = frozenset({"child"})
    with pytest.raises(ValueError, match="agent_wait_cycle"):
        await team.wait((ROOT_INSTANCE,), caller="child", timeout_seconds=0)
    team._waiting.clear()
    question = await store.send(ROOT_INSTANCE, "child", "question", "Which date?", idempotency_key="question")
    await store.send("child", ROOT_INSTANCE, "reply", "Today", idempotency_key="reply", in_reply_to=question.message_id)
    reply = await team.wait((), caller=ROOT_INSTANCE, in_reply_to=question.message_id, timeout_seconds=0)
    assert reply["messages"][-1].content == "Today"


@pytest.mark.asyncio
async def test_agent_loop_executes_team_tools_without_streaming_private_results():
    store = Store()

    async def run_child(_instance):
        return "secret specialist analysis"

    team = AgentTeam("run-1", store, run_child, allowed_roles=frozenset({"research"}))
    instance_id = "agent-" + hashlib.sha256(b"run-1:spawn-1").hexdigest()[:24]
    provider = StaticLLMProvider(
        [
            LLMResult("", [ToolCall("spawn-1", "agent_spawn", {"role_id": "research", "task": "private assignment"})]),
            LLMResult("", [ToolCall("wait-1", "agent_wait", {"instance_ids": [instance_id], "timeout_seconds": 2})]),
            LLMResult("public synthesis"),
        ]
    )
    registry = ToolRegistry()
    for spec in get_agent_team_tool_specs():
        registry.register(spec)
    loop = AgentLoop(
        llm_provider=provider,
        tool_executor=ToolExecutor(registry, SandboxPolicy(timeout_seconds=3)),
        skill_manager=SkillManager([]),
        memory_manager=MemoryManager(),
        extension_registry=DojoExtensionRegistry(),
        config=AgentConfig(model="test-model", enable_guardrails=False, enable_context_compression=False),
    )
    loop.model_context_registry.resolve = lambda *args: asyncio.sleep(0, result=32768)
    sink = AgentEventSink(run_id="run-1", session_id="session-1")
    checkpoints = []

    async def checkpoint(messages):
        checkpoints.extend(messages)

    tokens = bind_agent_team(team, ROOT_INSTANCE)
    try:
        response = await loop.run(
            ChatRequest(
                message="Compare domains",
                user_id="alice",
                session_id="session-1",
                metadata={"persist_session": False, "_agent_inbox": lambda: team.receive(caller=ROOT_INSTANCE), "_agent_message_checkpoint": checkpoint},
            ),
            event_sink=sink,
        )
        assert response.content == "public synthesis"
        projected = str(sink.events)
        assert "secret specialist analysis" not in projected
        assert "private assignment" not in projected
        assert any(message.get("_agent_internal") for message in checkpoints)
    finally:
        reset_agent_team(tokens)
        await team.close()
