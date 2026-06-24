"""Tests for dojoagents.planning.tools — create_plan, execute_plan, revise_plan tools."""

import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from dojoagents.planning.tools import get_plan_tools
from dojoagents.planning.engine import PlanExecutionEngine
from dojoagents.planning.store import PlanStateStore
from dojoagents.planning.models import Plan, PlanStep, PlanStatus, StepType
from dojoagents.tools.registry import ToolSpec


def _make_engine(tmp_path: Path):
    pool = MagicMock()
    pool.invoke = AsyncMock(return_value=MagicMock(content="result"))
    store = PlanStateStore(tmp_path)
    engine = PlanExecutionEngine(pool, store)
    return engine, store


class TestPlanTools:
    def test_returns_three_specs(self, tmp_path: Path):
        engine, _ = _make_engine(tmp_path)
        specs = get_plan_tools(engine)
        assert len(specs) == 3
        assert all(isinstance(s, ToolSpec) for s in specs)

    def test_tool_names(self, tmp_path: Path):
        engine, _ = _make_engine(tmp_path)
        specs = get_plan_tools(engine)
        names = {s.name for s in specs}
        assert names == {"create_plan", "execute_plan", "revise_plan"}

    @pytest.mark.asyncio
    async def test_create_plan_handler(self, tmp_path: Path):
        engine, store = _make_engine(tmp_path)
        specs = get_plan_tools(engine)
        create_spec = next(s for s in specs if s.name == "create_plan")
        result = await create_spec.handler({
            "title": "BTC Analysis",
            "objective": "Analyze BTC",
            "steps": [
                {"id": "s1", "title": "Research", "description": "Research BTC",
                 "step_type": "analysis"},
            ],
        })
        assert "BTC Analysis" in result
        assert "1 steps" in result
        # Plan saved to store
        ids = store.list_all()
        assert len(ids) == 1

    @pytest.mark.asyncio
    async def test_execute_plan_handler(self, tmp_path: Path):
        engine, store = _make_engine(tmp_path)
        # Pre-save a plan
        plan = Plan(
            id="exec1", title="Exec", objective="Test",
            steps=[PlanStep(id="s1", title="S1", description="D1", step_type=StepType.ANALYSIS)],
        )
        store.save(plan)
        specs = get_plan_tools(engine)
        exec_spec = next(s for s in specs if s.name == "execute_plan")
        result = await exec_spec.handler({"plan_id": "exec1", "session_id": "sess-1"})
        assert "exec1" in result or "Exec" in result

    @pytest.mark.asyncio
    async def test_revise_plan_handler(self, tmp_path: Path):
        engine, store = _make_engine(tmp_path)
        plan = Plan(id="rev1", title="Rev", objective="Test")
        store.save(plan)
        specs = get_plan_tools(engine)
        rev_spec = next(s for s in specs if s.name == "revise_plan")
        result = await rev_spec.handler({"plan_id": "rev1", "revision": "Need more analysis"})
        assert "Rev" in result or "rev1" in result
        loaded = store.get("rev1")
        assert loaded.status == PlanStatus.REVISED
        assert len(loaded.revision_history) == 1

    def test_create_plan_parameter_schema(self, tmp_path: Path):
        engine, _ = _make_engine(tmp_path)
        specs = get_plan_tools(engine)
        create_spec = next(s for s in specs if s.name == "create_plan")
        props = create_spec.parameters["properties"]
        assert "title" in props
        assert "objective" in props
        assert "steps" in props
