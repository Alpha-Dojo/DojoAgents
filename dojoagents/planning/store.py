"""YAML-based persistence store for plan state."""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any

import yaml

from dojoagents.planning.models import Plan, PlanStep, PlanStatus, StepType


class PlanStateStore:
    """Stores plans as individual YAML files in a directory."""

    def __init__(self, path: str | Path = "~/.dojo/agents/plans") -> None:
        self.path = Path(path).expanduser()

    def _plan_file(self, plan_id: str) -> Path:
        return self.path / f"{plan_id}.yaml"

    def save(self, plan: Plan) -> None:
        """Serialize plan to YAML and write to {path}/{plan.id}.yaml."""
        self.path.mkdir(parents=True, exist_ok=True)
        data = _plan_to_dict(plan)
        self._plan_file(plan.id).write_text(
            yaml.safe_dump(data, sort_keys=False, allow_unicode=True),
            encoding="utf-8",
        )

    def get(self, plan_id: str) -> Plan:
        """Load a plan by ID. Raises FileNotFoundError if not found."""
        filepath = self._plan_file(plan_id)
        if not filepath.exists():
            raise FileNotFoundError(f"No plan with id '{plan_id}' at {filepath}")
        raw = yaml.safe_load(filepath.read_text(encoding="utf-8")) or {}
        return _dict_to_plan(raw)

    def list_all(self) -> list[str]:
        """Return all plan IDs in the store."""
        if not self.path.exists():
            return []
        return [f.stem for f in self.path.glob("*.yaml")]

    def delete(self, plan_id: str) -> None:
        """Delete a plan file. Raises FileNotFoundError if not found."""
        filepath = self._plan_file(plan_id)
        if not filepath.exists():
            raise FileNotFoundError(f"No plan with id '{plan_id}'")
        filepath.unlink()


def _plan_to_dict(plan: Plan) -> dict[str, Any]:
    data = asdict(plan)
    data["status"] = plan.status.value
    for step in data["steps"]:
        if isinstance(step.get("step_type"), StepType):
            step["step_type"] = step["step_type"].value
    return data


def _dict_to_plan(data: dict[str, Any]) -> Plan:
    steps = []
    for s in data.get("steps", []):
        step_type = s.get("step_type", "analysis")
        if isinstance(step_type, str):
            step_type = StepType(step_type)
        steps.append(PlanStep(
            id=s["id"],
            title=s["title"],
            description=s["description"],
            step_type=step_type,
            depends_on=s.get("depends_on", []),
            assigned_agent=s.get("assigned_agent", "orchestrator"),
            status=s.get("status", "pending"),
            result=s.get("result", ""),
            tools_needed=s.get("tools_needed", []),
            acceptance_criteria=s.get("acceptance_criteria", ""),
            metadata=s.get("metadata", {}),
        ))
    status = data.get("status", "draft")
    if isinstance(status, str):
        status = PlanStatus(status)
    return Plan(
        id=data["id"],
        title=data["title"],
        objective=data["objective"],
        steps=steps,
        status=status,
        created_at=data.get("created_at", ""),
        context=data.get("context", {}),
        revision_history=data.get("revision_history", []),
    )
