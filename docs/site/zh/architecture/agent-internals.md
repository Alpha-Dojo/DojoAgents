# Agent 实现内幕

> 本页回答一个此前文档没有正面回答的问题：**DojoAgents 的 Agent 能力到底是怎么搭起来的？**
>
> [Agent Loop](agent-loop.md) 描述的是「概念上的一轮对话」，本页描述的是「代码里真实发生的事」——用了哪个 Agent 框架、怎么桥接、系统提示词怎么拼、工具调用被谁拦截、上下文怎么压、领域逻辑挂在哪。
>
> 主要代码入口：`dojoagents/agent/loop.py`，重点是 `AgentLoop.run()`。本页行号只用于定位当前文档快照，稳定的引用依据是符号名。
>
> 证据边界：本页描述当前代码中可观察到的实现，不推断项目未记录的框架选型意图。已经确认的运行限制统一记录在[已知限制](../development/known-limitations.md)。

---

## 1. 一句话概括

**DojoAgents 把模型与工具之间的内层循环交给 [Strands Agents](https://github.com/strands-agents/sdk-python)，而 `AgentLoop.run()` 仍负责请求编排、提示词装配、桥接、Hook、恢复、领域校验和对外事件。**

```text
        DojoAgents 自有资产                     Strands Agents 内核
  ┌───────────────────────────┐           ┌────────────────────────┐
  │ LLMProvider (OpenAI 兼容) │──桥接──▶ │ strands.models.Model   │
  │ ToolSpec + ToolExecutor   │──桥接──▶ │ strands.types.AgentTool│
  │ SkillManager / Memory     │──拼装──▶ │ system_prompt          │
  │ Guardrails / Harness      │──挂载──▶ │ hooks (Before/After)   │
  │ Plugins                   │──挂载──▶ │ plugins                │
  │ DojoAgentSessionManager   │──注入──▶ │ session_manager        │
  └───────────────────────────┘           └────────────────────────┘
                                                    │
                                          agent.invoke_async(...)
                                                    │
                                          多轮 tool-use 循环由内核驱动
```

---

## 2. 用了哪些框架

| 依赖 | 版本约束 | 在 Agent 能力中的角色 |
| --- | --- | --- |
| `strands-agents` | 不锁版本 | **Agent 事件循环内核**：多轮 tool-use 编排、消息状态机、Hook/Plugin 体系、`stop_reason`/`metrics` |
| `strands-agents-tools` | 不锁版本 | Strands 官方工具集（按需引入） |
| `openai` | `>=1.20,<2` | `OpenAICompatibleProvider` 的底层 SDK，也用于统计 token 与探测上下文窗口 |
| `mcp` | `>=1.26,<2` | MCP 工具接入（`dojoagents/tools/mcp_tool.py`、`mcp_oauth.py`） |
| `fastapi` | `>=0.110,<0.112` | Dashboard / Gateway 暴露 Agent 能力（SSE、OpenAI 兼容接口） |
| `apscheduler` | `>=3.10,<4` | 定时任务触发 Agent 运行 |
| `dojosdk` | `>=0.1.15` | 量化金融数据能力，包装为工具（`tools/dojo_sdk_tool.py`） |

声明位置：`pyproject.toml` `dependencies` 与 `requirements.txt`。

> **代码中可观察到的集成取舍。** 当前实现使用 Strands 承担模型/工具循环和 Hook 协议，同时通过适配器保留 DojoAgents 自己的 provider 与工具契约。可变的工具前后事件支持取消、改参和改结果。这些是实现事实，不代表项目已经记录了与其他框架的完整比较或选型理由。

---

## 3. 六条贯穿全局的设计思想

### 3.1 防腐层：借内核，不被内核绑架

Strands 的主要适配边界集中在 `agent/loop.py`：`DojoStrandsModelBridge`、`DojoBridgedTool`、消息转换和调用都在这里实现。少量相邻模块也直接使用 Strands 契约，包括会话管理、空回复恢复和插件桥。因此替换内核需要调整这一边界及其集成点，不能简化为只改一个桥接代码段。

配套的是**双向消息翻译**：

- 出站：Dojo 历史 → Strands `Messages`（`run()` 第 3 阶段，`loop.py:647` 起）
- 入站：Strands `Messages` → Dojo 消息（`strands_to_dojo_messages()`，`loop.py:324`）
- 压缩前再拍平一次：`compressor.flatten_messages_for_compress()` / `messages_to_strands()`

### 3.2 通用循环 + 领域 Harness

金融领域的强约束（组合必须先创建再回测、评测必须提交结果……）**不写进循环**，而是实现 `TaskHarness` 协议后注册进来。循环只负责在固定的 6 个时机回调它。详见 [§5.6](#harness-domain-constraints)。

### 3.3 上下文经济学：渐进式披露 + 主动压缩

- **技能按配置披露**：默认 `agent.lazy_skills: true` 时，`SkillManager.prompt_block()` 只注入名称/描述，正文靠 `skill_view` 按需读取；关闭懒加载时会直接注入技能正文。
- **工具结果不全量保留**：`ContextCompressor.prune_old_tool_results()` 保留尾部 N 条，历史工具结果降级为摘要（`_summarize_tool_result()`），工具入参 JSON 截断到 150 字符（`_truncate_tool_call_args_json()`）。
- **超限自愈**：撞到上下文上限不是报错，而是压缩后重试一次（[§5.4](#context-token-governance)）。

### 3.4 混合式治理：Hook 与显式编排

护栏、Token 压缩、记忆接入、回合完成和插件拦截通过 Hook/Plugin 装配；`AgentLoop.run()` 仍显式负责 Harness 解析与修复、恢复尝试、事件发布和最终响应处理。扩展或替换循环时必须同时考虑这两类治理路径。

### 3.5 一切能力皆 ToolSpec

技能管理、插件管理、终端、代码执行、会话文件、MCP、DojoSDK 数据、甚至**子 Agent 委派**，统一收敛为 `ToolSpec` 注册到 `ToolRegistry`。模型看到的世界是同构的，`Runtime` 只是在装配期决定往注册表里放什么。

### 3.6 事件总线：解耦旁路能力

`dojoagents/utils/event_bus.py::EventBus` 提供 `publish(topic, payload)`。计划编排、多智能体派发、工具失败自愈和大结果摘要通过订阅解耦；发布动作仍是 `AgentLoop.run()` 及其工具 Hook 中的显式调用，因此它属于循环编排的一部分：

| 事件 | 发布位置 | 典型订阅者 |
| --- | --- | --- |
| `TaskComplexityHigh` | `loop.py:595` 附近（Plan 激活检查） | `planning/automation.py::AutoPlanManager` |
| `ToolExecutionFailed` | after-tool hook | 自愈/重写策略（返回值可直接顶替失败结果） |
| `DataVolumeLarge` | after-tool hook（结果 > 5000 字符） | 分析型子 Agent，把大结果换成摘要 |

---

## 4. 模块分层

```text
入口层    CLI / Dashboard(FastAPI) / Gateway / Cron
             │  ChatRequest
装配层    dojoagents/agent/runtime.py::Runtime
          └─ 读 ConfigStore → 建 provider、ToolRegistry、SkillManager、
             MemoryManager、PluginRegistry、AgentPool、Harness 列表
编排层    dojoagents/agent/loop.py::AgentLoop.run()   ← 本页重点
          ├─ 桥接: DojoStrandsModelBridge / DojoBridgedTool
          ├─ 切面: guardrails / token compression / turn completion / memory / plugin
          └─ 内核: strands.Agent.invoke_async()
执行层    tools/executor.py::ToolExecutor → sandbox policy → ToolSpec.handler
旁路层    event_bus ↔ planning / multi_agent / 自愈策略
```

---

## 5. 关键实现拆解

### 5.1 双向桥接层

#### `DojoBridgedTool`（`loop.py:72-146`）

继承 `strands.types.tools.AgentTool`，把一个 Dojo `ToolSpec` 包装成 Strands 工具：

- `tool_spec` 属性把 Dojo 的 JSON Schema 转成 Strands 的 `inputSchema`；
- `stream()` 内部调用 `ToolExecutor`，并把产生的 `ToolResult` 塞进 `invocation_state["_dojo_tool_results"]`（`loop.py:124`），供 after-tool hook 取回真实的 `latency_ms` / `truncated` / `viz_blocks` / `artifacts` / `resource_changes`；
- 同时向 `event_sink` 发工具事件，驱动前端流式 UI。

> 这里有一个值得注意的细节：Strands 的工具结果是纯文本 content，**结构化元数据会丢失**。DojoAgents 用 `invocation_state` 这条"侧信道"把富结果带出来，再在 hook 里按 `call_id` 匹配回收（`loop.py:1046-1056`）。

#### `DojoStrandsModelBridge`（`loop.py:147-323`）

继承 `strands.models.model.Model`，把任意 Dojo `LLMProvider` 变成 Strands 模型：

1. `strands_to_dojo_messages()` 把 Strands 消息翻译回 OpenAI 风格消息（含 `toolUse` / `toolResult` / `reasoningContent` / 多模态图片块）；
2. 起一个后台 task 调 `llm_provider.chat(..., stream=True, stream_callback=callback)`，用 `asyncio.Queue` 把增量文本和最终 `LLMResult` 送回；
3. 按 Strands 的 `StreamEvent` 协议 yield：`messageStart` → `contentBlockStart` → 多个 `contentBlockDelta` → 工具块/结束块；
4. **上下文溢出自愈**：捕获 `ContextLengthExceededError` 后，从 `invocation_state` 取出 `_dojo_handle_context_length_exceeded` 回调压缩 `agent.messages`，然后**原地重试一次**（`_dojo_context_length_retries < 1`，`loop.py:210-235`）；
5. 顺带把 usage 写入 `invocation_state["_dojo_last_usage"]`，provider 没返回 usage 时用 `_estimate_tokens_rough()` 估算。

### 5.2 `AgentLoop.run()` 的七个阶段

代码里用编号注释明确分段，可按行号定位：

| 阶段 | 行号 | 做什么 |
| --- | --- | --- |
| 1. 构建系统提示词 | `loop.py:544` | 见下方拼装清单 |
| 2. 建模型桥 + Token 账本 | `loop.py:604` | `DojoStrandsModelBridge`、`SessionTokenLedger`、`ModelContextRegistry` 决定窗口大小 |
| 3. 转换历史 | `loop.py:647` | Dojo 历史 → Strands `content blocks`（文本 / toolUse / reasoningContent） |
| 4. 收集并桥接工具 | `loop.py:743` | `_collect_tool_specs()` + 插件工具 → `_sanitize_tool_specs()` → `DojoBridgedTool` |
| 5. 装配 Hook | `loop.py:757` | memory hook、token 压缩 hook、turn completion hook、插件桥、护栏 hook |
| 6. 实例化 Strands Agent | `loop.py:1082` | 见 `Agent(...)` 于 `loop.py:1134` |
| 7. 运行与收尾 | `loop.py:1146` | `invoke_async` → 空回复恢复 → harness 校验 → exit hooks |

**系统提示词拼装顺序**（`loop.py:544-590`，用 `\n\n` 连接非空块）：

```text
1  角色定义（"You are DojoAgents, a full-market finance analysis agent."）
2  build_temporal_context_block()        时间上下文，防止模型用训练期日期
3  SkillManager.prompt_block(platform)   技能索引（按 channel 平台过滤）
4  MemoryManager.build_system_prompt()   长期记忆说明
5  MemoryManager.prefetch_all(message)   与本轮问题相关的记忆预取
6  [quant] QuantContext.prompt_block() + DojoExtensionRegistry.prompt_context()
7  [dashboard] 可视化协议 + 工具协议 + 可视化策略目录 + 本轮策略锚点
8  [task] TaskPromptManager.build_injection_block()
9  build_turn_intent_anchor_async()      用小模型抽取本轮意图，做成锚点
10 [多模态] MULTIMODAL_IMAGE_PROTOCOL
11 [附件]   SESSION_ATTACHMENTS_PROTOCOL
```

> 设计要点：提示词是**按请求动态组装**的，`request.channel`（dashboard / gateway / cli）直接决定注入哪些协议块。这让同一个 Agent 内核能服务形态差异很大的前端而不需要分叉。

**Agent 实例化**（`loop.py:1134`）：

```python
agent = Agent(
    model=model,                 # DojoStrandsModelBridge
    messages=agent_messages,     # 转换后的历史
    tools=strands_tools,         # DojoBridgedTool 列表
    system_prompt=system,        # 上面拼出来的字符串
    hooks=hooks,                 # 护栏/压缩/记忆/回合完成
    plugins=plugins,             # DojoPluginBridge
    callback_handler=callback_handler if active_callback else None,
    agent_id=strands_agent_id,
    session_manager=strands_session_manager,   # DojoAgentSessionManager
)
```

**执行**（`loop.py:1171`）：`await agent.invoke_async(prompt=..., invocation_state=..., limits=...)`。多轮 tool-use 由 Strands 内核驱动，`result.metrics.cycle_count` 即实际迭代轮数，`result.stop_reason == "limit_turns"` 映射为 DojoAgents 的 `iteration_limit`。

### 5.3 Hook 拦截链

| Hook | 实现位置 | 触发时机与职责 |
| --- | --- | --- |
| `check_guardrails_before` | `loop.py` 内闭包（约 920-1000） | 领域参数修复（`repair_sector_tool_arguments`）、harness 修复/拦截、护栏 `before_call`、发 `tool_started` 事件 |
| `check_guardrails_after` | `loop.py` 内闭包（约 1003-1078） | 失败发 `ToolExecutionFailed`、大结果发 `DataVolumeLarge`、护栏 `after_call` 追加指导语、回收富结果、写 `tool_trace` |
| `TokenCompressionHook` | `agent/hooks/token_compression.py` | 每轮前按 `TokenCompressionPolicy` 判断是否压缩历史 |
| `TurnCompletionHook` | `agent/hooks/turn_completion.py` | 回合完成时的收尾（持久化/统计） |
| `MemoryHookProvider` | `memory/manager.py:77` | 记忆的读写接入 |
| `DojoPluginBridge` | `plugins/registry.py:499` | 把插件声明的 hook 转成 Strands plugin |

**拦截能力有多强？** before-hook 里三种干预都用上了：

- 改参数：`event.tool_use["input"] = repaired_args`
- 改工具名：`event.tool_use["name"] = repaired.name`
- 取消执行并回注合成结果：`event.cancel_tool = blocked_res["content"]`
- 直接中止整轮：`raise GuardrailHaltException(...)`（`loop.py:65`），在外层被识别为 `EventLoopException.__cause__` 后转成优雅回复

after-hook 可以**改写工具结果**（`event.result["content"] = [...]`），这是"失败自愈"和"大结果摘要化"的实现基础。

<a id="context-token-governance"></a>

### 5.4 上下文与 Token 治理

四个组件协同：

| 组件 | 位置 | 职责 |
| --- | --- | --- |
| `ModelContextRegistry` | `agent/model_context.py:165` | 查/探测每个模型的上下文窗口（`ModelContextInfo`） |
| `SessionTokenLedger` | `agent/token_ledger.py:72` | 按 session 累计 token（`SessionTokenState`），支撑 `TokenUsageEvent` |
| `TokenCompressionPolicy` | `agent/token_policy.py:7` | 判断"何时该压" |
| `ContextCompressor` | `agent/compressor.py:237` | 执行压缩：`prune_old_tool_results()` 保尾裁头 + `compress()` 做 LLM 摘要 |

三条触发路径：

1. **预防式**：`TokenCompressionHook` 在每轮模型调用前按 policy 检查；
2. **应急式**：模型桥捕获 `ContextLengthExceededError` → 压缩 → 重试一次；
3. **结果级**：`ToolExecutor` 对超长工具输出直接截断并标记 `truncated`。

压缩完成后会发出 `ContextCompactedEvent`（`agent/events.py:113`），前端可以显示"上下文已压缩"。

### 5.5 工具护栏

`agent/guardrails.py::ToolCallGuardrailController`：

- `ToolCallSignature.from_call()`（:36）把 `工具名 + 参数` 归一化成签名，用于**识别重复调用**；
- `before_call()`（:96）返回 `ToolGuardrailDecision`，含 `allows_execution` / `should_halt`；
- `after_call()`（:181）根据结果与失败状态决定 `warn` / 升级；
- `toolguard_synthetic_result()`（:275）生成"假装工具返回"的内容，让模型看到被拦截的原因而不是空洞失败；
- `append_toolguard_guidance()`（:294）在真实结果后追加纠偏指导语。

`reset_for_turn()`（:89）保证计数按回合重置。开关：`AgentConfig.enable_guardrails`。

<a id="harness-domain-constraints"></a>

### 5.6 Harness：领域逻辑的可插拔约束层

协议定义在 `agent/harness.py:129`，实现放在 `agent/harnesses/`：

```text
harnesses/portfolio.py              组合创建/调仓流程约束
harnesses/portfolio_eval.py         组合评测流程约束
harnesses/portfolio_task_intent.py  组合任务意图识别
harnesses/artifact_synthesis.py     产物合成
harnesses/tool_orchestrated.py      纯工具编排型任务
```

`TaskHarness` 六个回调及其调用点：

| 方法 | 调用点 | 作用 |
| --- | --- | --- |
| `matches(request, state)` | `loop.py:448` `_resolve_active_harness()` | 选出本轮生效的 harness（首个匹配） |
| `repair_tool_calls(calls, state)` | before-tool hook（`loop.py:974`） | 纠正模型给出的错误工具名/参数 |
| `block_tool_call(call, state)` | before-tool hook（`loop.py:989`） | 违反流程则拦截并给出原因 |
| `validate_progress(state)` | 收尾阶段（`loop.py:1288`） | 判断任务是否真正完成 |
| `build_recovery_prompt(decision, locale)` | 收尾阶段（`loop.py:1292`） | 未完成时生成补救提示，触发额外回合 |
| `build_final_context(...)` | 收尾阶段 | 给最终回答补充结构化上下文 |

状态载体是 `HarnessLoopState`（`harness.py:22`），它把本轮的 `tool_calls` / `tool_results` / `blocked_calls` / `tool_trace` / `final_response` 汇总起来，并提供领域快捷访问器（如 `created_portfolio_ids`、`target_portfolio_id`、`last_eval_submission`）。

恢复回合有上限：`min(recovery_cap, max_iterations - 1)`（`loop.py:1285`），避免与模型互相拉锯。

> **边界纪律**：`agent-loop.md` 里那句"领域逻辑不应硬编码在通用 Agent Loop 中"，落地机制就是这套 harness。新增业务约束应当新建 harness，而不是在 `run()` 里加分支。

### 5.7 工具层

- 契约：`tools/registry.py:9::ToolSpec`（`name` / `description` / JSON Schema / `handler`），`schema()` 输出模型可见的函数定义；
- 注册表：`ToolRegistry`（:24），提供 `register` / `get` / `schema_list` / `all` / `clone` / `remove`，`clone()` 是**子 Agent 裁剪工具子集**的基础；
- 执行：`tools/executor.py::ToolExecutor.execute_one()`，负责沙箱策略校验、超时、异常归一化、超长截断、`latency_ms` 统计，产出统一的 `ToolResult`；
- 内置工具（`dojoagents/tools/`）：`terminal_tool`、`code_execution_tool`、`session_file_tool`、`session_input_tool`、`web_searcher`、`dojo_sdk_tool`、`mcp_tool`(+`mcp_oauth`)、`skill_manage`、`plugin_manage`、`tools_list_tool`、`agent_viz`、`process_registry`、`environments/`；
- 名称安全：模型侧工具名经 `_safe_tool_name()`（`loop.py:1519`）与 `_sanitize_tool_specs()`（:1464）清洗，回填时用 `_restore_tool_call_names()`（:1488）还原真名——兼容对函数名字符集有限制的 provider。

`Runtime` 在装配期把这些注册进 `ToolRegistry`（`runtime.py:57-231`），包括条件性注册（终端/代码执行受策略控制、多智能体开启时才注册 `delegation` 工具）。

### 5.8 技能层（Skills）

`skills/manager.py::SkillManager`：

| 方法 | 行号 | 说明 |
| --- | --- | --- |
| `parse_frontmatter()` | :38 | 解析 `SKILL.md` 的 YAML frontmatter 与正文 |
| `_matches_platform()` | :64 | 按 `request.channel` 平台过滤 |
| `_matches_tool_requirements()` | :79 | 依赖工具不可用时不展示，避免模型调不存在的工具 |
| `_get_skill_content()` | :88 | 带缓存的内容读取 |
| `prompt_block(platform)` | :100 | 生成注入系统提示词的技能索引块 |
| `list_skills(platform)` | :163 | 列出可用技能 |

正文按需读取由 `tools/skill_manage.py` 提供的 `skills_list` / `skill_view` 工具完成——这就是 **progressive disclosure**：索引进提示词，正文进工具结果，token 花在真正用到的技能上。

### 5.9 插件层

`plugins/registry.py`：`PluginManifest`（:39）描述清单，`DojoPluginContext`（:50）是插件拿到的运行时句柄，`DojoPluginRegistry`（:73）负责发现（内置目录 + `~/.dojo/plugins`）与加载，`DojoPluginBridge`（:499）继承 Strands `Plugin`，把插件声明的 hook 转接到内核事件上。插件可同时贡献**技能目录、MCP 配置、工具和 hook**。

### 5.10 旁路能力：Planning 与 Multi-Agent

**Planning**（`dojoagents/planning/`）：`Plan` / `PlanStep` / `PlanStatus` / `StepType`（`models.py`）、`PlanStateStore`（`store.py:14`）持久化、`PlanExecutionEngine`（`engine.py:12`）执行、`PlanActivationHook`（`triggers.py:21`）判断是否需要出计划、`AutoPlanManager`（`automation.py:13`）订阅 `TaskComplexityHigh` 用 LLM 自动生成计划。主循环只在 `loop.py:595` 附近做一次 `should_create_plan()` 判断并 `publish`，**若计划流程接管则直接返回其结果**。

**Multi-Agent**（`dojoagents/multi_agent/`）：`AgentSpec` / `AgentRole` / `SubTask` / `AgentMessage`（`models.py`）、`AgentPool`（`pool.py:15`）创建子 Agent（复用 `AgentLoop` + `ToolRegistry.clone()` 裁剪工具）、`get_delegation_tool_spec(pool)` 把"委派"暴露成普通工具（`runtime.py:218`）、`Orchestrator`（`orchestrator.py:19`）编排、`MultiAgentTriggerHook`（`triggers.py:38`）与 `MultiAgentAutoDispatcher`（`automation.py:10`）负责事件驱动的自动派发（例如订阅 `DataVolumeLarge` 让分析子 Agent 做摘要）。

### 5.11 韧性设计（容易被忽略但很关键）

| 问题 | 对策 | 位置 |
| --- | --- | --- |
| 模型返回空回复 | 检测 `last_assistant_turn_empty()` → 用 `build_empty_assistant_recovery_prompt()` 重试 1 次 → 仍空则回退到 `empty_assistant_user_message()` 兜底文案 | `loop.py:1186-1210`、`agent/empty_assistant.py` |
| 思维链泄漏到正文 | 正则清洗 `<think>` / `<thinking>` / `<reasoning>` / `<thought>`，流式侧用 `StreamingThinkScrubber` | `loop.py:1158-1166`、`agent/think_scrubber.py` |
| 上下文超限 | 压缩后重试一次 | `loop.py:210-235` |
| 工具反复调用同一参数 | 护栏签名去重 | `guardrails.py:31` |
| 领域流程被跳过 | harness 校验 + 恢复回合 | `loop.py:1279-1300` |
| provider 未配置 | 提前返回带 `error: no_model_configured` 的 `AgentResponse`，不抛异常 | `loop.py:541` |
| 迭代打满 | `stop_reason == "limit_turns"` → `stopped_reason = "iteration_limit"`，仍产出可用回答 | `loop.py:1181` |

---

## 6. 一次请求的完整时序

```text
ChatRequest
   │
   ├─ [装配] Runtime 提供 provider / tools / skills / memory / plugins / harnesses
   │
   ├─ 1 系统提示词拼装（时间 + 技能索引 + 记忆 + 协议块 + 意图锚点）
   ├─ 2 模型桥 + token 账本 + 上下文窗口探测
   ├─ 3 历史转换为 Strands 消息
   ├─ 4 工具收集 → 名称清洗 → DojoBridgedTool
   ├─ 5 Hook 装配（护栏 / 压缩 / 记忆 / 回合完成 / 插件）
   ├─  Plan 激活检查 ── publish("TaskComplexityHigh") ──▶ 命中则由计划流程接管并返回
   ├─ 6 Agent(...) 实例化
   │
   └─ 7 agent.invoke_async()
          └── Strands 内核循环 ↻
                ├─ Model.stream() ─▶ DojoStrandsModelBridge ─▶ LLMProvider.chat()
                │      └─ ContextLengthExceeded ─▶ 压缩 ─▶ 重试一次
                ├─ BeforeToolCall ─▶ 参数修复 / harness 拦截 / 护栏 / tool_started 事件
                ├─ Tool.stream() ─▶ DojoBridgedTool ─▶ ToolExecutor ─▶ sandbox ─▶ handler
                ├─ AfterToolCall ─▶ 失败自愈 / 大结果摘要 / 护栏警告 / 富结果回收 / tool_trace
                └─ 直到无工具调用或触达 limits
          ↓
       空回复恢复 → think 清洗 → harness.validate_progress() → 恢复回合
          ↓
       _run_exit_hooks()（loop.py:1348）
          ↓
       AgentResponse（content / tool_trace / metrics / stopped_reason）+ 事件流
```

事件流类型见 `agent/events.py`：`ContentDeltaEvent`、`PhaseChangedEvent`、`Thinking*`、`ToolStarted/Finished`、`TokenUsageEvent`、`ContextCompactedEvent`、`RunCompleted/Failed` 等，由 `AgentEventSink`（:118）投递。

---

## 7. 扩展点速查

| 我想做… | 应该改哪里 | 不要改哪里 |
| --- | --- | --- |
| 加一个新工具 | 写 `ToolSpec` 并在 `runtime.py` 注册，见 [添加工具](../development/adding-tools.md) | `loop.py` |
| 加一条业务流程约束 | 新建 `agent/harnesses/xxx.py` 实现 `TaskHarness` | 在 `run()` 里加 if |
| 接一个新模型服务 | 实现 `LLMProvider` 协议并注册到 `LLMProviderRegistry` | 模型桥 |
| 加一段提示词 | 优先做成 Skill；平台专属协议块加在 `run()` 第 1 阶段 | 硬编码进角色定义 |
| 改压缩策略 | `token_policy.py` / `compressor.py` | Hook 装配顺序 |
| 加一个 Hook 支持的拦截 | 新建 hook 或写插件 | 主循环中的显式恢复/事件编排 |
| 加子 Agent 角色 | `multi_agent/models.py::AgentSpec` + `AgentPool` | 委派工具的调用方 |

---

## 8. 代码索引

| 文件 | 关键符号 | 职责 |
| --- | --- | --- |
| `agent/loop.py` | `AgentLoop`(:393)、`run()`(:435)、`DojoStrandsModelBridge`(:147)、`DojoBridgedTool`(:72)、`strands_to_dojo_messages`(:324)、`GuardrailHaltException`(:65)、`_run_exit_hooks`(:1348)、`_sanitize_tool_specs`(:1464) | 编排与桥接 |
| `agent/runtime.py` | `Runtime`(:34)、`from_default_config`(:47)、`from_config_store`(:51)、`for_profile`(:360) | 依赖装配 |
| `agent/harness.py` + `agent/harnesses/` | `TaskHarness`(:129)、`HarnessLoopState`(:22)、`HarnessDecision`(:10) | 领域约束 |
| `agent/providers.py` | `LLMProvider`(:54)、`LLMProviderRegistry`(:69)、`OpenAICompatibleProvider`(:139)、`get_strands_model`(:326) | 模型接入 |
| `agent/guardrails.py` | `ToolCallGuardrailController`(:66) | 工具护栏 |
| `agent/compressor.py` | `ContextCompressor`(:237)、`flatten_messages_for_compress`(:72) | 上下文压缩 |
| `agent/model_context.py` / `token_ledger.py` / `token_policy.py` | `ModelContextRegistry`(:165)、`SessionTokenLedger`(:72)、`TokenCompressionPolicy`(:7) | Token 治理 |
| `agent/hooks/` | `TokenCompressionHook`、`TurnCompletionHook` | 循环切面 |
| `agent/session_manager.py` | `DojoAgentSessionManager`(:144) | 会话持久化 |
| `agent/events.py` | `AgentEventSink`(:118) 及各事件类 | 事件流 |
| `tools/registry.py` / `tools/executor.py` / `tools/sandbox.py` | `ToolSpec`、`ToolRegistry`、`ToolExecutor` | 工具契约与执行 |
| `skills/manager.py` | `SkillManager`(:15) | 技能索引与懒加载 |
| `memory/manager.py` | `MemoryManager`(:8)、`MemoryHookProvider`(:77) | 记忆 |
| `plugins/registry.py` | `DojoPluginRegistry`(:73)、`DojoPluginBridge`(:499) | 插件 |
| `planning/` | `PlanExecutionEngine`(:12)、`PlanActivationHook`(:21)、`AutoPlanManager`(:13) | 计划 |
| `multi_agent/` | `AgentPool`(:15)、`Orchestrator`(:19)、`MultiAgentAutoDispatcher`(:10) | 多智能体 |
| `utils/event_bus.py` | `EventBus`(:4) | 事件总线 |

> 行号对应撰写时的代码状态，重构后请以符号名检索为准。

---

## 9. 延伸阅读

- [Agent Loop](agent-loop.md)：概念视角的一轮对话
- [Runtime](runtime.md)：依赖装配与配置来源
- [Tools 与 Sandbox](tools-and-sandbox.md)：工具契约与沙箱策略
- [Plugins](plugins.md)：插件发现与清单
- [Multi-Agent 与 Planning](multi-agent-planning.md)：子 Agent 与计划
- [Memory](memory.md)：记忆 provider
- [Event-driven](event-driven.md)：事件总线与订阅者
- [添加工具](../development/adding-tools.md)、[仓库地图](../development/repository-map.md)
