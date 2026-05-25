from __future__ import annotations

import re
from typing import Callable

from dojoagents.agent.models import AgentResponse, ChatRequest, LLMResult, ToolCall
from dojoagents.agent.providers import LLMProvider
from dojoagents.config.models import AgentConfig
from dojoagents.dojo_extensions.registry import DojoExtensionRegistry
from dojoagents.memory.manager import MemoryManager
from dojoagents.skills.manager import SkillManager
from dojoagents.tools.executor import ToolExecutor
from dojoagents.logging import LOGGER


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
        tool_specs, tool_name_map = self._sanitize_tool_specs(tool_specs)

        for iteration in range(self.config.max_iterations):
            try:
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
                tool_calls = self._restore_tool_call_names(
                    llm_result.tool_calls,
                    tool_name_map,
                )
                tool_results = await self.tool_executor.execute_many(
                    tool_calls,
                    session_id=request.session_id,
                )
                messages.extend(
                    self._tool_result_messages_for_llm(
                        tool_results.to_messages(),
                        tool_name_map,
                    )
                )
            except Exception as e:
                LOGGER.exception(f"Error in agent loop: {e}")
                return AgentResponse(
                    content=f"Error in agent loop: {e}",
                    session_id=request.session_id,
                    metadata={"stopped": "error"},
                )

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

    def _sanitize_tool_specs(
        self,
        tool_specs: list[dict],
    ) -> tuple[list[dict], dict[str, str]]:
        safe_specs: list[dict] = []
        safe_to_original: dict[str, str] = {}
        used_names: set[str] = set()
        for spec in tool_specs:
            original_name = str(spec["name"])
            safe_name = _safe_tool_name(original_name)
            if safe_name in used_names:
                suffix = 2
                candidate = f"{safe_name}_{suffix}"
                while candidate in used_names:
                    suffix += 1
                    candidate = f"{safe_name}_{suffix}"
                safe_name = candidate
            used_names.add(safe_name)
            safe_to_original[safe_name] = original_name
            safe_spec = dict(spec)
            safe_spec["name"] = safe_name
            safe_specs.append(safe_spec)
        return safe_specs, safe_to_original

    def _restore_tool_call_names(
        self,
        tool_calls: list[ToolCall],
        tool_name_map: dict[str, str],
    ) -> list[ToolCall]:
        return [
            ToolCall(
                id=call.id,
                name=tool_name_map.get(call.name, call.name),
                arguments=call.arguments,
            )
            for call in tool_calls
        ]

    def _tool_result_messages_for_llm(
        self,
        messages: list[dict],
        tool_name_map: dict[str, str],
    ) -> list[dict]:
        original_to_safe = {
            original_name: safe_name
            for safe_name, original_name in tool_name_map.items()
        }
        safe_messages: list[dict] = []
        for message in messages:
            safe_message = dict(message)
            name = safe_message.get("name")
            if name in original_to_safe:
                safe_message["name"] = original_to_safe[name]
            safe_messages.append(safe_message)
        return safe_messages


def _safe_tool_name(name: str) -> str:
    safe_name = re.sub(r"[^a-zA-Z0-9_-]", "_", name)
    safe_name = re.sub(r"_+", "_", safe_name).strip("_")
    return safe_name or "tool"
