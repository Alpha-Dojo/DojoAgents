"""Agent pool with lazy creation and tool filtering."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from dojoagents.agent.loop import AgentLoop
from dojoagents.agent.models import AgentResponse, ChatRequest
from dojoagents.multi_agent.models import AgentSpec
from dojoagents.tools.executor import ToolExecutor
from dojoagents.tools.registry import ToolRegistry
from dojoagents.sessions.models import SessionPrincipal


class AgentPool:
    """Manages a pool of specialized worker agent instances."""

    def __init__(self, runtime: Any, principal: SessionPrincipal | None = None) -> None:
        self._runtime = runtime
        self._agents: dict[str, AgentLoop] = {}
        self._specs: dict[str, AgentSpec] = {}
        self._principal = principal

    def register_agent(self, spec: AgentSpec) -> None:
        """Register an agent specification (lazy instantiation)."""
        self._specs[spec.name] = spec

    def get_or_create(self, name: str) -> AgentLoop:
        """Get existing agent or create from spec. Raises KeyError if no spec registered."""
        if name not in self._agents:
            if name not in self._specs:
                raise KeyError(f"No agent spec registered for '{name}'")
            self._agents[name] = self._create_agent(self._specs[name])
        return self._agents[name]

    def _create_agent(self, spec: AgentSpec) -> AgentLoop:
        """Create a new AgentLoop instance with spec overrides."""
        src = self._runtime.agent

        # Clone tool registry and apply filters
        tool_registry: ToolRegistry = src.tool_executor.registry.clone()
        if spec.disallowed_tools:
            for tool_name in spec.disallowed_tools:
                tool_registry.remove(tool_name)

        # Override model if spec specifies one
        agent_config = self._runtime.config.agent
        if spec.model:
            agent_config = replace(agent_config, model=spec.model)

        return AgentLoop(
            llm_provider=src.llm_provider,
            tool_executor=ToolExecutor(tool_registry, src.tool_executor.sandbox),
            skill_manager=src.skill_manager,
            memory_manager=src.memory_manager,
            extension_registry=src.extension_registry,
            config=agent_config,
            task_manager=getattr(src, "task_manager", None),
            harness_runtime=getattr(src, "harness_runtime", None),
            session_service=getattr(src, "session_service", None),
            harness_descriptor=getattr(src, "harness_descriptor", None),
        )

    async def invoke(self, name: str, request: ChatRequest) -> AgentResponse:
        """Invoke a specific agent by name."""
        agent = self.get_or_create(name)
        if self._principal is not None:
            request = replace(
                request,
                principal=self._principal,
                user_id=self._principal.user_id,
            )
        return await agent.run(request)
