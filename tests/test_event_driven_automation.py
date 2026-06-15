import pytest
from unittest.mock import AsyncMock, MagicMock

from dojoagents.agent.models import AgentResponse, ChatRequest, LLMResult
from dojoagents.multi_agent.automation import MultiAgentAutoDispatcher
from dojoagents.multi_agent.pool import AgentPool
from dojoagents.planning.automation import AutoPlanManager
from dojoagents.planning.engine import PlanExecutionEngine
from dojoagents.planning.models import PlanStatus, PlanStep, Plan, StepType
from dojoagents.planning.store import PlanStateStore
from dojoagents.utils.event_bus import event_bus


@pytest.mark.asyncio
async def test_event_bus():
    called = []

    async def handler(payload):
        called.append(payload["data"])
        return "result"

    event_bus.subscribe("test_event", handler)
    results = await event_bus.publish("test_event", {"data": "hello"})
    assert called == ["hello"]
    assert results == ["result"]


@pytest.mark.asyncio
async def test_auto_plan_manager_handle_complex_task(tmp_path):
    llm = MagicMock()
    plan_json = """
    {
      "title": "E2E Auto Plan",
      "objective": "Objective description",
      "steps": [
        {
          "id": "s1",
          "title": "Step 1",
          "description": "Do something",
          "step_type": "analysis",
          "depends_on": [],
          "assigned_agent": "orchestrator"
        }
      ]
    }
    """
    synthesis_json = "Synthesized response content"

    chat_calls = []

    async def mock_chat(messages, tools, model):
        chat_calls.append(messages)
        if "plan generator" in messages[0]["content"]:
            return LLMResult(content=plan_json)
        else:
            return LLMResult(content=synthesis_json)

    llm.chat = AsyncMock(side_effect=mock_chat)

    store = PlanStateStore(str(tmp_path / "plans"))
    pool = MagicMock(spec=AgentPool)
    engine = PlanExecutionEngine(pool, store)

    async def mock_invoke(name, request):
        return AgentResponse(content="Step result output", session_id=request.session_id)

    pool.invoke = AsyncMock(side_effect=mock_invoke)

    manager = AutoPlanManager(llm, "gpt-4", engine)

    request = ChatRequest(
        message="Perform a complex market analysis first, and then optimize strategy",
        user_id="user-123",
        session_id="session-xyz",
    )

    plan_created_called = []
    plan_completed_called = []

    async def on_plan_created(payload):
        plan_created_called.append(payload["plan"])

    async def on_plan_completed(payload):
        plan_completed_called.append(payload["plan"])

    event_bus.subscribe("PlanCreated", on_plan_created)
    event_bus.subscribe("PlanCompleted", on_plan_completed)

    results = await event_bus.publish("TaskComplexityHigh", {"request": request})

    assert len(results) == 1
    resp = results[0]
    assert isinstance(resp, AgentResponse)
    assert resp.content == synthesis_json
    assert resp.metadata["auto_plan"] is True

    assert len(plan_created_called) == 1
    assert len(plan_completed_called) == 1
    assert plan_completed_called[0].status == PlanStatus.COMPLETED
    assert plan_completed_called[0].steps[0].result == "Step result output"


@pytest.mark.asyncio
async def test_multi_agent_auto_dispatcher_tool_failure():
    pool = MagicMock(spec=AgentPool)
    reviewer = MagicMock()

    async def mock_run(request):
        return AgentResponse(content="Fixed code execution result", session_id=request.session_id)

    reviewer.run = AsyncMock(side_effect=mock_run)
    pool.get_or_create.return_value = reviewer

    dispatcher = MultiAgentAutoDispatcher(pool)

    payload = {
        "tool_name": "code_execution",
        "args": {"code": "print(1/0)"},
        "error": "ZeroDivisionError: division by zero",
        "session_id": "session-123",
    }

    results = await event_bus.publish("ToolExecutionFailed", payload)

    assert results == ["Fixed code execution result"]
    pool.get_or_create.assert_called_once_with("reviewer")


@pytest.mark.asyncio
async def test_multi_agent_auto_dispatcher_large_data():
    pool = MagicMock(spec=AgentPool)
    analyst = MagicMock()

    async def mock_run(request):
        return AgentResponse(content="Analyst insight report", session_id=request.session_id)

    analyst.run = AsyncMock(side_effect=mock_run)
    pool.get_or_create.return_value = analyst

    dispatcher = MultiAgentAutoDispatcher(pool)

    payload = {
        "data_summary": "10000 rows of stock price data",
        "session_id": "session-123",
    }

    results = await event_bus.publish("DataVolumeLarge", payload)

    assert results == ["Analyst insight report"]
    pool.get_or_create.assert_called_once_with("analyst")
