"""Tests for dojoagents.planning.models — Plan, PlanStep, PlanStatus, StepType."""

import pytest

from dojoagents.planning.models import Plan, PlanStep, PlanStatus, StepType


class TestPlanStatus:
    def test_enum_values(self):
        assert PlanStatus.DRAFT == "draft"
        assert PlanStatus.APPROVED == "approved"
        assert PlanStatus.EXECUTING == "executing"
        assert PlanStatus.COMPLETED == "completed"
        assert PlanStatus.FAILED == "failed"
        assert PlanStatus.REVISED == "revised"

    def test_all_six(self):
        assert len(PlanStatus) == 6


class TestStepType:
    def test_enum_values(self):
        assert StepType.ANALYSIS == "analysis"
        assert StepType.IMPLEMENTATION == "implementation"
        assert StepType.VALIDATION == "validation"
        assert StepType.DECISION == "decision"
        assert StepType.DELEGATION == "delegation"

    def test_all_five(self):
        assert len(StepType) == 5


class TestPlanStep:
    def test_defaults(self):
        step = PlanStep(id="s1", title="Analyze", description="Analyze BTC", step_type=StepType.ANALYSIS)
        assert step.depends_on == []
        assert step.assigned_agent == "orchestrator"
        assert step.status == "pending"
        assert step.result == ""
        assert step.tools_needed == []
        assert step.acceptance_criteria == ""
        assert step.metadata == {}


class TestPlan:
    def test_defaults(self):
        plan = Plan(id="p1", title="Test", objective="Test obj")
        assert plan.status == PlanStatus.DRAFT
        assert plan.steps == []
        assert plan.revision_history == []
        assert plan.created_at  # non-empty ISO timestamp

    def test_next_actionable_steps_no_deps(self):
        steps = [
            PlanStep(id=f"s{i}", title=f"Step {i}", description=f"Desc {i}", step_type=StepType.ANALYSIS)
            for i in range(3)
        ]
        plan = Plan(id="p1", title="T", objective="O", steps=steps)
        actionable = plan.next_actionable_steps()
        assert len(actionable) == 3

    def test_next_actionable_steps_with_deps_pending(self):
        s1 = PlanStep(id="s1", title="S1", description="D1", step_type=StepType.ANALYSIS)
        s2 = PlanStep(id="s2", title="S2", description="D2", step_type=StepType.ANALYSIS, depends_on=["s1"])
        plan = Plan(id="p1", title="T", objective="O", steps=[s1, s2])
        actionable = plan.next_actionable_steps()
        assert len(actionable) == 1
        assert actionable[0].id == "s1"

    def test_next_actionable_steps_dep_completed(self):
        s1 = PlanStep(id="s1", title="S1", description="D1", step_type=StepType.ANALYSIS, status="completed")
        s2 = PlanStep(id="s2", title="S2", description="D2", step_type=StepType.ANALYSIS, depends_on=["s1"])
        plan = Plan(id="p1", title="T", objective="O", steps=[s1, s2])
        actionable = plan.next_actionable_steps()
        assert len(actionable) == 1
        assert actionable[0].id == "s2"

    def test_is_complete_all_completed(self):
        steps = [
            PlanStep(id=f"s{i}", title=f"S{i}", description=f"D{i}", step_type=StepType.ANALYSIS, status="completed")
            for i in range(3)
        ]
        plan = Plan(id="p1", title="T", objective="O", steps=steps)
        assert plan.is_complete()

    def test_is_complete_with_skipped(self):
        s1 = PlanStep(id="s1", title="S1", description="D1", step_type=StepType.ANALYSIS, status="completed")
        s2 = PlanStep(id="s2", title="S2", description="D2", step_type=StepType.ANALYSIS, status="skipped")
        plan = Plan(id="p1", title="T", objective="O", steps=[s1, s2])
        assert plan.is_complete()

    def test_is_complete_false_when_pending(self):
        s1 = PlanStep(id="s1", title="S1", description="D1", step_type=StepType.ANALYSIS, status="completed")
        s2 = PlanStep(id="s2", title="S2", description="D2", step_type=StepType.ANALYSIS, status="pending")
        plan = Plan(id="p1", title="T", objective="O", steps=[s1, s2])
        assert not plan.is_complete()
