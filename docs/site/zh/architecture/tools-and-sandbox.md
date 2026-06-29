# Tools 与 Sandbox

## 目标

Tools 是 Agent 执行外部动作的标准接口；Sandbox 负责在执行前应用安全策略和超时边界。

## 组件

| 组件 | 说明 |
| --- | --- |
| `ToolSpec` | 工具名称、描述、参数 schema、handler、sandbox policy |
| `ToolRegistry` | 注册、查找、列出工具 |
| `ToolExecutor` | 执行工具、捕获异常、规范化结果 |
| `SandboxPolicy` | 工具调用安全和超时策略 |

## 工具结果

工具 handler 返回 `dict[str, Any]` 或字符串，最终会被规范化为 `ToolResult`。结构化字段包括 `data`、`viz_blocks`、`artifacts`、`resource_changes`。

## 相关代码

- `dojoagents/tools/registry.py`
- `dojoagents/tools/executor.py`
- `dojoagents/tools/sandbox.py`
- `dojoagents/tools/dojo_sdk_tool.py`
- `dojoagents/tools/web_searcher.py`
- `dojoagents/tools/agent_viz.py`

