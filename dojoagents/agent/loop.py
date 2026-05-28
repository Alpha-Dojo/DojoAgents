from __future__ import annotations

import json
import re
import time
from typing import Callable
from dataclasses import asdict
from dojoagents.plugins import get_plugin_registry

from dojoagents.agent.models import AgentResponse, ChatRequest, LLMResult, ToolCall
from dojoagents.agent.providers import LLMProvider
from dojoagents.config.models import AgentConfig
from dojoagents.dojo_extensions.registry import DojoExtensionRegistry
from dojoagents.memory.manager import MemoryManager
from dojoagents.skills.manager import SkillManager
from dojoagents.tools.executor import ToolExecutor
from dojoagents.logging import LOGGER

from dojoagents.agent.think_scrubber import StreamingThinkScrubber
from dojoagents.agent.guardrails import (
    ToolCallGuardrailController,
    toolguard_synthetic_result,
    append_toolguard_guidance,
)
from dojoagents.agent.compressor import ContextCompressor


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

        self.think_scrubber = StreamingThinkScrubber()
        self.compressor = ContextCompressor(
            threshold_tokens=15000,
            protect_first_n=3,
            protect_last_n=8,
        )
        self.guardrails = ToolCallGuardrailController()

    async def run(self, request: ChatRequest) -> AgentResponse:
        plugin_registry = get_plugin_registry()
        plugin_registry.invoke_hook(
            "on_session_start",
            session_id=request.session_id,
            model=self.config.model,
        )

        messages = await self._build_messages(request)

        # 2. Invoke pre_llm_call hook
        pre_results = plugin_registry.invoke_hook(
            "pre_llm_call",
            session_id=request.session_id,
            user_message=request.message,
        )
        for res in pre_results:
            if isinstance(res, str) and res.strip():
                messages[-1]["content"] += f"\n\n[Plugin Context]\n{res}"

        tool_specs = self._collect_tool_specs()
        for plugin_tool in plugin_registry._tools:
            self.tool_executor.registry.register(plugin_tool)
            if not any(spec["name"] == plugin_tool.name for spec in tool_specs):
                tool_specs.append(plugin_tool.schema())

        tool_specs, tool_name_map = self._sanitize_tool_specs(tool_specs)

        if self.config.enable_guardrails:
            self.guardrails.reset_for_turn()

        for iteration in range(self.config.max_iterations):
            try:
                # 1. Compress context if enabled
                if self.config.enable_context_compression:
                    messages = await self.compressor.compress(
                        messages, self.llm_provider, self.config.model
                    )

                # 2. Setup streaming scrubber if stream callback is provided
                active_callback = None
                if self.stream_delta_callback and self.config.enable_think_scrubbing:
                    self.think_scrubber.reset()
                    def wrapped_callback(delta: str) -> None:
                        scrubbed = self.think_scrubber.feed(delta)
                        if scrubbed and self.stream_delta_callback:
                            self.stream_delta_callback(scrubbed)
                    active_callback = wrapped_callback
                else:
                    active_callback = self.stream_delta_callback

                # 3. Invoke pre_api_request hook
                plugin_registry.invoke_hook(
                    "pre_api_request",
                    session_id=request.session_id,
                    api_call_count=iteration + 1,
                    request_messages=messages,
                )

                llm_result = await self.llm_provider.chat(
                    messages,
                    tool_specs,
                    model=self.config.model,
                    stream=bool(active_callback),
                    stream_callback=active_callback,
                    metadata={"session_id": request.session_id, "channel": request.channel},
                )
                LOGGER.debug(f"LLM Result: {json.dumps(asdict(llm_result), ensure_ascii=False)}")
                # 4. Invoke post_api_request hook
                plugin_registry.invoke_hook(
                    "post_api_request",
                    session_id=request.session_id,
                    api_call_count=iteration + 1,
                    llm_result=llm_result,
                )

                # Flush scrubber at end of stream
                if self.stream_delta_callback and self.config.enable_think_scrubbing:
                    tail = self.think_scrubber.flush()
                    if tail and self.stream_delta_callback:
                        self.stream_delta_callback(tail)

                # Clean thinking blocks from LLMResult content for clean downstream history
                if self.config.enable_think_scrubbing and llm_result.content:
                    llm_result.content = re.sub(r"<think>.*?</think>", "", llm_result.content, flags=re.DOTALL)
                    llm_result.content = re.sub(r"<thinking>.*?</thinking>", "", llm_result.content, flags=re.DOTALL)
                    llm_result.content = re.sub(r"<reasoning>.*?</reasoning>", "", llm_result.content, flags=re.DOTALL)
                    llm_result.content = re.sub(r"<thought>.*?</thought>", "", llm_result.content, flags=re.DOTALL)

                if not llm_result.tool_calls:
                    await self.memory_manager.sync_turn(
                        request.message,
                        llm_result.content,
                        session_id=request.session_id,
                    )
                    response_text = self._run_exit_hooks(
                        llm_result.content or "",
                        request,
                        messages,
                        completed=True,
                    )
                    return AgentResponse(
                        content=response_text,
                        session_id=request.session_id,
                        metadata={"iterations": iteration + 1},
                    )

                tool_calls = self._restore_tool_call_names(
                    llm_result.tool_calls,
                    tool_name_map,
                )

                allowed_tool_calls = []
                blocked_results = []

                for call in tool_calls:
                    block_message = None
                    try:
                        pre_results = plugin_registry.invoke_hook(
                            "pre_tool_call",
                            tool_name=call.name,
                            args=call.arguments,
                            session_id=request.session_id,
                            tool_call_id=call.id,
                        )
                        for res in pre_results:
                            if isinstance(res, dict) and res.get("action") == "block":
                                block_message = res.get("message") or "Blocked by plugin"
                                break
                    except Exception as he:
                        LOGGER.exception(f"Error in pre_tool_call hook: {he}")

                    if block_message:
                        assistant_msg = {
                            "role": "assistant",
                            "content": llm_result.content,
                        }
                        if llm_result.tool_calls:
                            assistant_msg["tool_calls"] = [
                                {
                                    "id": c.id,
                                    "type": "function",
                                    "function": {
                                        "name": c.name,
                                        "arguments": (
                                            json.dumps(c.arguments, ensure_ascii=False)
                                            if isinstance(c.arguments, dict)
                                            else str(c.arguments)
                                        ),
                                    },
                                }
                                for c in llm_result.tool_calls
                            ]
                        reasoning_content = llm_result.metadata.get("reasoning_content") if llm_result.metadata else None
                        if reasoning_content:
                            assistant_msg["reasoning_content"] = reasoning_content
                        messages.append(assistant_msg)

                        messages.append({
                            "role": "tool",
                            "name": call.name,
                            "tool_call_id": call.id,
                            "content": json.dumps({"error": block_message}, ensure_ascii=False),
                        })

                        response_text = self._run_exit_hooks(
                            block_message,
                            request,
                            messages,
                            completed=False,
                        )
                        return AgentResponse(
                            content=response_text,
                            session_id=request.session_id,
                            metadata={"iterations": iteration + 1, "stopped": "plugin_blocked"},
                        )

                    if self.config.enable_guardrails:
                        decision = self.guardrails.before_call(call.name, call.arguments)
                        if decision.should_halt:
                            # Direct halt
                            blocked_res = toolguard_synthetic_result(decision)
                            from dojoagents.agent.models import ToolResult
                            blocked_results.append(ToolResult(
                                call_id=call.id,
                                name=call.name,
                                ok=False,
                                error=decision.message,
                                content=blocked_res["content"],
                                metadata=blocked_res["metadata"]
                            ))
                            # Add assistant response to messages and return
                            assistant_msg = {
                                "role": "assistant",
                                "content": llm_result.content,
                            }
                            if llm_result.tool_calls:
                                assistant_msg["tool_calls"] = [
                                    {
                                        "id": c.id,
                                        "type": "function",
                                        "function": {
                                            "name": c.name,
                                            "arguments": (
                                                json.dumps(c.arguments, ensure_ascii=False)
                                                if isinstance(c.arguments, dict)
                                                else str(c.arguments)
                                            ),
                                        },
                                    }
                                    for c in llm_result.tool_calls
                                ]
                            reasoning_content = llm_result.metadata.get("reasoning_content") if llm_result.metadata else None
                            if reasoning_content:
                                assistant_msg["reasoning_content"] = reasoning_content
                            messages.append(assistant_msg)
                            # Append the blocked error result to messages
                            messages.append({
                                "role": "tool",
                                "name": call.name,
                                "tool_call_id": call.id,
                                "content": blocked_res["content"],
                            })
                            response_text = self._run_exit_hooks(
                                decision.message,
                                request,
                                messages,
                                completed=False,
                            )
                            return AgentResponse(
                                content=response_text,
                                session_id=request.session_id,
                                metadata={"iterations": iteration + 1, "stopped": "guardrail_halt"},
                            )
                        elif not decision.allows_execution:
                            blocked_res = toolguard_synthetic_result(decision)
                            from dojoagents.agent.models import ToolResult
                            blocked_results.append(ToolResult(
                                call_id=call.id,
                                name=call.name,
                                ok=False,
                                error=decision.message,
                                content=blocked_res["content"],
                                metadata=blocked_res["metadata"]
                            ))
                        else:
                            allowed_tool_calls.append(call)
                    else:
                        allowed_tool_calls.append(call)

                # Execute allowed tool calls concurrently
                tool_start_time = time.monotonic()
                tool_results = await self.tool_executor.execute_many(
                    allowed_tool_calls,
                    session_id=request.session_id,
                )
                duration_ms = int((time.monotonic() - tool_start_time) * 1000)

                for res in tool_results:
                    tc = next((c for c in allowed_tool_calls if c.id == res.call_id), None)
                    tc_args = tc.arguments if tc else {}

                    # post_tool_call hook
                    try:
                        plugin_registry.invoke_hook(
                            "post_tool_call",
                            tool_name=res.name,
                            args=tc_args,
                            result=res.content if res.ok else res.error,
                            task_id=request.user_id,
                            session_id=request.session_id,
                            tool_call_id=res.call_id,
                            duration_ms=duration_ms,
                        )
                    except Exception as he:
                        LOGGER.exception(f"Error in post_tool_call hook: {he}")

                    # transform_tool_result hook
                    try:
                        transform_results = plugin_registry.invoke_hook(
                            "transform_tool_result",
                            tool_name=res.name,
                            args=tc_args,
                            result=res.content if res.ok else res.error,
                            task_id=request.user_id,
                            session_id=request.session_id,
                            tool_call_id=res.call_id,
                            duration_ms=duration_ms,
                        )
                        for trans_res in transform_results:
                            if isinstance(trans_res, str):
                                if res.ok:
                                    res.content = trans_res
                                else:
                                    res.error = trans_res
                                break
                    except Exception as he:
                        LOGGER.exception(f"Error in transform_tool_result hook: {he}")

                # Process results through guardrails after execution
                if self.config.enable_guardrails:
                    for res in tool_results:
                        tc = next((c for c in allowed_tool_calls if c.id == res.call_id), None)
                        tc_args = tc.arguments if tc else {}
                        decision = self.guardrails.after_call(
                            res.name,
                            tc_args,
                            res.content,
                            failed=not res.ok or "error" in str(res.content).lower(),
                        )
                        if decision.action == "warn":
                            res.content = append_toolguard_guidance(res.content, decision)

                # Merge blocked and success results maintaining call order
                from dojoagents.agent.models import ToolResultList
                final_results = ToolResultList()
                blocked_map = {r.call_id: r for r in blocked_results}
                success_map = {r.call_id: r for r in tool_results}

                for call in tool_calls:
                    if call.id in blocked_map:
                        final_results.append(blocked_map[call.id])
                    elif call.id in success_map:
                        final_results.append(success_map[call.id])

                assistant_msg = {
                    "role": "assistant",
                    "content": llm_result.content,
                }
                if llm_result.tool_calls:
                    assistant_msg["tool_calls"] = [
                        {
                            "id": call.id,
                            "type": "function",
                            "function": {
                                "name": call.name,
                                "arguments": (
                                    json.dumps(call.arguments, ensure_ascii=False)
                                    if isinstance(call.arguments, dict)
                                    else str(call.arguments)
                                ),
                            },
                        }
                        for call in llm_result.tool_calls
                    ]
                reasoning_content = llm_result.metadata.get("reasoning_content") if llm_result.metadata else None
                if reasoning_content:
                    assistant_msg["reasoning_content"] = reasoning_content
                messages.append(assistant_msg)

                messages.extend(
                    self._tool_result_messages_for_llm(
                        final_results.to_messages(),
                        tool_name_map,
                    )
                )
            except Exception as e:
                LOGGER.exception(f"Error in agent loop: {e}")
                response_text = self._run_exit_hooks(
                    f"Error in agent loop: {e}",
                    request,
                    messages,
                    completed=False,
                )
                return AgentResponse(
                    content=response_text,
                    session_id=request.session_id,
                    metadata={"stopped": "error"},
                )

        response_text = self._run_exit_hooks(
            "Agent stopped after reaching the iteration limit.",
            request,
            messages,
            completed=False,
        )
        return AgentResponse(
            content=response_text,
            session_id=request.session_id,
            metadata={"stopped": "iteration_limit"},
        )

    def _run_exit_hooks(self, response_text: str, request: ChatRequest, messages: list[dict], completed: bool) -> str:
        plugin_registry = get_plugin_registry()
        try:
            transform_results = plugin_registry.invoke_hook(
                "transform_llm_output",
                response_text=response_text,
                session_id=request.session_id,
            )
            for trans in transform_results:
                if isinstance(trans, str):
                    response_text = trans
        except Exception as he:
            LOGGER.exception(f"Error in transform_llm_output hook: {he}")

        try:
            plugin_registry.invoke_hook(
                "post_llm_call",
                session_id=request.session_id,
                user_message=request.message,
                assistant_response=response_text,
                conversation_history=messages,
                model=self.config.model,
                platform=request.channel,
            )
        except Exception as he:
            LOGGER.exception(f"Error in post_llm_call hook: {he}")

        try:
            plugin_registry.invoke_hook(
                "on_session_end",
                session_id=request.session_id,
                completed=completed,
            )
        except Exception as he:
            LOGGER.exception(f"Error in on_session_end hook: {he}")

        return response_text

    async def _build_messages(self, request: ChatRequest) -> list[dict]:
        blocks = [
            "You are DojoAgents, a quantitative finance analysis agent.",
            self.skill_manager.prompt_block(platform=request.channel),
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
            formatted_msg = {
                "role": msg["role"],
                "content": msg.get("content"),
            }
            if msg["role"] == "assistant":
                if "tool_calls" in msg and msg["tool_calls"]:
                    formatted_tool_calls = []
                    for tc in msg["tool_calls"]:
                        func = tc.get("function") or {}
                        args = func.get("arguments")
                        if isinstance(args, dict):
                            args_str = json.dumps(args, ensure_ascii=False)
                        else:
                            args_str = str(args) if args is not None else "{}"
                        
                        formatted_tool_calls.append({
                            "id": tc.get("id"),
                            "type": tc.get("type", "function"),
                            "function": {
                                "name": func.get("name"),
                                "arguments": args_str
                            }
                        })
                    formatted_msg["tool_calls"] = formatted_tool_calls
                if "reasoning_content" in msg and msg["reasoning_content"]:
                    formatted_msg["reasoning_content"] = msg["reasoning_content"]
            elif msg["role"] == "tool":
                formatted_msg["tool_call_id"] = msg.get("tool_call_id")
                formatted_msg["name"] = msg.get("name")
            messages.append(formatted_msg)
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
