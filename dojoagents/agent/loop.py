from __future__ import annotations

from typing import Callable

from dojoagents.agent.models import AgentResponse, ChatRequest
from dojoagents.agent.providers import LLMProvider
from dojoagents.config.models import AgentConfig
from dojoagents.dojo_extensions.registry import DojoExtensionRegistry
from dojoagents.memory.manager import MemoryManager
from dojoagents.skills.manager import SkillManager
from dojoagents.tools.executor import ToolExecutor


class AgentLoop:
    def __init__(
        self,
        *,
        llm_provider: LLMProvider,
        tool_executor: ToolExecutor,
        skill_manager: SkillManager,
        memory_manager: MemoryManager,
        extension_registry: DojoExtensionRegistry,
        config: AgentConfig,
        stream_delta_callback: Callable[[str], None] | None = None,
    ) -> None:
        self.llm_provider = llm_provider
        self.tool_executor = tool_executor
        self.skill_manager = skill_manager
        self.memory_manager = memory_manager
        self.extension_registry = extension_registry
        self.config = config
        self.stream_delta_callback = stream_delta_callback

    async def run(self, request: ChatRequest) -> AgentResponse:
        messages = await self._build_messages(request)
        tool_specs = self._collect_tool_specs()

        for iteration in range(self.config.max_iterations):
            llm_result = await self.llm_provider.chat(
                messages,
                tool_specs,
                model=self.config.model,
                stream=bool(self.stream_delta_callback),
                stream_callback=self.stream_delta_callback,
                metadata={"session_id": request.session_id, "channel": request.channel},
            )
            if not llm_result.tool_calls:
                await self.memory_manager.sync_turn(
                    request.message,
                    llm_result.content,
                    session_id=request.session_id,
                )
                return AgentResponse(
                    content=llm_result.content,
                    session_id=request.session_id,
                    metadata={"iterations": iteration + 1},
                )

            messages.append(
                {
                    "role": "assistant",
                    "content": llm_result.content,
                    "tool_calls": [
                        {
                            "id": call.id,
                            "type": "function",
                            "function": {
                                "name": call.name,
                                "arguments": call.arguments,
                            },
                        }
                        for call in llm_result.tool_calls
                    ],
                }
            )
            tool_results = await self.tool_executor.execute_many(
                llm_result.tool_calls,
                session_id=request.session_id,
            )
            messages.extend(tool_results.to_messages())

        return AgentResponse(
            content="Agent stopped after reaching the iteration limit.",
            session_id=request.session_id,
            metadata={"stopped": "iteration_limit"},
        )

    async def _build_messages(self, request: ChatRequest) -> list[dict]:
        blocks = [
            "You are DojoAgents, a quantitative finance analysis agent.",
            self.skill_manager.prompt_block(),
            self.memory_manager.build_system_prompt(),
            await self.memory_manager.prefetch_all(
                request.message, session_id=request.session_id
            ),
        ]
        if request.quant is not None:
            blocks.append(request.quant.prompt_block())
            blocks.append(self.extension_registry.prompt_context(request.quant))
        system = "\n\n".join(block for block in blocks if block)
        messages = [{"role": "system", "content": system}]
        history = request.metadata.get("history") or []
        for msg in history:
            messages.append({"role": msg["role"], "content": msg["content"]})
        messages.append({"role": "user", "content": request.message})
        return messages

    def _collect_tool_specs(self) -> list[dict]:
        return self.tool_executor.registry.schema_list()
