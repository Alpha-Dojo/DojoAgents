from __future__ import annotations

import json
import re
from uuid import uuid4
from typing import Any

from dojoagents.agent.models import ChatRequest, AgentResponse
from dojoagents.planning.models import Plan, PlanStep, PlanStatus, StepType
from dojoagents.planning.engine import PlanExecutionEngine
from dojoagents.utils.event_bus import event_bus

class AutoPlanManager:
    def __init__(self, llm_provider: Any, model: str, plan_engine: PlanExecutionEngine):
        self.llm = llm_provider
        self.model = model
        self.engine = plan_engine
        event_bus.subscribe("TaskComplexityHigh", self.handle_complex_task)

    async def handle_complex_task(self, payload: dict[str, Any]) -> AgentResponse:
        request: ChatRequest = payload["request"]
        session_id = request.session_id
        
        # 1. Automatically generate the plan via LLM
        plan = await self.generate_plan(request.message)
        
        # Save plan
        self.engine._store.save(plan)
        
        # 2. Publish PlanCreated
        await event_bus.publish("PlanCreated", {"plan": plan, "session_id": session_id})
        
        # 3. Automatically execute the plan
        completed_plan = await self.engine.execute_plan(plan, session_id)
        
        # 4. Publish PlanCompleted
        await event_bus.publish("PlanCompleted", {"plan": completed_plan, "session_id": session_id})
        
        # 5. Synthesize the final response using LLM
        response_text = await self.synthesize_plan_results(request, completed_plan)
        
        return AgentResponse(
            content=response_text,
            session_id=session_id,
            metadata={"iterations": len(completed_plan.steps), "auto_plan": True}
        )

    async def generate_plan(self, user_message: str) -> Plan:
        prompt = (
            "You are a plan generator. Create a structured plan to address the user request. "
            "Break the task down into clear steps with dependencies.\n"
            "Each step must have:\n"
            "- id: a unique short string like 'step_1'\n"
            "- title: a brief title\n"
            "- description: detailed description of what to do\n"
            "- step_type: one of 'analysis', 'implementation', 'validation', 'decision', 'delegation'\n"
            "- depends_on: list of step IDs that must be completed before this step\n"
            "- assigned_agent: the agent role to run this step, one of: 'orchestrator', 'analyst', 'implementer', 'reviewer'\n\n"
            "Respond ONLY with a JSON object of the following format, no other text or explanation:\n"
            "{\n"
            "  \"title\": \"Plan title\",\n"
            "  \"objective\": \"What the plan aims to achieve\",\n"
            "  \"steps\": [\n"
            "    {\n"
            "      \"id\": \"step_1\",\n"
            "      \"title\": \"Step title\",\n"
            "      \"description\": \"Step description\",\n"
            "      \"step_type\": \"analysis\",\n"
            "      \"depends_on\": [],\n"
            "      \"assigned_agent\": \"orchestrator\"\n"
            "    }\n"
            "  ]\n"
            "}"
        )
        
        messages = [
            {"role": "system", "content": prompt},
            {"role": "user", "content": f"User Request: {user_message}"}
        ]
        
        res = await self.llm.chat(messages, tools=[], model=self.model)
        content = res.content.strip()
        
        # Clean markdown wrappers if any
        match = re.search(r"```(?:json)?\s*(.*?)\s*```", content, re.DOTALL)
        if match:
            content = match.group(1)
            
        try:
            data = json.loads(content.strip())
        except Exception:
            # Fallback to a single-step plan if parsing fails
            data = {
                "title": "Auto Execution Plan",
                "objective": "Execute the request",
                "steps": [
                    {
                        "id": "step_1",
                        "title": "Execute Task",
                        "description": user_message,
                        "step_type": "analysis",
                        "depends_on": [],
                        "assigned_agent": "orchestrator"
                    }
                ]
            }
            
        steps = []
        for s in data.get("steps", []):
            stype = s.get("step_type", "analysis")
            steps.append(PlanStep(
                id=s.get("id", uuid4().hex[:6]),
                title=s.get("title", "Plan Step"),
                description=s.get("description", ""),
                step_type=StepType(stype) if stype in [t.value for t in StepType] else StepType.ANALYSIS,
                depends_on=s.get("depends_on", []),
                assigned_agent=s.get("assigned_agent", "orchestrator")
            ))
            
        return Plan(
            id=uuid4().hex[:8],
            title=data.get("title", "Execution Plan"),
            objective=data.get("objective", ""),
            steps=steps
        )

    async def synthesize_plan_results(self, request: ChatRequest, plan: Plan) -> str:
        step_details = []
        for s in plan.steps:
            step_details.append(f"### Step: {s.title} ({s.status})\nDescription: {s.description}\nResult:\n{s.result}\n")
            
        prompt = (
            "You are the main coordinator. A complex plan has just finished executing. "
            "Below is the user's original request, followed by the execution plan and the results of each step. "
            "Provide a comprehensive, final synthesized response to the user. "
            "Combine the findings, code, and conclusions into a single cohesive response. "
            "Do not talk about the plan steps in the response; speak directly to the user addressing their request."
        )
        
        context = f"User Request: {request.message}\n\nPlan Title: {plan.title}\nPlan Objective: {plan.objective}\n\nStep Results:\n" + "\n".join(step_details)
        
        messages = [
            {"role": "system", "content": prompt},
            {"role": "user", "content": context}
        ]
        
        res = await self.llm.chat(messages, tools=[], model=self.model)
        return res.content
