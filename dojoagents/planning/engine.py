"""Plan execution engine — step-by-step plan execution with dependency resolution."""

from __future__ import annotations

from typing import Any

from dojoagents.agent.models import AgentResponse, ChatRequest
from dojoagents.planning.models import Plan, PlanStep, PlanStatus, StepType
from dojoagents.planning.store import PlanStateStore


class PlanExecutionEngine:
    """Executes a plan step-by-step, coordinating with the agent pool."""

    def __init__(self, pool: Any, plan_store: PlanStateStore) -> None:
        self._pool = pool
        self._store = plan_store

    async def execute_plan(self, plan: Plan, session_id: str) -> Plan:
        """Execute plan steps respecting dependencies."""
        plan.status = PlanStatus.EXECUTING
        self._store.save(plan)

        max_iterations = len(plan.steps) * 2 + 1  # deadlock guard
        iteration = 0

        while not plan.is_complete():
            iteration += 1
            if iteration > max_iterations:
                plan.status = PlanStatus.FAILED
                break

            actionable = plan.next_actionable_steps()
            if not actionable:
                plan.status = PlanStatus.FAILED
                break

            for step in actionable:
                step.status = "in_progress"
                try:
                    result = await self._execute_step(step, plan, session_id)
                    step.result = result
                    step.status = "completed"
                except Exception as e:
                    step.result = str(e)
                    step.status = "failed"
                    plan.status = PlanStatus.FAILED
                    self._store.save(plan)
                    return plan

            self._store.save(plan)

        if plan.is_complete():
            plan.status = PlanStatus.COMPLETED
        self._store.save(plan)
        return plan

    async def _execute_step(self, step: PlanStep, plan: Plan, session_id: str) -> str:
        """Execute a single plan step."""
        # Build context from completed dependencies
        dep_results = {
            s.id: s.result
            for s in plan.steps
            if s.id in step.depends_on and s.status == "completed"
        }

        context = f"Plan: {plan.title}\nObjective: {plan.objective}\n"
        if dep_results:
            context += f"Prior results: {dep_results}\n"

        if step.step_type == StepType.DELEGATION:
            request = ChatRequest(
                message=f"{context}\n\nTask: {step.description}",
                user_id="plan_engine",
                session_id=f"plan-{plan.id}-{step.id}",
                channel="internal",
            )
            response: AgentResponse = await self._pool.invoke(step.assigned_agent, request)
            return response.content
        else:
            # Orchestrator handles analysis/decision/validation steps
            if self._pool is not None:
                request = ChatRequest(
                    message=f"{context}\n\nExecute step: {step.title}\n{step.description}",
                    user_id="plan_engine",
                    session_id=session_id,
                    channel="internal",
                )
                response = await self._pool.invoke("orchestrator", request)
                return response.content
            return f"Step '{step.title}' acknowledged (no pool available)"
