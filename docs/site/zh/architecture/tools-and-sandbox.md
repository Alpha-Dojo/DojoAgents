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

## 工具族

| 族 | 注册位置 | 说明 |
| --- | --- | --- |
| `dojo.sdk.*` | `Runtime` → `get_dojo_sdk_specs()` | **金融只读主路径**（HF offline / qdata） |
| web | `get_web_searcher_specs()` | `web_search` / `web_extract` |
| session | `get_write_session_file_spec` / `get_read_session_output_spec` | 任务与会话产物 |
| portfolio / domain | `register_dashboard_*_tools`（dashboard 启动或 tasks CLI） | 组合写路径；domain 金融读为 **legacy**，新 Task 勿新增依赖 |

## 工具结果

工具 handler 返回 `dict[str, Any]` 或字符串，最终会被规范化为 `ToolResult`。结构化字段包括 `data`、`viz_blocks`、`artifacts`、`resource_changes`。

## 相关代码

- `dojoagents/tools/registry.py`
- `dojoagents/tools/executor.py`
- `dojoagents/tools/sandbox.py`
- `dojoagents/tools/dojo_sdk_tool.py`
- `dojoagents/tools/web_searcher.py`
- `dojoagents/tools/session_file_tool.py`
- `dojoagents/tools/agent_viz.py`
- `dojoagents/dashboard/tools/domain_tools.py`（legacy）
- `dojoagents/dashboard/tools/portfolio_tools.py`

## 深入阅读

- [DojoSDK](../reference/dojo-sdk.md)
- [任务与流水线](../user-guide/tasks-and-pipelines.md)
- [添加工具](../development/adding-tools.md)
