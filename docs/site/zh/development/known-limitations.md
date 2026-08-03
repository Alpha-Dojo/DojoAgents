# 已知限制

本清单记录基于 `0d3389e` 工作树中已经确认、且与项目实现直接相关的问题，并把可观察事实与修复建议分开。只有在回归测试证明问题已解决后，才移除对应条目。

## 状态定义

- **Open**：已由代码或可复现运行确认，尚无完整修复。
- **Mitigated**：已有规避方式或安全边界，但根因仍存在。
- **Resolved in working tree**：本地已有代码修正和定向回归测试，完成常规评审后可移出清单。

## 未解决限制

### DA-KI-001 — Agent run 缺少总墙钟时限

- **状态：** Open
- **范围：** `DojoStrandsModelBridge.stream()`、`AgentLoop.run()`
- **证据：** 模型桥通过没有超时的 `queue.get()` 等待结果，模型调用也没有包在 run 级 `asyncio.wait_for()` 中。工具和部分传输操作各自有超时，但完整 Agent run 没有累计 deadline。
- **影响：** 如果 provider 流既不结束也不抛错，run 可能持续处于运行状态；迭代次数无法约束实际耗时。
- **规避：** 使用后台 run 的取消接口，并在入口代理或进程层设置总超时。
- **后续：** 增加可配置 run deadline，把取消信号传播到模型任务，并用永不返回终态的 provider 编写测试。

### DA-KI-002 — Pipeline 与 Harness 缺少累计预算

- **状态：** Open
- **范围：** `tasks/runtime_helpers.py::run_agent_with_tasks()`、`AgentLoop.run()` 的 Harness 恢复逻辑
- **证据：** Pipeline 最多可调用五个 Agent step，每个 step 又可能增加最多八次 Harness 恢复调用；每次调用都接收常规的单次 `Limits`，完整 pipeline run 没有独立的累计 turn 或模型调用预算。
- **影响：** 不收敛的任务可能消耗远多于单看 `agent.max_iterations` 所预期的模型/工具循环。
- **规避：** 保守设置 pipeline step 和 `max_iterations`，在运行不再产生可观察进展时主动取消。
- **后续：** 引入覆盖 pipeline step、恢复调用、模型调用、工具调用和墙钟时间的共享 run budget，并在响应元数据中暴露累计消耗。

<a id="da-ki-003"></a>

### DA-KI-003 — Web 提取未执行 `max_content_bytes`

- **状态：** Open
- **范围：** `WebToolsConfig.max_content_bytes`、`tools/web_searcher.py`
- **证据：** 配置已加载并写入文档，但提取器读取 HTTP 响应体时没有使用它；字符级裁剪只发生在内容接收完成之后。
- **影响：** 大响应可能消耗超过配置含义所预期的网络流量和内存。
- **规避：** 只提取可信 URL；有强限制要求时，在出站代理层限制响应大小。
- **后续：** 流式读取响应字节，到达上限即停止并标记截断，同时补充多字节文本测试。

### DA-KI-004 — 搜索结果没有保留发布时间

- **状态：** Open
- **范围：** `_sanitize_search_rows()`、内置板块归因任务
- **证据：** 任务要求校验 `published_at`，但清洗后的搜索结果只保留 `title`、`url`、`description` 和 `position`，即使后端返回日期也会被丢弃。
- **影响：** Agent 不能只依靠搜索元数据证明新闻处于目标日期窗口；若不核验正文，可能采用过期证据。
- **规避：** 对候选来源调用 `web_extract`，从页面内容核验发布时间后再写入任务产物。
- **后续：** 定义跨后端的可选 `published_at` 字段，在适配和清洗阶段保留它，并补充日期范围测试。

### DA-KI-005 — Dashboard 身份认证由部署层承担

- **状态：** Mitigated
- **范围：** Dashboard HTTP API
- **证据：** 路由没有内置身份或角色校验；默认监听 `127.0.0.1`，[Dashboard API](../reference/dashboard-api.md) 已说明该边界。
- **影响：** 任何能连接监听地址的调用方都可以调用对话和管理接口。
- **规避：** 仅监听可信本机接口，或在带 TLS、网络策略和审计的认证入口之后部署。
- **后续：** 增加可选的一方认证模式，或提供官方支持的认证部署方案。

### DA-KI-011 — 前端锁文件解析到存在漏洞的 PostCSS 版本

- **状态：** Open
- **范围：** Dashboard 前端构建依赖
- **证据：** `npm audit` 对传递依赖 `postcss@8.5.15` 报告 [GHSA-r28c-9q8g-f849](https://github.com/advisories/GHSA-r28c-9q8g-f849)；受影响范围为 `<=8.5.17`，已有可用修复。
- **影响：** 前端构建处理攻击者控制的 previous source map 时，可能泄露构建主机上的任意 `.map` 文件。这是构建期依赖风险，不代表生成的 Dashboard bundle 已被证明可在浏览器中直接利用。
- **规避：** 只在隔离的 CI 环境中构建可信源码，不处理不可信 CSS/source map。
- **后续：** 把锁定的传递依赖升级到已修复的 PostCSS 版本，重新执行 `npm ci`、`npm audit` 和 `npm run build`，确认后保留锁文件变更。

## 当前工作树已修正项

| ID | 状态 | 修正内容 | 回归覆盖 |
| --- | --- | --- | --- |
| DA-KI-006 | Resolved in working tree | 显式 `null` 现在会禁用 Web search/extract 后端，不再被默认值悄悄覆盖。 | `tests/test_web_searcher.py` |
| DA-KI-007 | Resolved in working tree | 旧版组合数据先完成 v2 中间转换，再进入当前 candidates/orders schema。 | `tests/dashboard/stores/test_portfolio_migration.py`、`test_portfolio_orders.py` |
| DA-KI-008 | Resolved in working tree | 批量 K 线按 `symbol` 列建立并复用索引；显式日期窗口绕过快照。 | `tests/dashboard/test_dojo_data_gateway.py`、`test_kline_single_day_vs_bulk.py` |
| DA-KI-009 | Resolved in working tree | MCP sampling 在 provider 上限与调用方 `maxTokens` 之间取较小值。 | `tests/test_mcp_advanced.py` |
| DA-KI-010 | Resolved in working tree | 没有 session history 时跳过 turn-intent 分类，避免一次结果不可能影响提示词的模型调用。 | `tests/test_turn_intent.py`、`test_agent_harness.py` |
