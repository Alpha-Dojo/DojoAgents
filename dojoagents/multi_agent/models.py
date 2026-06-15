"""Core data models for multi-agent orchestration."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class AgentRole(str, Enum):
    ORCHESTRATOR = "orchestrator"
    ANALYST = "analyst"
    IMPLEMENTER = "implementer"
    REVIEWER = "reviewer"
    SPECIALIST = "specialist"


class TaskStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class AgentSpec:
    """Defines a worker agent's configuration."""

    role: AgentRole
    name: str
    system_prompt_override: str = ""
    model: str | None = None
    allowed_tools: list[str] = field(default_factory=list)
    disallowed_tools: list[str] = field(default_factory=list)
    max_iterations: int = 50


@dataclass
class SubTask:
    """A unit of work delegated to a worker agent."""

    id: str
    title: str
    description: str
    assigned_to: AgentRole
    status: TaskStatus = TaskStatus.PENDING
    depends_on: list[str] = field(default_factory=list)
    result: str = ""
    artifacts: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentMessage:
    """Inter-agent communication message."""

    from_agent: str
    to_agent: str
    content: str
    message_type: str = "task_result"
    metadata: dict[str, Any] = field(default_factory=dict)
