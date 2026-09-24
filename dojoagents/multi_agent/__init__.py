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
from dojoagents.multi_agent.mailbox import AgentAddress, AgentEnvelope, AgentInstance, MessageStore
from dojoagents.multi_agent.team import AgentTeam, get_agent_team_tool_specs

__all__ = [
    "AgentMessage",
    "AgentAddress",
    "AgentEnvelope",
    "AgentInstance",
    "AgentTeam",
    "MessageStore",
    "AgentPool",
    "AgentRole",
    "AgentSpec",
    "MultiAgentTriggerHook",
    "Orchestrator",
    "SubTask",
    "TaskStatus",
    "get_delegation_tool_spec",
    "get_agent_team_tool_specs",
]
