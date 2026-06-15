"""Multi-agent orchestration for DojoAgents."""

from dojoagents.multi_agent.models import (
    AgentMessage,
    AgentRole,
    AgentSpec,
    SubTask,
    TaskStatus,
)
from dojoagents.multi_agent.orchestrator import Orchestrator
from dojoagents.multi_agent.pool import AgentPool
from dojoagents.multi_agent.tools import get_delegation_tool_spec
from dojoagents.multi_agent.triggers import MultiAgentTriggerHook

__all__ = [
    "AgentMessage",
    "AgentPool",
    "AgentRole",
    "AgentSpec",
    "MultiAgentTriggerHook",
    "Orchestrator",
    "SubTask",
    "TaskStatus",
    "get_delegation_tool_spec",
]
