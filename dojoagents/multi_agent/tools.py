"""Delegation tools for multi-agent orchestration."""

from __future__ import annotations

from uuid import uuid4

from dojoagents.agent.models import ChatRequest
from dojoagents.multi_agent.pool import AgentPool
from dojoagents.tools.registry import ToolSpec


def get_delegation_tool_spec(pool: AgentPool) -> ToolSpec:
    """Tool that lets the orchestrator delegate subtasks to specialist workers."""

    async def delegate_handler(args: dict) -> str:
        agent_role: str = args["agent_role"]
        task_description: str = args["task_description"]
        context: str = args.get("context", "")

        parts = []
        if context:
            parts.append(f"[Context]\n{context}")
        parts.append(f"[Task]\n{task_description}")
        message = "\n\n".join(parts)

        request = ChatRequest(
            message=message,
            user_id="orchestrator",
            session_id=f"sub-{agent_role}-{uuid4().hex[:8]}",
            channel="internal",
        )
        response = await pool.invoke(agent_role, request)
        return response.content

    return ToolSpec(
        name="delegate_task",
        description=(
            "Delegate a subtask to a specialist agent. "
            "Use when the task requires specialized analysis, coding, or review."
        ),
        parameters={
            "type": "object",
            "properties": {
                "agent_role": {
                    "type": "string",
                    "enum": ["analyst", "implementer", "reviewer"],
                    "description": "The specialist agent to delegate to",
                },
                "task_description": {
                    "type": "string",
                    "description": "Clear description of what the agent should accomplish",
                },
                "context": {
                    "type": "string",
                    "description": "Relevant context from prior analysis or plan",
                },
            },
            "required": ["agent_role", "task_description"],
        },
        handler=delegate_handler,
    )
