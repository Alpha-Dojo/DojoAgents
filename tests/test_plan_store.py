"""Tests for dojoagents.planning.store — PlanStateStore YAML persistence."""

import pytest
from pathlib import Path

from dojoagents.planning.store import PlanStateStore
from dojoagents.planning.models import Plan, PlanStep, PlanStatus, StepType


def _make_plan(plan_id: str = "p1", status: PlanStatus = PlanStatus.DRAFT) -> Plan:
    return Plan(
        id=plan_id,
        title=f"Plan {plan_id}",
        objective=f"Objective {plan_id}",
        status=status,
        steps=[
            PlanStep(id="s1", title="S1", description="D1", step_type=StepType.ANALYSIS),
        ],
    )


class TestPlanStateStore:
    def test_save_and_get(self, tmp_path: Path):
        store = PlanStateStore(tmp_path)
        plan = _make_plan()
        store.save(plan)
        loaded = store.get("p1")
        assert loaded.id == "p1"
        assert loaded.title == "Plan p1"
        assert len(loaded.steps) == 1

    def test_get_nonexistent_raises(self, tmp_path: Path):
        store = PlanStateStore(tmp_path)
        with pytest.raises((KeyError, FileNotFoundError)):
            store.get("nonexistent")

    def test_save_overwrite(self, tmp_path: Path):
        store = PlanStateStore(tmp_path)
        plan = _make_plan()
        store.save(plan)
        plan.status = PlanStatus.COMPLETED
        store.save(plan)
        loaded = store.get("p1")
        assert loaded.status == PlanStatus.COMPLETED

    def test_list_all(self, tmp_path: Path):
        store = PlanStateStore(tmp_path)
        for i in range(3):
            store.save(_make_plan(f"p{i}"))
        ids = store.list_all()
        assert sorted(ids) == ["p0", "p1", "p2"]

    def test_delete(self, tmp_path: Path):
        store = PlanStateStore(tmp_path)
        store.save(_make_plan())
        store.delete("p1")
        with pytest.raises((KeyError, FileNotFoundError)):
            store.get("p1")

    def test_creates_directory(self, tmp_path: Path):
        store_path = tmp_path / "plans" / "sub"
        store = PlanStateStore(store_path)
        store.save(_make_plan())
        assert store_path.exists()
