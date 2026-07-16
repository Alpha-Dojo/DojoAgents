from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class TaskArtifactSpec:
    filename: str
    format: str = "json"
    required: bool = True
    schema: str | None = None
    source_task: str | None = None


@dataclass(frozen=True)
class TaskContract:
    id: str
    version: int = 1
    name: str = ""
    harness_profile: str = "artifact_synthesis"
    inputs: list[TaskArtifactSpec] = field(default_factory=list)
    outputs: list[TaskArtifactSpec] = field(default_factory=list)
    required_tools: list[str] = field(default_factory=list)
    triggers: dict[str, Any] = field(default_factory=dict)
    channels: list[str] = field(default_factory=list)
    constraints: dict[str, Any] = field(default_factory=dict)
    downstream: str | None = None


@dataclass(frozen=True)
class TaskSpec:
    contract: TaskContract
    prompt_body: str
    task_dir: Path


@dataclass(frozen=True)
class PipelineStep:
    task: str
    on_success: str = "continue"
    input_map: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class PipelinePreflight:
    """Optional gates evaluated before a pipeline run starts."""

    require_any_trading_market: tuple[str, ...] = ()


@dataclass(frozen=True)
class PipelineSpec:
    id: str
    name: str = ""
    steps: list[PipelineStep] = field(default_factory=list)
    preflight: PipelinePreflight | None = None


@dataclass
class ActiveTask:
    task_id: str
    params: dict[str, Any] = field(default_factory=dict)
    harness_profile: str = ""
    constraints: dict[str, Any] = field(default_factory=dict)
    inputs: list[dict[str, Any]] = field(default_factory=list)
    outputs: list[dict[str, Any]] = field(default_factory=list)
    tool_budget_used: dict[str, int] = field(default_factory=dict)
    input_read: set[str] = field(default_factory=set)

    def to_metadata(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "params": dict(self.params),
            "harness_profile": self.harness_profile,
            "constraints": dict(self.constraints),
            "inputs": list(self.inputs),
            "outputs": list(self.outputs),
            "tool_budget_used": dict(self.tool_budget_used),
            "input_read": sorted(self.input_read),
        }

    @classmethod
    def from_metadata(cls, raw: Any) -> ActiveTask | None:
        if not isinstance(raw, dict):
            return None
        task_id = str(raw.get("task_id") or "").strip()
        if not task_id:
            return None
        params = raw.get("params")
        constraints = raw.get("constraints")
        inputs = raw.get("inputs")
        outputs = raw.get("outputs")
        budget = raw.get("tool_budget_used")
        input_read = raw.get("input_read")
        return cls(
            task_id=task_id,
            params=dict(params) if isinstance(params, dict) else {},
            harness_profile=str(raw.get("harness_profile") or ""),
            constraints=dict(constraints) if isinstance(constraints, dict) else {},
            inputs=list(inputs) if isinstance(inputs, list) else [],
            outputs=list(outputs) if isinstance(outputs, list) else [],
            tool_budget_used=dict(budget) if isinstance(budget, dict) else {},
            input_read=set(input_read) if isinstance(input_read, list) else set(),
        )


@dataclass
class PipelineState:
    id: str
    step: int = 1
    params: dict[str, Any] = field(default_factory=dict)
    artifacts: dict[str, str] = field(default_factory=dict)

    def to_metadata(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "step": self.step,
            "params": dict(self.params),
            "artifacts": dict(self.artifacts),
        }

    @classmethod
    def from_metadata(cls, raw: Any) -> PipelineState | None:
        if not isinstance(raw, dict):
            return None
        pipeline_id = str(raw.get("id") or "").strip()
        if not pipeline_id:
            return None
        params = raw.get("params")
        artifacts = raw.get("artifacts")
        step_raw = raw.get("step", 1)
        try:
            step = int(step_raw)
        except (TypeError, ValueError):
            step = 1
        return cls(
            id=pipeline_id,
            step=max(1, step),
            params=dict(params) if isinstance(params, dict) else {},
            artifacts=dict(artifacts) if isinstance(artifacts, dict) else {},
        )
