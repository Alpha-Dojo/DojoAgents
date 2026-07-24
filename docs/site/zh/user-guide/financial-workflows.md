# 金融工作流

## 适用场景

DojoAgents 面向量化金融分析，常见工作流包括行情查询、行业/主题分析、组合构建与验证、结构化任务批处理、报告生成和可视化展示。

## 核心能力

- **`dojo.sdk.*` 金融只读取数**（Agent / Task 主路径）。详见 [DojoSDK](../reference/dojo-sdk.md)。
- **结构化 Task / Pipeline**（如每日市场事件、Theme Deep Dive）。详见 [任务与流水线](tasks-and-pipelines.md)。
- Dashboard financial services 与 store（**UI / REST**；不是新 Task 的依赖）。
- Agent tool result 中的 `resource_changes`，用于驱动前端刷新。
- `viz_blocks`，用于展示表格、K 线、趋势和组合分析结果。
- Harness，用于让 Agent 在金融任务中完成必要步骤后再总结。

## 推荐路径

### A. 交互式研究（Dashboard Chat）

1. 先通过 [模型配置](../getting-started/model-configuration.md) 配好 provider。
2. 启动 [Dashboard](dashboard.md)，确认金融数据 store / SDK 缓存能正常加载。
3. 用自然语言提出任务，例如市场概览、行业对比、ticker 分析或组合诊断。
4. 让 Agent 通过 **`dojo.sdk.*`（及 web / session 工具）** 读取数据；前端根据 `viz_blocks` 展示结构化结果。
5. 如果工具改变了组合或 session 数据，前端根据 `resource_changes` 刷新对应资源。

### B. 批处理任务

1. 确保 `tasks.enabled` 与 precompute 数据可用（见 [CLI](../reference/cli.md)）。
2. 运行流水线，例如：
   - `dojoagents tasks run --pipeline daily-market-events --date YYYY-MM-DD`
   - （设计中）Theme Deep Dive：单板块 `trading_date + market + (L1/L2/L3 | name)`
3. 用 `dojoagents tasks eval` 校验产物 schema。

### C. 组合工作流

组合创建 / 调仓 / 绩效仍可通过 Dashboard portfolio tools 与 Folio UI 完成（写路径暂留 Dashboard 工具面）。读行情与板块证据时优先 SDK。

## 路由对照（简表）

| 场景 | 优先工具族 |
| --- | --- |
| 板块定位 / 日收益 / 成分股 / alpha / theme_state | `dojo.sdk.*`（含待补 precomputed 工具） |
| 外网新闻归因 | `web_search` / `web_extract` |
| 任务产物 | `write_session_file` / `read_session_output` |
| 组合写入 | `portfolio_*`（Dashboard tools，暂留） |
| 页面展示与 HTTP | Dashboard REST（`/api/v1`），≠ Agent tool 名 |

## 相关页面

- [DojoSDK Reference](../reference/dojo-sdk.md)
- [任务与流水线](tasks-and-pipelines.md)
- [Tool Contracts](../reference/tool-contracts.md)
- [Agent Loop 架构](../architecture/agent-loop.md)
