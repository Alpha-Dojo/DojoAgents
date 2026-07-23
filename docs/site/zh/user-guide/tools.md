# Tools

## 适用场景

Tools 是 Agent 调用外部能力的标准入口，包括代码执行、终端、MCP、DojoSDK、Web search、技能管理、插件管理和可视化构建。

## 工具结果

工具处理函数返回的数据会被 `ToolExecutor` 规范化为 `ToolResult`。Dashboard 和 SSE 会消费其中的：

- `content`
- `data`
- `viz_blocks`
- `artifacts`
- `resource_changes`
- `latency_ms`
- `error`

## 用户侧观察

在 Dashboard 中，工具调用会出现在 Agent 活动流中；如果工具返回 `viz_blocks`，前端可以渲染表格、K 线、图表或指标卡。

## 深入阅读

- [Tools 与 Sandbox 架构](../architecture/tools-and-sandbox.md)
- [Tool Contracts](../reference/tool-contracts.md)
- [DojoSDK](../reference/dojo-sdk.md)
- [任务与流水线](tasks-and-pipelines.md)
- [添加工具](../development/adding-tools.md)

