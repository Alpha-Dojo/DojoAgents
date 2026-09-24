"""Storage-neutral contracts for communication between agents in one run."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class AgentAddress:
    root_run_id: str
    instance_id: str


@dataclass(frozen=True)
class AgentInstance:
    address: AgentAddress
    parent_instance_id: str | None
    role_id: str
    task: str
    status: str = "created"
    last_consumed_sequence: int = 0


@dataclass(frozen=True)
class AgentEnvelope:
    message_id: str
    root_run_id: str
    sender_instance_id: str
    recipient_instance_id: str
    type: str
    content: str
    sender_sequence: int
    recipient_sequence: int
    in_reply_to: str | None = None
    artifact_refs: tuple[str, ...] = ()
    schema_version: int = 1


class MessageStore(Protocol):
    """The host owns authorization, fencing, storage, and atomic checkpoints."""

    async def create(self, instance: AgentInstance, *, idempotency_key: str) -> AgentInstance:
        pass

    async def send(
        self,
        sender: str,
        recipient: str,
        message_type: str,
        content: str,
        *,
        idempotency_key: str,
        in_reply_to: str | None = None,
        artifact_refs: tuple[str, ...] = (),
    ) -> AgentEnvelope:
        pass

    async def receive(self, recipient: str, *, after_sequence: int, limit: int) -> tuple[AgentEnvelope, ...]:
        pass

    async def list_instances(self) -> tuple[AgentInstance, ...]:
        pass

    async def set_status(self, instance_id: str, status: str) -> None:
        pass

    async def complete(self, instance_id: str, content: str, *, failed: bool = False) -> AgentEnvelope:
        pass

    async def checkpoint(self, instance_id: str, messages: list[dict[str, Any]], consumed_sequence: int) -> None:
        pass

    async def cancel_active(self) -> None:
        pass
