"""Plan management tools exposed to the LLM."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from dojoagents.planning.engine import PlanExecutionEngine
from dojoagents.planning.models import Plan, PlanStep, PlanStatus, StepType
from dojoagents.tools.registry import ToolSpec


def get_plan_tools(engine: PlanExecutionEngine) -> list[ToolSpec]:
    """Tools that let the agent create and manage plans."""

    async def create_plan_handler(args: dict) -> str:
        title: str = args["title"]
        objective: str = args["objective"]
        raw_steps: list[dict] = args.get("steps", [])
        steps = []
        for s in raw_steps:
            step_type = s.get("step_type", "analysis")
            if isinstance(step_type, str):
                step_type = StepType(step_type)
            steps.append(
                PlanStep(
                    id=s.get("id", uuid4().hex[:6]),
                    title=s["title"],
                    description=s["description"],
                    step_type=step_type,
                    depends_on=s.get("depends_on", []),
                    assigned_agent=s.get("assigned_agent", "orchestrator"),
                )
            )
        plan = Plan(
            id=uuid4().hex[:8],
            title=title,
            objective=objective,
            steps=steps,
        )
        engine._store.save(plan)
        return f"Plan '{title}' created with {len(steps)} steps. ID: {plan.id}"

    async def execute_plan_handler(args: dict) -> str:
        plan_id: str = args["plan_id"]
        session_id: str = str(args.get("session_id") or f"plan-{plan_id}")
        plan = engine._store.get(plan_id)
        result = await engine.execute_plan(plan, session_id=session_id)
        step_summary = "\n".join(f"  - {s.title}: {s.status}" for s in result.steps)
        return f"Plan '{plan.title}' execution {result.status.value}.\n{step_summary}"

    async def revise_plan_handler(args: dict) -> str:
        plan_id: str = args["plan_id"]
        revision: str = args.get("revision", "")
        plan = engine._store.get(plan_id)
        plan.revision_history.append(
            {
                "reason": revision,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )
        plan.status = PlanStatus.REVISED
        engine._store.save(plan)
        return f"Plan '{plan.title}' marked for revision: {revision}"

    return [
        ToolSpec(
            name="create_plan",
            description="Create a structured execution plan for a complex task",
            parameters={
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Plan title"},
                    "objective": {"type": "string", "description": "What the plan aims to achieve"},
                    "steps": {
                        "type": "array",
                        "description": "List of plan steps",
                        "items": {
                            "type": "object",
                            "properties": {
                                "id": {"type": "string"},
                                "title": {"type": "string"},
                                "description": {"type": "string"},
                                "step_type": {"type": "string", "enum": [t.value for t in StepType]},
                                "depends_on": {"type": "array", "items": {"type": "string"}},
                                "assigned_agent": {"type": "string"},
                            },
                            "required": ["title", "description", "step_type"],
                        },
                    },
                },
                "required": ["title", "objective", "steps"],
            },
            handler=create_plan_handler,
        ),
        ToolSpec(
            name="execute_plan",
            description="Execute an approved plan step-by-step",
            parameters={
                "type": "object",
                "properties": {
                    "plan_id": {"type": "string", "description": "ID of the plan to execute"},
                    "session_id": {"type": "string", "description": "Session context"},
                },
                "required": ["plan_id"],
            },
            handler=execute_plan_handler,
        ),
        ToolSpec(
            name="revise_plan",
            description="Revise an existing plan based on new information",
            parameters={
                "type": "object",
                "properties": {
                    "plan_id": {"type": "string", "description": "ID of the plan to revise"},
                    "revision": {"type": "string", "description": "Reason for revision"},
                },
                "required": ["plan_id", "revision"],
            },
            handler=revise_plan_handler,
        ),
    ]
