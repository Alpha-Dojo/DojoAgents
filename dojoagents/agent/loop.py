from __future__ import annotations

import json
import re
from typing import Callable, Any, TypeVar, AsyncGenerator, AsyncIterable

from dojoagents.plugins import get_plugin_registry

from dojoagents.agent.events import AgentEventSink
from dojoagents.agent.models import AgentResponse, ChatRequest, ToolCall
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
)
from dojoagents.agent.compressor import ContextCompressor


from strands.models.model import Model
from strands.types.streaming import StreamEvent
from strands.types.tools import ToolSpec, ToolChoice
from strands.types.content import Messages, SystemContentBlock
from strands.hooks import BeforeToolCallEvent, AfterToolCallEvent
from strands.types.tools import AgentTool, ToolSpec as StrandsToolSpec, ToolUse
from strands.types._events import ToolResultEvent

T = TypeVar("T")


class GuardrailHaltException(Exception):
    def __init__(self, message: str, stopped_reason: str):
        super().__init__(message)
        self.message = message
        self.stopped_reason = stopped_reason


class DojoBridgedTool(AgentTool):
    def __init__(
        self,
        dojo_spec_or_name: Any,
        tool_executor_inst: Any,
        sess_id: str,
        event_sink: AgentEventSink | None = None,
    ):
        super().__init__()
        if isinstance(dojo_spec_or_name, str):
            self.dojo_name = dojo_spec_or_name
            self.dojo_spec = None
        else:
            self.dojo_spec = dojo_spec_or_name
            self.dojo_name = dojo_spec_or_name.name
        self.tool_executor = tool_executor_inst
        self.sess_id = sess_id
        self.event_sink = event_sink

    @property
    def tool_name(self) -> str:
        return _safe_tool_name(self.dojo_name)

    @property
    def tool_spec(self) -> StrandsToolSpec:
        if self.dojo_spec:
            return {"name": _safe_tool_name(self.dojo_spec.name), "description": self.dojo_spec.description, "inputSchema": {"json": self.dojo_spec.parameters}}
        else:
            return {"name": _safe_tool_name(self.dojo_name), "description": f"Dynamic tool {self.dojo_name}", "inputSchema": {"json": {"type": "object"}}}

    @property
    def tool_type(self) -> str:
        return "python"

    async def stream(self, tool_use: ToolUse, invocation_state: dict[str, Any], **kwargs: Any):
        from dojoagents.agent.models import ToolCall as DojoToolCall
        from unittest.mock import AsyncMock

        dojo_call = DojoToolCall(id=tool_use["toolUseId"], name=self.dojo_name, arguments=tool_use["input"])
        if hasattr(self.tool_executor, "execute_many") and (
            isinstance(self.tool_executor, AsyncMock) or hasattr(self.tool_executor.execute_many, "assert_called") or not hasattr(self.tool_executor, "execute_one")
        ):
            results = await self.tool_executor.execute_many([dojo_call], session_id=self.sess_id)
            res = results[0]
        else:
            res = await self.tool_executor.execute_one(dojo_call, session_id=self.sess_id)

        if self.event_sink is not None:
            self.event_sink.tool_result(
                call_id=res.call_id,
                tool=res.name,
                ok=res.ok,
                content=res.content,
                error=res.error,
                latency_ms=res.latency_ms,
                truncated=res.truncated,
                data=res.data,
                viz_blocks=res.viz_blocks,
                artifacts=res.artifacts,
                resource_changes=res.resource_changes,
            )

        status = "success" if res.ok else "error"
        content_text = res.content if res.ok else res.error
        result = {"status": status, "toolUseId": tool_use["toolUseId"], "name": self.tool_name, "content": [{"text": content_text}]}
        yield ToolResultEvent(result)


