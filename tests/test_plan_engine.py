"""Tests for dojoagents.planning.engine — PlanExecutionEngine."""

import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from dojoagents.planning.engine import PlanExecutionEngine
from dojoagents.planning.models import Plan, PlanStep, PlanStatus, StepType
from dojoagents.planning.store import PlanStateStore
from dojoagents.agent.models import AgentResponse


def _make_pool() -> MagicMock:
    pool = MagicMock()
    pool.invoke = AsyncMock(return_value=AgentResponse(
        content="Step result", session_id="plan-step"
    ))
    return pool


def _make_engine(tmp_path: Path, pool: MagicMock | None = None):
    store = PlanStateStore(tmp_path)
    p = pool or _make_pool()
    engine = PlanExecutionEngine(p, store)
    return engine, store, p


class TestPlanExecutionEngine:
    @pytest.mark.asyncio
    async def test_execute_simple_plan(self, tmp_path: Path):
        engine, store, pool = _make_engine(tmp_path)
        plan = Plan(
            id="p1", title="Simple", objective="Test",
            steps=[
                PlanStep(id="s1", title="S1", description="D1", step_type=StepType.ANALYSIS),
                PlanStep(id="s2", title="S2", description="D2", step_type=StepType.ANALYSIS),
            ],
        )
        result = await engine.execute_plan(plan, "sess-1")
        assert result.status == PlanStatus.COMPLETED
        assert result.steps[0].status == "completed"
        assert result.steps[1].status == "completed"

    @pytest.mark.asyncio
    async def test_execute_plan_with_dependencies(self, tmp_path: Path):
        engine, store, pool = _make_engine(tmp_path)
        plan = Plan(
            id="p2", title="Deps", objective="Test",
            steps=[
                PlanStep(id="s1", title="S1", description="D1", step_type=StepType.ANALYSIS),
                PlanStep(id="s2", title="S2", description="D2", step_type=StepType.IMPLEMENTATION, depends_on=["s1"]),
            ],
        )
        result = await engine.execute_plan(plan, "sess-2")
        assert result.status == PlanStatus.COMPLETED
        # s1 must complete before s2
        assert result.steps[0].status == "completed"
        assert result.steps[1].status == "completed"

    @pytest.mark.asyncio
    async def test_execute_plan_step_failure(self, tmp_path: Path):
        pool = _make_pool()
        pool.invoke = AsyncMock(side_effect=RuntimeError("tool error"))
        engine, store, _ = _make_engine(tmp_path, pool)
        plan = Plan(
            id="p3", title="Fail", objective="Test",
            steps=[
                PlanStep(id="s1", title="S1", description="D1", step_type=StepType.ANALYSIS),
            ],
        )
        result = await engine.execute_plan(plan, "sess-3")
        assert result.status == PlanStatus.FAILED
        assert result.steps[0].status == "failed"

    @pytest.mark.asyncio
    async def test_execute_plan_delegation_step(self, tmp_path: Path):
        engine, store, pool = _make_engine(tmp_path)
        plan = Plan(
            id="p4", title="Delegate", objective="Test",
            steps=[
                PlanStep(id="s1", title="S1", description="Delegate to analyst",
                         step_type=StepType.DELEGATION, assigned_agent="analyst"),
            ],
        )
        result = await engine.execute_plan(plan, "sess-4")
        assert result.status == PlanStatus.COMPLETED
        # Pool was called with "analyst"
        call_args = pool.invoke.call_args
        assert call_args[0][0] == "analyst"

    @pytest.mark.asyncio
    async def test_execute_plan_saves_after_steps(self, tmp_path: Path):
        engine, store, pool = _make_engine(tmp_path)
        plan = Plan(
            id="p5", title="Save", objective="Test",
            steps=[
                PlanStep(id="s1", title="S1", description="D1", step_type=StepType.ANALYSIS),
            ],
        )
        await engine.execute_plan(plan, "sess-5")
        # Plan should be saved in store
        loaded = store.get("p5")
        assert loaded.status == PlanStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_deadlock_detection(self, tmp_path: Path):
        engine, store, pool = _make_engine(tmp_path)
        # Circular deps: s1 depends on s2, s2 depends on s1
        plan = Plan(
            id="p6", title="Deadlock", objective="Test",
            steps=[
                PlanStep(id="s1", title="S1", description="D1", step_type=StepType.ANALYSIS, depends_on=["s2"]),
                PlanStep(id="s2", title="S2", description="D2", step_type=StepType.ANALYSIS, depends_on=["s1"]),
            ],
        )
        result = await engine.execute_plan(plan, "sess-6")
        assert result.status == PlanStatus.FAILED

    @pytest.mark.asyncio
    async def test_context_includes_dep_results(self, tmp_path: Path):
        pool = _make_pool()
        pool.invoke = AsyncMock(side_effect=[
            AgentResponse(content="BTC is bullish", session_id="p7-s1"),
            AgentResponse(content="Strategy built", session_id="p7-s2"),
        ])
        engine, store, _ = _make_engine(tmp_path, pool)
        plan = Plan(
            id="p7", title="Context", objective="Test",
            steps=[
                PlanStep(id="s1", title="S1", description="Analyze", step_type=StepType.ANALYSIS),
                PlanStep(id="s2", title="S2", description="Build", step_type=StepType.IMPLEMENTATION, depends_on=["s1"]),
            ],
        )
        await engine.execute_plan(plan, "sess-7")
        # Second call should include first result in context
        second_call_msg = pool.invoke.call_args_list[1][0][1].message
        assert "BTC is bullish" in second_call_msg
