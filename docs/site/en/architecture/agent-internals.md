# Agent Internals

> This page answers a question the other docs never addressed head-on: **how is the DojoAgents agent capability actually built?**
>
> [Agent Loop](agent-loop.md) describes the conceptual turn. This page describes what really happens in code: which agent framework is embedded, how it is bridged, how the system prompt is assembled, who intercepts tool calls, how context is compacted, and where domain logic plugs in.
>
> Main entry point: `dojoagents/agent/loop.py`, especially `AgentLoop.run()`. Line numbers on this page are orientation aids for the documented snapshot; symbol names are the stable references.
>
> Evidence boundary: this page describes behavior observable in the current code. It does not claim to reconstruct undocumented framework-selection intent. Confirmed operational gaps are tracked in [Known Limitations](../development/known-limitations.md).

---

## 1. In one sentence

**DojoAgents delegates the inner model-to-tool cycle to [Strands Agents](https://github.com/strands-agents/sdk-python), while `AgentLoop.run()` owns request orchestration, prompt assembly, bridges, hooks, recovery, domain validation and outward events.**

```text
        DojoAgents assets                         Strands Agents kernel
  ┌───────────────────────────┐           ┌────────────────────────┐
  │ LLMProvider (OpenAI-comp.)│──bridge─▶ │ strands.models.Model   │
  │ ToolSpec + ToolExecutor   │──bridge─▶ │ strands.types.AgentTool│
  │ SkillManager / Memory     │──compose▶ │ system_prompt          │
  │ Guardrails / Harness      │──attach─▶ │ hooks (Before/After)   │
  │ Plugins                   │──attach─▶ │ plugins                │
  │ DojoAgentSessionManager   │──inject─▶ │ session_manager        │
  └───────────────────────────┘           └────────────────────────┘
                                                    │
                                          agent.invoke_async(...)
                                          multi-turn tool-use driven by kernel
```

---

## 2. Frameworks in use

| Dependency | Constraint | Role in the agent capability |
| --- | --- | --- |
| `strands-agents` | unpinned | **Agent event-loop kernel**: multi-turn tool-use orchestration, message state machine, hook/plugin system, `stop_reason` / `metrics` |
| `strands-agents-tools` | unpinned | Official Strands tool collection (optional) |
| `openai` | `>=1.20,<2` | SDK behind `OpenAICompatibleProvider`; also used for token accounting and context-window probing |
| `mcp` | `>=1.26,<2` | MCP tool integration (`tools/mcp_tool.py`, `tools/mcp_oauth.py`) |
| `fastapi` | `>=0.110,<0.112` | Exposes the agent through Dashboard / Gateway (SSE, OpenAI-compatible API) |
| `apscheduler` | `>=3.10,<4` | Scheduled jobs that trigger agent runs |
| `dojosdk` | `>=0.1.15` | Quant finance data, wrapped as tools (`tools/dojo_sdk_tool.py`) |

Declared in `pyproject.toml` and `requirements.txt`.

> **Observable integration trade-offs.** The code uses Strands for the model/tool cycle and hook protocol while retaining DojoAgents provider and tool contracts behind adapters. Mutable before/after tool events support cancellation and argument/result rewriting. These are properties of the implementation, not a documented comparison or selection rationale against other frameworks.

---

## 3. Six cross-cutting design ideas

### 3.1 Anti-corruption layer

The main Strands adaptation boundary is concentrated in `agent/loop.py`: `DojoStrandsModelBridge`, `DojoBridgedTool`, message conversion and invocation are implemented there. A small number of adjacent modules also use Strands contracts directly, including session management, empty-assistant recovery and the plugin bridge. Replacing the kernel would therefore require changing this boundary and those integration points, rather than only one bridge block.

Two-way message translation supports this: outbound in `run()` stage 3 (`loop.py:647`), inbound via `strands_to_dojo_messages()` (`loop.py:324`), plus `compressor.flatten_messages_for_compress()` / `messages_to_strands()` around compaction.

### 3.2 Generic loop + domain harness

Domain constraints (a portfolio must exist before backtesting, an evaluation must be submitted, …) are **not** in the loop. They implement the `TaskHarness` protocol and are called back at six fixed points. See [§5.6](#56-harness-pluggable-domain-constraints).

### 3.3 Context economics: progressive disclosure + active compaction

- With `agent.lazy_skills: true` (the default), `SkillManager.prompt_block()` injects names/descriptions and bodies are fetched through `skill_view`. With lazy loading disabled, skill bodies are injected directly.
- Tool results are pruned: `ContextCompressor.prune_old_tool_results()` keeps the tail, degrades older results to summaries (`_summarize_tool_result()`), and truncates argument JSON to 150 chars (`_truncate_tool_call_args_json()`).
- Overflow self-heals: hitting the context limit triggers compaction and one retry ([§5.4](#54-context-and-token-governance)).

### 3.4 Interception-based governance

Governance is deliberately mixed. Guardrails, token compaction, memory integration, turn completion and plugin interception are assembled as hooks/plugins. `AgentLoop.run()` still performs explicit orchestration for harness resolution and repair, recovery attempts, event publication and final response handling. This split matters when extending or replacing the loop.

### 3.5 Every capability is a ToolSpec

Skill management, plugin management, terminal, code execution, session files, MCP, DojoSDK data and even **sub-agent delegation** all collapse into `ToolSpec` entries in `ToolRegistry`. `Runtime` merely decides what goes into the registry at assembly time.

### 3.6 Event bus for decoupled side capabilities

`dojoagents/utils/event_bus.py::EventBus` offers `publish(topic, payload)`. Planning, multi-agent dispatch, tool-failure self-healing and large-result summarisation subscribe to these events. The publishers are explicit calls in `AgentLoop.run()` and its tool hooks, so subscribers are decoupled but publication is still part of loop orchestration.

| Event | Published at | Typical subscriber |
| --- | --- | --- |
| `TaskComplexityHigh` | plan activation check (`loop.py:595` area) | `planning/automation.py::AutoPlanManager` |
| `ToolExecutionFailed` | after-tool hook | self-healing strategies; the returned value can replace the failed result |
| `DataVolumeLarge` | after-tool hook (result > 5000 chars) | analyst sub-agent that replaces the payload with a summary |

---

## 4. Layering

```text
Entry      CLI / Dashboard (FastAPI) / Gateway / Cron
              │  ChatRequest
Assembly   agent/runtime.py::Runtime
           └─ ConfigStore → provider, ToolRegistry, SkillManager,
              MemoryManager, PluginRegistry, AgentPool, harness list
Orchestr.  agent/loop.py::AgentLoop.run()      ← focus of this page
           ├─ bridges: DojoStrandsModelBridge / DojoBridgedTool
           ├─ aspects: guardrails / token compaction / turn completion / memory / plugins
           └─ kernel : strands.Agent.invoke_async()
Execution  tools/executor.py::ToolExecutor → sandbox policy → ToolSpec.handler
Side       event_bus ↔ planning / multi_agent / self-healing
```

---

## 5. Implementation walk-through

### 5.1 The two bridges

**`DojoBridgedTool` (`loop.py:72-146`)** extends `strands.types.tools.AgentTool`. `tool_spec` converts the Dojo JSON schema into a Strands `inputSchema`; `stream()` calls `ToolExecutor` and pushes the resulting `ToolResult` into `invocation_state["_dojo_tool_results"]` (`loop.py:124`) so the after-tool hook can recover `latency_ms`, `truncated`, `viz_blocks`, `artifacts`, `resource_changes`. Strands tool results are plain text, so this side channel is how structured metadata survives; results are matched back by `call_id` (`loop.py:1046-1056`).

**`DojoStrandsModelBridge` (`loop.py:147-323`)** extends `strands.models.model.Model`:

1. translates Strands messages back to OpenAI-style messages (`toolUse` / `toolResult` / `reasoningContent` / image blocks);
2. runs `llm_provider.chat(..., stream=True, stream_callback=...)` in a background task, piping deltas through an `asyncio.Queue`;
3. yields Strands `StreamEvent`s: `messageStart` → `contentBlockStart` → `contentBlockDelta`* → tool/stop blocks;
4. **self-heals on overflow**: catches `ContextLengthExceededError`, calls `_dojo_handle_context_length_exceeded` from `invocation_state` to compact `agent.messages`, then retries once (`_dojo_context_length_retries < 1`, `loop.py:210-235`);
5. records usage into `invocation_state["_dojo_last_usage"]`, falling back to `_estimate_tokens_rough()`.

### 5.2 The seven stages of `run()`

| Stage | Line | What happens |
| --- | --- | --- |
| 1. Build system prompt | `loop.py:544` | see list below |
| 2. Model bridge + token ledger | `loop.py:604` | `DojoStrandsModelBridge`, `SessionTokenLedger`, `ModelContextRegistry` |
| 3. Convert history | `loop.py:647` | Dojo history → Strands content blocks |
| 4. Collect and bridge tools | `loop.py:743` | `_collect_tool_specs()` + plugin tools → `_sanitize_tool_specs()` → `DojoBridgedTool` |
| 5. Assemble hooks | `loop.py:757` | memory, token compaction, turn completion, plugin bridge, guardrails |
| 6. Instantiate Strands Agent | `loop.py:1082` | `Agent(...)` at `loop.py:1134` |
| 7. Run and finalise | `loop.py:1146` | `invoke_async` → empty-turn recovery → harness validation → exit hooks |

System prompt blocks (`loop.py:544-590`, joined with `\n\n`):

```text
1  role definition ("You are DojoAgents, a full-market finance analysis agent.")
2  build_temporal_context_block()          current-time grounding
3  SkillManager.prompt_block(platform)     skill index, filtered by channel
4  MemoryManager.build_system_prompt()
5  MemoryManager.prefetch_all(message)     memories relevant to this turn
6  [quant]     QuantContext.prompt_block() + DojoExtensionRegistry.prompt_context()
7  [dashboard] viz protocol + tool protocol + viz policy catalog + turn anchor
8  [task]      TaskPromptManager.build_injection_block()
9  build_turn_intent_anchor_async()        intent anchor extracted by a small model
10 [multimodal] MULTIMODAL_IMAGE_PROTOCOL
11 [attachments] SESSION_ATTACHMENTS_PROTOCOL
```

The prompt is assembled **per request**, and `request.channel` (dashboard / gateway / cli) decides which protocol blocks are injected — one kernel serves very different front ends without forking.

Instantiation (`loop.py:1134`):

```python
agent = Agent(
    model=model,                 # DojoStrandsModelBridge
    messages=agent_messages,
    tools=strands_tools,         # DojoBridgedTool list
    system_prompt=system,
    hooks=hooks,
    plugins=plugins,
    callback_handler=callback_handler if active_callback else None,
    agent_id=strands_agent_id,
    session_manager=strands_session_manager,
)
```

Execution (`loop.py:1171`): `await agent.invoke_async(prompt=..., invocation_state=..., limits=...)`. The kernel drives multi-turn tool use; `result.metrics.cycle_count` is the iteration count and `result.stop_reason == "limit_turns"` maps to `iteration_limit`.

### 5.3 Hook chain

| Hook | Location | Responsibility |
| --- | --- | --- |
| `check_guardrails_before` | closure in `loop.py` (~920-1000) | domain argument repair (`repair_sector_tool_arguments`), harness repair/block, guardrail `before_call`, `tool_started` event |
| `check_guardrails_after` | closure in `loop.py` (~1003-1078) | publish `ToolExecutionFailed`, publish `DataVolumeLarge`, guardrail `after_call` guidance, recover rich results, build `tool_trace` |
| `TokenCompressionHook` | `agent/hooks/token_compression.py` | compaction decision before each model call |
| `TurnCompletionHook` | `agent/hooks/turn_completion.py` | turn finalisation |
| `MemoryHookProvider` | `memory/manager.py:77` | memory read/write |
| `DojoPluginBridge` | `plugins/registry.py:499` | plugin hooks → Strands plugin |

Available interventions: rewrite `event.tool_use["input"]`, rewrite `event.tool_use["name"]`, cancel with a synthetic result via `event.cancel_tool`, or abort the turn with `GuardrailHaltException` (`loop.py:65`, later recognised as `EventLoopException.__cause__`). The after-hook may rewrite `event.result["content"]`, which is how self-healing and summarisation work.

### 5.4 Context and token governance

| Component | Location | Role |
| --- | --- | --- |
| `ModelContextRegistry` | `agent/model_context.py:165` | resolve/probe each model's window (`ModelContextInfo`) |
| `SessionTokenLedger` | `agent/token_ledger.py:72` | per-session token accounting (`SessionTokenState`) |
| `TokenCompressionPolicy` | `agent/token_policy.py:7` | when to compact |
| `ContextCompressor` | `agent/compressor.py:237` | how to compact: `prune_old_tool_results()` + LLM `compress()` |

Three trigger paths: preventive (`TokenCompressionHook`), emergency (`ContextLengthExceededError` → compact → retry once), and per-result truncation inside `ToolExecutor`. Compaction emits `ContextCompactedEvent` (`agent/events.py:113`).

### 5.5 Tool guardrails

`agent/guardrails.py::ToolCallGuardrailController`: `ToolCallSignature.from_call()` (:36) normalises name+args to detect repeats; `before_call()` (:96) returns a `ToolGuardrailDecision` with `allows_execution` / `should_halt`; `after_call()` (:181) may `warn`; `toolguard_synthetic_result()` (:275) fabricates a tool result so the model sees *why* it was blocked; `append_toolguard_guidance()` (:294) appends corrective guidance. `reset_for_turn()` (:89) resets counters. Toggle: `AgentConfig.enable_guardrails`.

### 5.6 Harness: pluggable domain constraints

Protocol at `agent/harness.py:129`; implementations in `agent/harnesses/` (`portfolio.py`, `portfolio_eval.py`, `portfolio_task_intent.py`, `artifact_synthesis.py`, `tool_orchestrated.py`).

| Method | Call site | Purpose |
| --- | --- | --- |
| `matches()` | `loop.py:448` | pick the active harness (first match) |
| `repair_tool_calls()` | before-tool hook (`loop.py:974`) | fix wrong tool name/arguments |
| `block_tool_call()` | before-tool hook (`loop.py:989`) | block out-of-order calls with a reason |
| `validate_progress()` | finalisation (`loop.py:1288`) | was the task really completed? |
| `build_recovery_prompt()` | finalisation (`loop.py:1292`) | drive an extra recovery turn |
| `build_final_context()` | finalisation | enrich the final answer |

State lives in `HarnessLoopState` (`harness.py:22`) with domain accessors (`created_portfolio_ids`, `target_portfolio_id`, `last_eval_submission`, …). Recovery turns are capped by `min(recovery_cap, max_iterations - 1)` (`loop.py:1285`).

### 5.7 Tool layer

`ToolSpec` (`tools/registry.py:9`) and `ToolRegistry` (:24, with `clone()` used to give sub-agents a trimmed tool subset); `ToolExecutor.execute_one()` handles sandbox policy, timeout, error normalisation, truncation and latency. Built-ins live in `dojoagents/tools/`: `terminal_tool`, `code_execution_tool`, `session_file_tool`, `session_input_tool`, `web_searcher`, `dojo_sdk_tool`, `mcp_tool` (+`mcp_oauth`), `skill_manage`, `plugin_manage`, `tools_list_tool`, `agent_viz`, `process_registry`, `environments/`. Tool names are sanitised for the model (`_safe_tool_name` `loop.py:1519`, `_sanitize_tool_specs` :1464) and restored afterwards (`_restore_tool_call_names` :1488). Registration happens in `runtime.py:57-231`, partly conditional (terminal / code execution by policy, delegation tool only when multi-agent is enabled).

### 5.8 Skills

`skills/manager.py::SkillManager`: `parse_frontmatter()` (:38), `_matches_platform()` (:64), `_matches_tool_requirements()` (:79, hides skills whose required tools are unavailable), `_get_skill_content()` (:88, cached), `prompt_block()` (:100), `list_skills()` (:163). Bodies are fetched on demand through `skills_list` / `skill_view` in `tools/skill_manage.py` — progressive disclosure in practice.

### 5.9 Plugins

`plugins/registry.py`: `PluginManifest` (:39), `DojoPluginContext` (:50), `DojoPluginRegistry` (:73, discovers built-in dirs plus `~/.dojo/plugins`), `DojoPluginBridge` (:499, a Strands `Plugin`). A plugin can contribute skill directories, MCP configs, tools and hooks at once.

### 5.10 Planning and multi-agent

**Planning** (`dojoagents/planning/`): `Plan` / `PlanStep` / `PlanStatus` / `StepType` (`models.py`), `PlanStateStore` (`store.py:14`), `PlanExecutionEngine` (`engine.py:12`), `PlanActivationHook` (`triggers.py:21`), `AutoPlanManager` (`automation.py:13`) subscribing to `TaskComplexityHigh`. The loop only checks `should_create_plan()` and publishes; if planning takes over, its result is returned directly.

**Multi-agent** (`dojoagents/multi_agent/`): `AgentSpec` / `AgentRole` / `SubTask` / `AgentMessage` (`models.py`), `AgentPool` (`pool.py:15`, reuses `AgentLoop` with a cloned tool subset), `get_delegation_tool_spec(pool)` registered at `runtime.py:218`, `Orchestrator` (`orchestrator.py:19`), `MultiAgentTriggerHook` (`triggers.py:38`) and `MultiAgentAutoDispatcher` (`automation.py:10`) for event-driven dispatch.

### 5.11 Resilience

| Problem | Mitigation | Location |
| --- | --- | --- |
| Empty assistant turn | detect `last_assistant_turn_empty()`, retry once with `build_empty_assistant_recovery_prompt()`, else fall back to `empty_assistant_user_message()` | `loop.py:1186-1210`, `agent/empty_assistant.py` |
| Reasoning leaking into content | strip `<think>` / `<thinking>` / `<reasoning>` / `<thought>`; streaming side uses `StreamingThinkScrubber` | `loop.py:1158-1166` |
| Context overflow | compact and retry once | `loop.py:210-235` |
| Repeated identical tool calls | guardrail signature dedup | `guardrails.py:31` |
| Domain flow skipped | harness validation + recovery turn | `loop.py:1279-1300` |
| Provider not configured | return `AgentResponse` with `error: no_model_configured` instead of raising | `loop.py:541` |
| Iteration cap reached | `stop_reason == "limit_turns"` → `stopped_reason = "iteration_limit"`, still answer | `loop.py:1181` |

---

## 6. End-to-end sequence

```text
ChatRequest
   ├─ [assembly] Runtime supplies provider / tools / skills / memory / plugins / harnesses
   ├─ 1 system prompt composition
   ├─ 2 model bridge + token ledger + context window
   ├─ 3 history → Strands messages
   ├─ 4 tools collected → sanitised → DojoBridgedTool
   ├─ 5 hooks assembled
   ├─   plan activation ── publish("TaskComplexityHigh") ──▶ planning may take over
   ├─ 6 Agent(...) instantiated
   └─ 7 agent.invoke_async()
          └── Strands kernel loop ↻
                ├─ Model.stream() → bridge → LLMProvider.chat()
                │     └─ ContextLengthExceeded → compact → retry once
                ├─ BeforeToolCall → arg repair / harness / guardrails / events
                ├─ Tool.stream() → DojoBridgedTool → ToolExecutor → sandbox → handler
                ├─ AfterToolCall → self-heal / summarise / guardrail warn / trace
                └─ until no tool calls or limits reached
          ↓ empty-turn recovery → think scrubbing → harness.validate_progress()
          ↓ _run_exit_hooks() (loop.py:1348)
       AgentResponse (content / tool_trace / metrics / stopped_reason) + event stream
```

Event types are defined in `agent/events.py` and delivered through `AgentEventSink` (:118).

---

## 7. Extension cheatsheet

| Goal | Change this | Not this |
| --- | --- | --- |
| Add a tool | write a `ToolSpec`, register in `runtime.py` — see [Adding Tools](../development/adding-tools.md) | `loop.py` |
| Add a business-flow constraint | new `agent/harnesses/xxx.py` implementing `TaskHarness` | an `if` inside `run()` |
| Support a new model service | implement `LLMProvider`, register in `LLMProviderRegistry` | the model bridge |
| Add prompt content | prefer a Skill; channel-specific protocol blocks go in stage 1 | the hard-coded role line |
| Change compaction | `token_policy.py` / `compressor.py` | hook ordering |
| Add a hook-supported interceptor | a new hook or a plugin | explicit recovery/event orchestration in the main loop |
| Add a sub-agent role | `multi_agent/models.py::AgentSpec` + `AgentPool` | delegation call sites |

---

## 8. Code index

| File | Key symbols | Responsibility |
| --- | --- | --- |
| `agent/loop.py` | `AgentLoop`(:393), `run()`(:435), `DojoStrandsModelBridge`(:147), `DojoBridgedTool`(:72), `strands_to_dojo_messages`(:324), `GuardrailHaltException`(:65), `_run_exit_hooks`(:1348) | orchestration and bridging |
| `agent/runtime.py` | `Runtime`(:34) | dependency assembly |
| `agent/harness.py`, `agent/harnesses/` | `TaskHarness`(:129), `HarnessLoopState`(:22) | domain constraints |
| `agent/providers.py` | `LLMProvider`(:54), `OpenAICompatibleProvider`(:139), `get_strands_model`(:326) | model access |
| `agent/guardrails.py` | `ToolCallGuardrailController`(:66) | tool guardrails |
| `agent/compressor.py` | `ContextCompressor`(:237) | context compaction |
| `agent/model_context.py`, `token_ledger.py`, `token_policy.py` | `ModelContextRegistry`, `SessionTokenLedger`, `TokenCompressionPolicy` | token governance |
| `agent/hooks/` | `TokenCompressionHook`, `TurnCompletionHook` | loop aspects |
| `agent/session_manager.py` | `DojoAgentSessionManager`(:144) | session persistence |
| `agent/events.py` | `AgentEventSink`(:118) | event stream |
| `tools/` | `ToolSpec`, `ToolRegistry`, `ToolExecutor`, `sandbox` | tool contract and execution |
| `skills/manager.py` | `SkillManager`(:15) | skill index and lazy loading |
| `memory/manager.py` | `MemoryManager`(:8), `MemoryHookProvider`(:77) | memory |
| `plugins/registry.py` | `DojoPluginRegistry`(:73), `DojoPluginBridge`(:499) | plugins |
| `planning/`, `multi_agent/` | `PlanExecutionEngine`, `AgentPool`, `Orchestrator` | planning and delegation |
| `utils/event_bus.py` | `EventBus`(:4) | event bus |

> Line numbers reflect the code at writing time; search by symbol after refactors.

---

## 9. Related pages

- [Agent Loop](agent-loop.md) — conceptual view of a turn
- [Runtime](runtime.md) — assembly and configuration
- [Tools and Sandbox](tools-and-sandbox.md)
- [Plugins](plugins.md)
- [Multi-Agent and Planning](multi-agent-planning.md)
- [Memory](memory.md)
- [Event-driven](event-driven.md)
- [Adding Tools](../development/adding-tools.md), [Repository Map](../development/repository-map.md)