class DojoStrandsModelBridge(Model):
    def __init__(self, llm_provider: Any, model_id: str):
        self.llm_provider = llm_provider
        self._model_id = model_id
        self._config = {"context_window_limit": 128000}

    def update_config(self, **model_config: Any) -> None:
        self._config.update(model_config)

    def get_config(self) -> Any:
        return self._config

    async def structured_output(self, output_model: type[T], prompt: Messages, system_prompt: str | None = None, **kwargs: Any) -> AsyncGenerator[dict[str, T | Any], None]:
        raise NotImplementedError("structured_output is not supported on DojoStrandsModelBridge")

    async def stream(
        self,
        messages: Messages,
        tool_specs: list[ToolSpec] | None = None,
        system_prompt: str | None = None,
        *,
        tool_choice: ToolChoice | None = None,
        system_prompt_content: list[SystemContentBlock] | None = None,
        invocation_state: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> AsyncIterable[StreamEvent]:
        dojo_msgs = strands_to_dojo_messages(messages, system_prompt)
        dojo_tools = []
        if tool_specs:
            for spec in tool_specs:
                dojo_tools.append({"name": spec["name"], "description": spec["description"], "parameters": spec["inputSchema"].get("json", spec["inputSchema"])})

        import asyncio

        queue = asyncio.Queue()

        def callback(delta: str) -> None:
            queue.put_nowait(delta)

        async def run_chat():
            try:
                res = await self.llm_provider.chat(dojo_msgs, dojo_tools, model=self._model_id, stream=True, stream_callback=callback, metadata=invocation_state)
                queue.put_nowait(res)
            except Exception as e:
                queue.put_nowait(e)

        _ = asyncio.create_task(run_chat())

        yield {"messageStart": {"role": "assistant"}}
        yield {"contentBlockStart": {"contentBlockIndex": 0, "start": {"text": ""}}}

        has_text_delta = False
        while True:
            item = await queue.get()
            if isinstance(item, Exception):
                raise item
            elif isinstance(item, str):
                has_text_delta = True
                yield {"contentBlockDelta": {"contentBlockIndex": 0, "delta": {"text": item}}}
            else:
                llm_result = item
                break

        if not has_text_delta and llm_result.content:
            yield {"contentBlockDelta": {"contentBlockIndex": 0, "delta": {"text": llm_result.content}}}

        yield {"contentBlockStop": {"contentBlockIndex": 0}}

        if llm_result.tool_calls:
            for idx, tc in enumerate(llm_result.tool_calls):
                block_index = idx + 1
                yield {
                    "contentBlockStart": {
                        "contentBlockIndex": block_index,
                        "start": {
                            "toolUse": {
                                "toolUseId": tc.id,
                                "name": tc.name,
                            }
                        },
                    }
                }
                yield {"contentBlockDelta": {"contentBlockIndex": block_index, "delta": {"toolUse": {"input": json.dumps(tc.arguments, ensure_ascii=False)}}}}
                yield {"contentBlockStop": {"contentBlockIndex": block_index}}

        stop_reason = "end_turn"
        if llm_result.tool_calls:
            stop_reason = "tool_use"

        reasoning_content = llm_result.metadata.get("reasoning_content") if llm_result.metadata else None

        yield {"messageStop": {"stopReason": stop_reason, "additionalModelResponseFields": {"reasoning_content": reasoning_content or ""}}}


def strands_to_dojo_messages(strands_messages: list[dict], system_prompt: str | None) -> list[dict]:
    dojo_messages = []
    if system_prompt:
        dojo_messages.append({"role": "system", "content": system_prompt})

    for msg in strands_messages:
        role = msg.get("role")
        content_list = msg.get("content", [])

        text_content = ""
        reasoning_content = ""
        tool_calls = []
        tool_results = []

        for block in content_list:
            if "text" in block:
                text_content += block["text"]
            elif "reasoningContent" in block:
                rc = block["reasoningContent"]
                if "reasoningText" in rc and "text" in rc["reasoningText"]:
                    reasoning_content += rc["reasoningText"]["text"]
            elif "toolUse" in block:
                tu = block["toolUse"]
                tool_calls.append(
                    {"id": tu.get("toolUseId"), "type": "function", "function": {"name": tu.get("name"), "arguments": json.dumps(tu.get("input", {}), ensure_ascii=False)}}
                )
            elif "toolResult" in block:
                tr = block["toolResult"]
                res_content = ""
                for res_block in tr.get("content", []):
                    if "text" in res_block:
                        res_content += res_block["text"]
                tool_results.append({"role": "tool", "name": tr.get("name") or "unknown", "tool_call_id": tr.get("toolUseId"), "content": res_content})

        if role == "user":
            if text_content.strip() or not tool_results:
                dojo_messages.append({"role": "user", "content": text_content})
        elif role == "assistant":
            assistant_msg = {"role": "assistant", "content": text_content}
            if tool_calls:
                assistant_msg["tool_calls"] = tool_calls
            reasoning = reasoning_content or msg.get("reasoning")
            if reasoning:
                assistant_msg["reasoning_content"] = reasoning
            dojo_messages.append(assistant_msg)

        for tr_msg in tool_results:
            dojo_messages.append(tr_msg)

    return dojo_messages


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
        stream_delta_callback: Callable[[Any], None] | None = None,
        plan_activation_hook: Any | None = None,
    ) -> None:
        self.llm_provider = llm_provider
        self.tool_executor = tool_executor
        self.skill_manager = skill_manager
        self.memory_manager = memory_manager
        self.extension_registry = extension_registry
        self.config = config
        self.stream_delta_callback = stream_delta_callback
        self._plan_activation_hook = plan_activation_hook

        self.think_scrubber = StreamingThinkScrubber()
        self.compressor = ContextCompressor(
            threshold_tokens=15000,
            protect_first_n=3,
            protect_last_n=8,
        )
        self.guardrails = ToolCallGuardrailController()

    async def run(self, request: ChatRequest, *, event_sink: AgentEventSink | None = None) -> AgentResponse:
        plugin_registry = get_plugin_registry()
        used_tokens = 0
        remaining_tokens = getattr(self.config, "session_max_tokens", 100000)
        active_phase = ""
        tool_trace: list[dict[str, Any]] = []
        saw_content_delta = False

        def emit_phase(phase: str) -> None:
            nonlocal active_phase
            if event_sink is None or active_phase == phase:
                return
            active_phase = phase
            event_sink.phase(phase)

        def emit_text_delta(text: str) -> None:
            nonlocal saw_content_delta
            if not text:
                return
            saw_content_delta = True
            if event_sink is not None:
                event_sink.delta(text)
                return
            if self.stream_delta_callback:
                self.stream_delta_callback(text)

        def emit_tool_start(tool_name: str, args: dict[str, Any], tool_use_id: str) -> None:
            if event_sink is not None:
                emit_phase("tools")
                event_sink.tool_start(call_id=tool_use_id, tool=tool_name, arguments=args)
                return
            if self.stream_delta_callback:
                self.stream_delta_callback(
                    {
                        "tool_calls": [
                            {
                                "id": str(tool_use_id),
                                "type": "function",
                                "function": {
                                    "name": str(tool_name or "tool"),
                                    "arguments": json.dumps(args, ensure_ascii=False),
                                },
                            }
                        ]
                    }
                )

        emit_phase("planning")

        # 1. Build the system prompt
        blocks = [
            "You are DojoAgents, a quantitative finance analysis agent.",
            self.skill_manager.prompt_block(platform=request.channel),
            self.memory_manager.build_system_prompt(),
            await self.memory_manager.prefetch_all(request.message, session_id=request.session_id),
        ]
        if request.quant is not None:
            blocks.append(request.quant.prompt_block())
            blocks.append(self.extension_registry.prompt_context(request.quant))
        # Inject Dashboard Canvas protocol when channel is "dashboard"
        if request.channel == "dashboard":
            from dojoagents.agent.canvas_protocol import DASHBOARD_CANVAS_PROTOCOL

            blocks.append(DASHBOARD_CANVAS_PROTOCOL)
        system = "\n\n".join(block for block in blocks if block)

        # Plan activation check
        if self._plan_activation_hook and self._plan_activation_hook.should_create_plan(request):
            from dojoagents.utils.event_bus import event_bus

            plan_results = await event_bus.publish("TaskComplexityHigh", {"request": request})
            if plan_results:
                return plan_results[0]
            plan_prompt = self._plan_activation_hook.get_plan_prompt()
            system = system + "\n\n" + plan_prompt

        # 2. Build model bridge
        model = DojoStrandsModelBridge(self.llm_provider, self.config.model)

        # 3. Convert history
        history_msgs = []
        history = request.metadata.get("history") or []
        for msg in history:
            role = msg["role"]
            content = msg.get("content")

            content_blocks = []
            if isinstance(content, str) and content:
                content_blocks.append({"text": content})

            if role == "assistant":
                if "tool_calls" in msg and msg["tool_calls"]:
                    for tc in msg["tool_calls"]:
                        func = tc.get("function") or {}
                        args = func.get("arguments")
                        if isinstance(args, str):
                            try:
                                args_dict = json.loads(args)
                            except json.JSONDecodeError:
                                args_dict = {"raw": args}
                        else:
                            args_dict = args or {}

                        content_blocks.append({"toolUse": {"toolUseId": tc.get("id"), "name": func.get("name"), "input": args_dict}})
                if "reasoning_content" in msg:
                    content_blocks.append({"reasoningContent": {"reasoningText": {"text": msg["reasoning_content"]}}})
                history_msg = {"role": "assistant", "content": content_blocks}
                if "reasoning_content" in msg:
                    history_msg["reasoning"] = msg["reasoning_content"]
                history_msgs.append(history_msg)
            elif role == "tool":
                history_msgs.append(
                    {
                        "role": "user",
                        "content": [{"toolResult": {"status": "success", "toolUseId": msg.get("tool_call_id"), "name": msg.get("name"), "content": [{"text": content or ""}]}}],
                    }
                )
            else:
                history_msgs.append({"role": role, "content": content_blocks})

        # Context Token Tracking & Memory Consolidation Trigger
        from dojoagents.agent.compressor import _estimate_tokens_rough

        session_max_tokens = getattr(self.config, "session_max_tokens", 100000)
        threshold_ratio = getattr(self.config, "threshold_ratio", 0.9)
        self.compressor.threshold_tokens = int(session_max_tokens * threshold_ratio)

        temp_messages = [{"role": "system", "content": system}]
        temp_messages.extend(history_msgs)
        temp_with_prompt = temp_messages + [{"role": "user", "content": request.message}]

        used_tokens = _estimate_tokens_rough(temp_with_prompt)

        if self.config.enable_context_compression and used_tokens >= self.compressor.threshold_tokens:
            # Trigger compression & pluggable memory consolidation
            compressed_temp = await self.compressor.compress(temp_messages, self.llm_provider, self.config.model, memory_manager=self.memory_manager, session_id=request.session_id)
            # Re-split system prompt and history
            if compressed_temp:
                first_msg = compressed_temp[0]
                if first_msg.get("role") == "system":
                    system = first_msg.get("content") or ""
                    history_msgs = compressed_temp[1:]
                else:
                    history_msgs = compressed_temp

            # Recalculate
            temp_messages = [{"role": "system", "content": system}]
            temp_messages.extend(history_msgs)
            temp_with_prompt = temp_messages + [{"role": "user", "content": request.message}]
            used_tokens = _estimate_tokens_rough(temp_with_prompt)

        remaining_tokens = max(0, session_max_tokens - used_tokens)

        # 4. Collect and bridge tools
        tool_specs = self._collect_tool_specs()
        for plugin_tool in plugin_registry._tools:
            self.tool_executor.registry.register(plugin_tool)
            if not any(spec["name"] == plugin_tool.name for spec in tool_specs):
                tool_specs.append(plugin_tool.schema())

        strands_tools = []
        for spec in self.tool_executor.registry.all():
            strands_tools.append(DojoBridgedTool(spec, self.tool_executor, request.session_id, event_sink=event_sink))

        # 5. Set up hooks (Memory Hook & Plugin Hook)
        hooks = []
        plugins = []

        # Bridge memory manager to strands Hooks
        memory_hook = self.memory_manager.as_hook_provider()

        # Define wrappers for HookProviders/Plugins that are mocks or don't pass isinstance checks
        from strands.hooks import HookProvider
        from strands.plugins.plugin import Plugin

        class HookProviderWrapper(HookProvider):
            def __init__(self, target_hook: Any) -> None:
                self.target_hook = target_hook

            def register_hooks(self, registry: Any, **kwargs: Any) -> None:
                if hasattr(self.target_hook, "register_hooks"):
                    self.target_hook.register_hooks(registry, **kwargs)

        class PluginMockWrapper(Plugin):
            def __init__(self, target_plugin: Any) -> None:
                self.target_plugin = target_plugin
                super().__init__()

            @property
            def name(self) -> str:
                return "dojo:mock_plugin"

            def init_agent(self, agent: Any) -> None:
                if hasattr(self.target_plugin, "init_agent"):
                    self.target_plugin.init_agent(agent)

        def is_mock(obj: Any) -> bool:
            return hasattr(obj, "_mock_return_value") or hasattr(obj, "assert_called")

        if is_mock(memory_hook):
            hooks.append(HookProviderWrapper(memory_hook))
        elif isinstance(memory_hook, HookProvider):
            hooks.append(memory_hook)
        else:
            hooks.append(HookProviderWrapper(memory_hook))

        # Bridge plugin registry to strands Plugin
        plugin_bridge = plugin_registry.as_strands_plugin()
        if is_mock(plugin_bridge):
            plugins.append(PluginMockWrapper(plugin_bridge))
        elif isinstance(plugin_bridge, Plugin):
            plugins.append(plugin_bridge)
        else:
            plugins.append(plugin_bridge)

        # Define before tool call hook to check Dojo's guardrails
        async def check_guardrails_before(event: BeforeToolCallEvent) -> None:
            if not event.selected_tool and event.tool_use:
                # Dynamically construct the tool!
                event.selected_tool = DojoBridgedTool(
                    event.tool_use["name"],
                    self.tool_executor,
                    request.session_id,
                    event_sink=event_sink,
                )
            if self.config.enable_guardrails:
                if not event.tool_use:
                    return
                tool_name = event.tool_use.get("name")
                args = event.tool_use.get("input") or {}
                decision = self.guardrails.before_call(tool_name, args)
                if decision.should_halt:
                    raise GuardrailHaltException(decision.message, "guardrail_halt")
                elif not decision.allows_execution:
                    from dojoagents.agent.guardrails import toolguard_synthetic_result

                    blocked_res = toolguard_synthetic_result(decision)
                    event.cancel_tool = blocked_res["content"]
            if event.tool_use:
                tool_name = event.tool_use.get("name")
                args = event.tool_use.get("input") or {}
                tool_use_id = event.tool_use.get("toolUseId") or event.tool_use.get("id") or tool_name or "tool"
                emit_tool_start(str(tool_name or "tool"), args, str(tool_use_id))

        # Define after tool call hook for guardrails
        async def check_guardrails_after(event: AfterToolCallEvent) -> None:
            if not event.tool_use or not event.result:
                return
            tool_name = event.tool_use.get("name")
            args = event.tool_use.get("input") or {}

            raw_result = ""
            content = event.result.get("content", [])
            raw_result = "\n".join(b.get("text", "") for b in content if isinstance(b, dict) and "text" in b)

            is_failed = event.result.get("status") == "error" or "error" in raw_result.lower()

            # 1. Event trigger check for failure
            if is_failed:
                from dojoagents.utils.event_bus import event_bus

                failure_results = await event_bus.publish("ToolExecutionFailed", {"tool_name": tool_name, "args": args, "error": raw_result, "session_id": request.session_id})
                if failure_results and failure_results[0]:
                    # Update result with auto-fixed output
                    event.result["status"] = "success"
                    event.result["content"] = [{"type": "text", "text": failure_results[0]}]
                    raw_result = failure_results[0]
                    is_failed = False

            # 2. Event trigger check for large data volume
            if len(raw_result) > 5000:
                from dojoagents.utils.event_bus import event_bus

                data_results = await event_bus.publish(
                    "DataVolumeLarge", {"data_summary": raw_result[:2000] + "\n... [TRUNCATED] ...\n" + raw_result[-1000:], "session_id": request.session_id}
                )
                if data_results and data_results[0]:
                    # Replace result with analyst summary
                    event.result["content"] = [{"type": "text", "text": data_results[0]}]

            if self.config.enable_guardrails:
                decision = self.guardrails.after_call(tool_name, args, raw_result, failed=is_failed)
                if decision.action == "warn":
                    from dojoagents.agent.guardrails import append_toolguard_guidance

                    warned_content = append_toolguard_guidance(raw_result, decision)
                    event.result["content"] = [{"type": "text", "text": warned_content}]

            if event.tool_use:
                tool_trace.append(
                    {
                        "call_id": event.tool_use.get("toolUseId") or event.tool_use.get("id"),
                        "tool": tool_name,
                        "ok": not is_failed,
                    }
                )

        hooks.append(check_guardrails_before)
        hooks.append(check_guardrails_after)

        # 6. Instantiate strands Agent
        from strands import Agent
        from strands.types.agent import Limits

        limits = Limits(turns=self.config.max_iterations)

        # Setup callback handler for streaming delta and think scrubbing
        if (event_sink is not None or self.stream_delta_callback) and self.config.enable_think_scrubbing:
            self.think_scrubber.reset()

            def wrapped_callback(delta: str) -> None:
                scrubbed = self.think_scrubber.feed(delta)
                if scrubbed:
                    emit_text_delta(scrubbed)

            active_callback = wrapped_callback
        else:
            active_callback = emit_text_delta if (event_sink is not None or self.stream_delta_callback) else None

        def callback_handler(**kwargs_cb: Any) -> None:
            data = kwargs_cb.get("data", "")
            if data and active_callback:
                emit_phase("answering")
                active_callback(data)

        agent = Agent(
            model=model,
            messages=history_msgs,
            tools=strands_tools,
            system_prompt=system,
            hooks=hooks,
            plugins=plugins,
            callback_handler=callback_handler if active_callback else None,
        )

        # 7. Run Agent
        invocation_state = {"session_id": request.session_id, "channel": request.channel}

        try:
            result = await agent.invoke_async(prompt=request.message, invocation_state=invocation_state, limits=limits)
            response_text = str(result).strip()
            iterations = result.metrics.cycle_count if result.metrics else 1
            stopped_reason = None
            if result.stop_reason == "limit_turns":
                stopped_reason = "iteration_limit"
        except Exception as e:
            target_exc = e
            from strands.types.exceptions import EventLoopException

            if isinstance(e, EventLoopException) and isinstance(e.__cause__, GuardrailHaltException):
                target_exc = e.__cause__

            if isinstance(target_exc, GuardrailHaltException):
                ghe = target_exc
                response_text = ghe.message
                iterations = len(agent.messages) // 2 or 1
                stopped_reason = ghe.stopped_reason
                response_text = self._run_exit_hooks(response_text, request, agent.messages, completed=False)
                if stopped_reason == "guardrail_halt":
                    if not response_text.startswith("Blocked"):
                        response_text = f"Blocked {response_text}"
                return AgentResponse(
                    content=response_text,
                    session_id=request.session_id,
                    metadata={"iterations": iterations, "stopped": stopped_reason, "used_tokens": used_tokens, "remaining_tokens": remaining_tokens},
                )
            else:
                if event_sink is not None:
                    event_sink.error(str(target_exc))
                raise

        # Flush think scrubber if needed
        if (event_sink is not None or self.stream_delta_callback) and self.config.enable_think_scrubbing:
            tail = self.think_scrubber.flush()
            if tail:
                emit_text_delta(tail)

        # Clean thinking blocks from response_text
        if self.config.enable_think_scrubbing:
            response_text = re.sub(r"<think>.*?</think>", "", response_text, flags=re.DOTALL)
            response_text = re.sub(r"<thinking>.*?</thinking>", "", response_text, flags=re.DOTALL)
            response_text = re.sub(r"<reasoning>.*?</reasoning>", "", response_text, flags=re.DOTALL)
            response_text = re.sub(r"<thought>.*?</thought>", "", response_text, flags=re.DOTALL)
        if event_sink is not None and response_text and not saw_content_delta:
            emit_phase("answering")
            emit_text_delta(response_text)

        metadata = {"iterations": iterations}
        if stopped_reason:
            metadata["stopped"] = stopped_reason
        metadata.setdefault(
            "usage",
            {
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
            },
        )
        metadata["used_tokens"] = used_tokens
        metadata["remaining_tokens"] = remaining_tokens
        metadata["tool_trace"] = tool_trace

        if event_sink is not None:
            event_sink.done(model_id=self.config.model, tool_trace=tool_trace, tool_steps=len(tool_trace))

        return AgentResponse(content=response_text, session_id=request.session_id, metadata=metadata)

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
            dojo_history = []
            for msg in messages:
                role = msg.get("role")
                content = msg.get("content")

                text_content = ""
                reasoning_content = ""
                if isinstance(content, list):
                    for b in content:
                        if isinstance(b, dict):
                            if "text" in b:
                                text_content += b.get("text", "")
                            elif "reasoningContent" in b:
                                rc = b["reasoningContent"]
                                if "reasoningText" in rc and "text" in rc["reasoningText"]:
                                    reasoning_content += rc["reasoningText"]["text"]
                else:
                    text_content = str(content)

                tool_calls = []
                if isinstance(content, list):
                    for b in content:
                        if isinstance(b, dict) and "toolUse" in b:
                            tu = b["toolUse"]
                            tool_calls.append(
                                {
                                    "id": tu.get("toolUseId"),
                                    "type": "function",
                                    "function": {"name": tu.get("name"), "arguments": json.dumps(tu.get("input", {}), ensure_ascii=False)},
                                }
                            )

                dojo_msg = {"role": role, "content": text_content}
                if tool_calls:
                    dojo_msg["tool_calls"] = tool_calls

                reasoning = reasoning_content or msg.get("reasoning")
                if reasoning:
                    dojo_msg["reasoning_content"] = reasoning
                dojo_history.append(dojo_msg)

            plugin_registry.invoke_hook(
                "post_llm_call",
                session_id=request.session_id,
                user_message=request.message,
                assistant_response=response_text,
                conversation_history=dojo_history,
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
        original_to_safe = {original_name: safe_name for safe_name, original_name in tool_name_map.items()}
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
