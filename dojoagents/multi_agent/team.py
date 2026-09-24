"""Run-scoped agent team; hosts provide durable, fenced mailbox storage."""

from __future__ import annotations

import asyncio
import hashlib
import json
import math
from contextvars import ContextVar, Token
from typing import Any, Awaitable, Callable

from dojoagents.multi_agent.mailbox import AgentAddress, AgentEnvelope, AgentInstance, MessageStore
from dojoagents.tools.registry import ToolSpec
from dojoagents.logging import LOGGER

ROOT_INSTANCE = "root"
AGENT_TEAM_PROTOCOL_VERSION = 1
MESSAGE_TYPES = frozenset({"task", "question", "reply", "progress", "result", "error"})
_TOOL_SUFFIXES = frozenset({"spawn", "send", "receive", "wait", "complete"})
_TOOL_NAMES = frozenset({f"agent.{suffix}" for suffix in _TOOL_SUFFIXES} | {f"agent_{suffix}" for suffix in _TOOL_SUFFIXES})


def is_agent_team_tool(name: str) -> bool:
    return name in _TOOL_NAMES


_team: ContextVar[AgentTeam | None] = ContextVar("dojo_agent_team", default=None)
_instance: ContextVar[str | None] = ContextVar("dojo_agent_instance", default=None)
_call_id: ContextVar[str | None] = ContextVar("dojo_agent_tool_call_id", default=None)


def bind_agent_team(team: AgentTeam, instance_id: str) -> tuple[Token, Token]:
    return _team.set(team), _instance.set(instance_id)


def reset_agent_team(tokens: tuple[Token, Token]) -> None:
    _instance.reset(tokens[1])
    _team.reset(tokens[0])


def bind_agent_tool_call(call_id: str) -> Token:
    return _call_id.set(call_id)


def reset_agent_tool_call(token: Token) -> None:
    _call_id.reset(token)


def current_agent_team() -> AgentTeam | None:
    return _team.get()


def current_agent_instance_id() -> str | None:
    return _instance.get()


