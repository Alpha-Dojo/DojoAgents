"""Data models for plan-driven execution."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class PlanStatus(str, Enum):
    DRAFT = "draft"
    APPROVED = "approved"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"
    REVISED = "revised"


class StepType(str, Enum):
    ANALYSIS = "analysis"
    IMPLEMENTATION = "implementation"
    VALIDATION = "validation"
    DECISION = "decision"
    DELEGATION = "delegation"


@dataclass
class PlanStep:
    id: str
    title: str
    description: str
    step_type: StepType
    depends_on: list[str] = field(default_factory=list)
    assigned_agent: str = "orchestrator"
    status: str = "pending"
    result: str = ""
    tools_needed: list[str] = field(default_factory=list)
    acceptance_criteria: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class Plan:
    id: str
    title: str
    objective: str
    steps: list[PlanStep] = field(default_factory=list)
    status: PlanStatus = PlanStatus.DRAFT
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    context: dict[str, Any] = field(default_factory=dict)
    revision_history: list[dict[str, Any]] = field(default_factory=list)

    def next_actionable_steps(self) -> list[PlanStep]:
        """Return steps whose dependencies are all completed."""
        completed_ids = {s.id for s in self.steps if s.status == "completed"}
        return [
            s for s in self.steps
            if s.status == "pending" and all(d in completed_ids for d in s.depends_on)
        ]

    def is_complete(self) -> bool:
        return all(s.status in ("completed", "skipped") for s in self.steps)
