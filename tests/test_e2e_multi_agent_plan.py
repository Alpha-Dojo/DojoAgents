"""End-to-end tests for multi-agent + plan architecture integration."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from dojoagents.agent.models import AgentResponse, ChatRequest
from dojoagents.multi_agent.models import AgentRole, AgentSpec, SubTask, TaskStatus
from dojoagents.multi_agent.pool import AgentPool
from dojoagents.multi_agent.tools import get_delegation_tool_spec
from dojoagents.multi_agent.triggers import MultiAgentTriggerHook
from dojoagents.multi_agent.orchestrator import Orchestrator
from dojoagents.planning.engine import PlanExecutionEngine
from dojoagents.planning.models import Plan, PlanStatus, PlanStep, StepType
from dojoagents.planning.store import PlanStateStore
from dojoagents.planning.tools import get_plan_tools
from dojoagents.planning.triggers import PlanActivationHook


# ── Helpers ──────────────────────────────────────────────────────────────────


def _make_mock_pool(responses: dict[str, str] | None = None):
    """Create a mock AgentPool that returns canned responses by agent name."""
    pool = MagicMock(spec=AgentPool)
    default_resp = "Task completed successfully."

    async def _invoke(name: str, request: ChatRequest) -> AgentResponse:
        content = (responses or {}).get(name, default_resp)
        return AgentResponse(content=content, session_id=request.session_id)

    pool.invoke = AsyncMock(side_effect=_invoke)
    return pool


def _make_plan_store(tmp_path):
    return PlanStateStore(str(tmp_path / "plans"))


# ── E2E: Plan Full Lifecycle ─────────────────────────────────────────────────


class TestPlanFullLifecycle:
    @pytest.mark.asyncio
    async def test_create_execute_complete_plan(self, tmp_path):
        """Full lifecycle: create plan → execute all steps → completed status."""
        store = _make_plan_store(tmp_path)
        pool = _make_mock_pool({"orchestrator": "Analysis result"})
        engine = PlanExecutionEngine(pool, store)

        plan = Plan(
            id="e2e-001",
            title="Market Analysis",
            objective="Analyze market trends",
            steps=[
                PlanStep(id="s1", title="Gather data", description="Collect market data",
                         step_type=StepType.ANALYSIS),
                PlanStep(id="s2", title="Analyze", description="Analyze collected data",
                         step_type=StepType.DECISION, depends_on=["s1"]),
            ],
        )
        store.save(plan)

        result = await engine.execute_plan(plan, session_id="test-session")

        assert result.status == PlanStatus.COMPLETED
        assert result.steps[0].status == "completed"
        assert result.steps[1].status == "completed"
        assert result.steps[0].result == "Analysis result"
        # Verify persisted
        persisted = store.get("e2e-001")
        assert persisted.status == PlanStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_plan_with_delegation_step(self, tmp_path):
        """Plan with a DELEGATION step invokes the correct pool agent."""
        store = _make_plan_store(tmp_path)
        pool = _make_mock_pool({
            "analyst": "Detailed analysis report",
            "orchestrator": "Orchestrator decision",
        })
        engine = PlanExecutionEngine(pool, store)

        plan = Plan(
            id="e2e-002",
            title="Delegation Plan",
            objective="Delegate and decide",
            steps=[
                PlanStep(id="d1", title="Delegate analysis", description="Run analysis",
                         step_type=StepType.DELEGATION, assigned_agent="analyst"),
                PlanStep(id="d2", title="Make decision", description="Decide based on analysis",
                         step_type=StepType.DECISION, depends_on=["d1"]),
            ],
        )

        result = await engine.execute_plan(plan, session_id="session-2")

        assert result.status == PlanStatus.COMPLETED
        # Verify analyst was invoked for delegation step
        calls = pool.invoke.call_args_list
        assert any(c[0][0] == "analyst" for c in calls)
        assert result.steps[0].result == "Detailed analysis report"


# ── E2E: Delegation Tool ─────────────────────────────────────────────────────


class TestDelegationToolE2E:
    @pytest.mark.asyncio
    async def test_delegate_task_tool_invokes_pool(self):
        """delegate_task tool handler invokes pool and returns content."""
        pool = _make_mock_pool({"implementer": "Code written successfully"})
        tool_spec = get_delegation_tool_spec(pool)

        result = await tool_spec.handler({
            "agent_role": "implementer",
            "task_description": "Write a trading bot",
            "context": "Previous analysis shows BTC trending up",
        })

        assert result == "Code written successfully"
        pool.invoke.assert_called_once()
        call_args = pool.invoke.call_args
        assert call_args[0][0] == "implementer"
        req = call_args[0][1]
        assert isinstance(req, ChatRequest)
        assert "Write a trading bot" in req.message
        assert req.channel == "internal"


# ── E2E: Trigger Detection → Orchestrator Activation ─────────────────────────


class TestTriggerToOrchestrator:
    def test_complexity_trigger_returns_orchestration_prompt(self):
        """MultiAgentTriggerHook detects complex request and returns orchestration prompt."""
        orchestrator = Orchestrator()
        hook = MultiAgentTriggerHook(orchestrator)

        result = hook.on_pre_llm_call(
            user_message="Analyze the market data and then implement a trading strategy",
            session_id="sess-1",
        )

        # pre_llm_call returns the prompt but does not activate the orchestrator
        assert result is not None
        assert "multi-agent" in result.lower() or "orchestration" in result.lower()

    def test_tool_result_trigger_activates_orchestrator(self):
        """Post-tool-call trigger activates orchestrator on failure patterns."""
        orchestrator = Orchestrator()
        hook = MultiAgentTriggerHook(orchestrator)

        hook.on_post_tool_call(
            tool_name="code_execution",
            result="error: compilation failed with multiple errors",
            session_id="sess-2",
        )

        assert orchestrator.is_active("sess-2")


# ── E2E: Plan Activation Detection ───────────────────────────────────────────


class TestPlanActivationE2E:
    def test_plan_trigger_detects_complex_request(self):
        """PlanActivationHook correctly identifies a request needing a plan."""
        hook = PlanActivationHook()

        # Multi-step pattern
        req = ChatRequest(
            message="First analyze the data, then implement the strategy, and finally backtest",
            user_id="user1",
            session_id="s1",
        )
        assert hook.should_create_plan(req) is True

        # Simple request
        req_simple = ChatRequest(
            message="What is the price of BTC?",
            user_id="user1",
            session_id="s2",
        )
        assert hook.should_create_plan(req_simple) is False

    def test_plan_trigger_metadata_workflow(self):
        """PlanActivationHook detects workflow_type in metadata."""
        hook = PlanActivationHook()
        req = ChatRequest(
            message="Run the strategy",
            user_id="user1",
            session_id="s3",
            metadata={"workflow_type": "backtest"},
        )
        assert hook.should_create_plan(req) is True


# ── E2E: Plan Tools Integration ──────────────────────────────────────────────


class TestPlanToolsE2E:
    @pytest.mark.asyncio
    async def test_create_and_execute_plan_via_tools(self, tmp_path):
        """Use create_plan and execute_plan tools in sequence."""
        store = _make_plan_store(tmp_path)
        pool = _make_mock_pool({"orchestrator": "Step done"})
        engine = PlanExecutionEngine(pool, store)
        tools = get_plan_tools(engine)
        tool_map = {t.name: t for t in tools}

        # 1. Create plan
        create_result = await tool_map["create_plan"].handler({
            "title": "E2E Test Plan",
            "objective": "Verify full tool flow",
            "steps": [
                {"id": "t1", "title": "Step 1", "description": "Do first thing",
                 "step_type": "analysis"},
                {"id": "t2", "title": "Step 2", "description": "Do second thing",
                 "step_type": "decision", "depends_on": ["t1"]},
            ],
        })
        assert "E2E Test Plan" in create_result

        # Verify plan was persisted (list_all returns plan IDs as strings)
        plan_ids = store.list_all()
        assert len(plan_ids) == 1
        plan_id = plan_ids[0]

        # 2. Execute plan
        exec_result = await tool_map["execute_plan"].handler({
            "plan_id": plan_id,
        })
        assert "completed" in exec_result.lower() or "COMPLETED" in exec_result