class AgentTeam:
    def __init__(
        self,
        root_run_id: str,
        store: MessageStore,
        run_child: Callable[[AgentInstance], Awaitable[str]],
        *,
        allowed_roles: frozenset[str],
        max_children: int = 3,
        max_parallel: int = 2,
        deadline_seconds: float = 300,
    ) -> None:
        self.root_run_id = root_run_id
        self.store = store
        self.run_child = run_child
        self.allowed_roles = allowed_roles
        self.max_children = min(max(1, max_children), 3)
        self._slots = asyncio.Semaphore(min(max(1, max_parallel), 2))
        self.deadline = asyncio.get_running_loop().time() + max(0.0, deadline_seconds)
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._seen: dict[str, int] = {}
        self._waiting: dict[str, frozenset[str]] = {}
        self._pending_completion: dict[str, str] = {}

    @staticmethod
    def _caller() -> tuple[AgentTeam, str, str]:
        team, instance, call_id = _team.get(), _instance.get(), _call_id.get()
        if team is None or not instance or not call_id:
            raise ValueError("agent_team_context_missing")
        return team, instance, call_id

    async def spawn(self, role_id: str, task: str, *, caller: str, call_id: str) -> AgentInstance:
        if caller != ROOT_INSTANCE or role_id not in self.allowed_roles:
            raise ValueError("agent_spawn_forbidden")
        if not task.strip() or len(task.encode("utf-8")) > 16384:
            raise ValueError("agent_task_invalid")
        instances = await self.store.list_instances()
        key = hashlib.sha256(f"{self.root_run_id}:{call_id}".encode()).hexdigest()[:24]
        instance_id = f"agent-{key}"
        if not any(item.address.instance_id == instance_id for item in instances) and len(instances) >= self.max_children:
            raise ValueError("agent_instance_limit")
        instance = await self.store.create(
            AgentInstance(AgentAddress(self.root_run_id, instance_id), ROOT_INSTANCE, role_id, task.strip()),
            idempotency_key=f"spawn:{call_id}",
        )
        await self.store.send(ROOT_INSTANCE, instance_id, "task", task.strip(), idempotency_key=f"task:{call_id}")
        self._launch(instance)
        return instance

    def _launch(self, instance: AgentInstance) -> None:
        instance_id = instance.address.instance_id
        if instance.status in {"completed", "failed", "cancelled"}:
            return
        if instance_id in self._tasks and not self._tasks[instance_id].done():
            return

        async def run() -> None:
            tokens = bind_agent_team(self, instance_id)
            try:
                async with self._slots:
                    await self.store.set_status(instance_id, "runnable")
                    result = await self.run_child(instance)
                current = {item.address.instance_id: item for item in await self.store.list_instances()}
                if current[instance_id].status not in {"completed", "failed", "cancelled"}:
                    await self.store.complete(instance_id, self._pending_completion.get(instance_id, result))
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                current = {item.address.instance_id: item for item in await self.store.list_instances()}
                if current[instance_id].status not in {"completed", "failed", "cancelled"}:
                    await self.store.complete(instance_id, f"{type(exc).__name__}: {exc}", failed=True)
            finally:
                reset_agent_team(tokens)

        task = asyncio.create_task(run(), name=f"agent-team:{self.root_run_id}:{instance_id}")
        self._tasks[instance_id] = task

        def observe(done: asyncio.Task[None]) -> None:
            if done.cancelled():
                return
            try:
                done.result()
            except Exception:
                LOGGER.exception("Agent team child task failed: root_run_id=%s instance_id=%s", self.root_run_id, instance_id)

        task.add_done_callback(observe)

    async def resume(self) -> None:
        for instance in await self.store.list_instances():
            self._launch(instance)

    async def send(
        self,
        recipient: str,
        message_type: str,
        content: str,
        *,
        caller: str,
        call_id: str,
        in_reply_to: str | None = None,
    ) -> AgentEnvelope:
        if message_type not in MESSAGE_TYPES or not content.strip():
            raise ValueError("agent_message_invalid")
        if caller in self._pending_completion:
            raise ValueError("agent_completion_pending")
        if len(content.encode("utf-8")) > 16384:
            raise ValueError("agent_message_too_large")
        return await self.store.send(caller, recipient, message_type, content, idempotency_key=f"send:{call_id}", in_reply_to=in_reply_to)

    async def receive(self, *, caller: str, after_sequence: int | None = None, limit: int = 20) -> tuple[AgentEnvelope, ...]:
        if limit < 1 or limit > 20:
            raise ValueError("agent_receive_limit")
        cursor = self._seen.get(caller, 0) if after_sequence is None else max(0, after_sequence)
        messages = await self.store.receive(caller, after_sequence=cursor, limit=limit)
        if messages:
            self._seen[caller] = max(self._seen.get(caller, 0), messages[-1].recipient_sequence)
        return messages

    def consumed_sequence(self, instance_id: str) -> int:
        return self._seen.get(instance_id, 0)

    def restore_cursor(self, instance_id: str, sequence: int) -> None:
        self._seen[instance_id] = max(0, sequence)

    async def checkpoint(self, instance_id: str, transcript: list[dict[str, Any]]) -> None:
        await self.store.checkpoint(instance_id, transcript, self.consumed_sequence(instance_id))

    async def wait(self, targets: tuple[str, ...], *, caller: str, timeout_seconds: float = 30, in_reply_to: str | None = None) -> dict[str, Any]:
        if not math.isfinite(timeout_seconds):
            raise ValueError("agent_wait_invalid")
        targets = tuple(dict.fromkeys(targets))
        if bool(targets) == bool(in_reply_to) or len(targets) > self.max_children or caller in targets:
            raise ValueError("agent_wait_invalid")
        known = {ROOT_INSTANCE} | {item.address.instance_id for item in await self.store.list_instances()}
        if not set(targets) <= known:
            raise ValueError("agent_wait_unknown_target")

        def reaches(start: str, destination: str, visited: set[str]) -> bool:
            if start == destination:
                return True
            if start in visited:
                return False
            visited.add(start)
            return any(reaches(next_id, destination, visited) for next_id in self._waiting.get(start, ()))

        if any(reaches(target, caller, set()) for target in targets):
            raise ValueError("agent_wait_cycle")
        self._waiting[caller] = frozenset(targets)
        until = min(self.deadline, asyncio.get_running_loop().time() + min(max(timeout_seconds, 0), 30))
        collected: list[AgentEnvelope] = []
        try:
            await self.store.set_status(caller, "waiting")
            while True:
                instances = {item.address.instance_id: item for item in await self.store.list_instances()}
                instances[ROOT_INSTANCE] = AgentInstance(AgentAddress(self.root_run_id, ROOT_INSTANCE), None, "role.main", "", "runnable")
                messages = await self.receive(caller=caller)
                collected.extend(messages)
                replied = in_reply_to is not None and any(item.in_reply_to == in_reply_to for item in collected)
                finished = bool(targets) and all(instances[target].status in {"completed", "failed", "cancelled"} for target in targets)
                if replied or (in_reply_to is None and (messages or finished)):
                    return {"status": "ready", "instances": {target: instances[target].status for target in targets}, "messages": tuple(collected)}
                if asyncio.get_running_loop().time() >= until:
                    return {"status": "timeout", "instances": {target: instances[target].status for target in targets}, "messages": tuple(collected)}
                await asyncio.sleep(min(0.25, max(0, until - asyncio.get_running_loop().time())))
        finally:
            self._waiting.pop(caller, None)
            try:
                await self.store.set_status(caller, "runnable")
            except Exception:
                # Cancellation or fencing loss is handled by the root Run owner.
                pass

    async def complete(self, content: str, *, caller: str) -> dict[str, Any]:
        if caller == ROOT_INSTANCE:
            raise ValueError("agent_complete_root_forbidden")
        if not content.strip() or len(content.encode("utf-8")) > 16384:
            raise ValueError("agent_result_invalid")
        previous = self._pending_completion.setdefault(caller, content)
        if previous != content:
            raise ValueError("agent_result_conflict")
        return {"status": "pending", "instance_id": caller}

    async def close(self, *, suspending: bool = False) -> None:
        for task in self._tasks.values():
            if not task.done():
                task.cancel()
        if self._tasks:
            await asyncio.wait(self._tasks.values(), timeout=5)
        if not suspending:
            await self.store.cancel_active()


def _payload(value: Any) -> dict[str, Any]:
    if isinstance(value, AgentEnvelope):
        return {
            "message_id": value.message_id,
            "from": value.sender_instance_id,
            "to": value.recipient_instance_id,
            "type": value.type,
            "content": value.content,
            "sequence": value.recipient_sequence,
            "in_reply_to": value.in_reply_to,
        }
    return value


def get_agent_team_tool_specs() -> tuple[ToolSpec, ...]:
    async def handle(name: str, args: dict[str, Any]) -> dict[str, Any]:
        try:
            team, caller, call_id = AgentTeam._caller()
            if name == "agent.spawn":
                item = await team.spawn(str(args["role_id"]), str(args["task"]), caller=caller, call_id=call_id)
                data = {"instance_id": item.address.instance_id, "role_id": item.role_id, "status": item.status}
            elif name == "agent.send":
                data = _payload(
                    await team.send(str(args["to_instance_id"]), str(args["type"]), str(args["content"]), caller=caller, call_id=call_id, in_reply_to=args.get("in_reply_to"))
                )
            elif name == "agent.receive":
                items = await team.receive(caller=caller, after_sequence=args.get("after_sequence"), limit=int(args.get("limit", 20)))
                data = {"messages": [_payload(item) for item in items], "cursor": team.consumed_sequence(caller)}
            elif name == "agent.wait":
                result = await team.wait(
                    tuple(args.get("instance_ids") or ()), caller=caller, timeout_seconds=float(args.get("timeout_seconds", 30)), in_reply_to=args.get("in_reply_to")
                )
                data = {**result, "messages": [_payload(item) for item in result["messages"]]}
            else:
                data = _payload(await team.complete(str(args["content"]), caller=caller))
            return {"content": json.dumps(data, ensure_ascii=False, default=str), "data": data, "metadata": {"provider": "agent_team", "ok": True}}
        except Exception as exc:
            message = str(exc)
            code = message if message.startswith("agent_") and len(message) <= 80 else "agent_mailbox_unavailable"
            return {"content": code, "data": {"ok": False, "code": code}, "metadata": {"provider": "agent_team", "ok": False}}

    schemas = {
        "agent.spawn": ({"role_id": {"type": "string"}, "task": {"type": "string"}}, ["role_id", "task"]),
        "agent.send": (
            {"to_instance_id": {"type": "string"}, "type": {"type": "string", "enum": sorted(MESSAGE_TYPES)}, "content": {"type": "string"}, "in_reply_to": {"type": "string"}},
            ["to_instance_id", "type", "content"],
        ),
        "agent.receive": ({"after_sequence": {"type": "integer", "minimum": 0}, "limit": {"type": "integer", "minimum": 1, "maximum": 20}}, []),
        "agent.wait": (
            {"instance_ids": {"type": "array", "items": {"type": "string"}}, "in_reply_to": {"type": "string"}, "timeout_seconds": {"type": "number", "minimum": 0, "maximum": 30}},
            [],
        ),
        "agent.complete": ({"content": {"type": "string"}}, ["content"]),
    }
    return tuple(
        ToolSpec(
            name=name,
            description=f"Run-scoped agent communication: {name}. Only available inside an authorized agent team.",
            parameters={"type": "object", "properties": properties, "required": required, "additionalProperties": False},
            handler=lambda args, name=name: handle(name, args),
        )
        for name, (properties, required) in schemas.items()
    )
