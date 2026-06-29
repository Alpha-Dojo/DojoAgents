# Tool Contracts

## 状态

工具契约以 `dojoagents/tools/registry.py::ToolSpec` 和 `dojoagents/agent/models.py::ToolResult` 为准。

## ToolSpec

| 字段 | 说明 |
| --- | --- |
| `name` | 工具名 |
| `description` | 给模型看的能力说明 |
| `parameters` | JSON schema 参数 |
| `handler` | async handler |
| `sandbox_policy` | sandbox 策略名 |

## ToolResult

| 字段 | 说明 |
| --- | --- |
| `call_id` | 工具调用 ID |
| `name` | 工具名 |
| `ok` | 是否成功 |
| `content` | 面向模型和用户的文本 |
| `error` | 错误文本 |
| `latency_ms` | 执行耗时 |
| `truncated` | 内容是否截断 |
| `data` | 结构化数据 |
| `viz_blocks` | Agent visualization blocks |
| `artifacts` | 产物引用 |
| `resource_changes` | 资源变更通知 |
| `metadata` | 额外元数据 |

## Handler 返回值

handler 应返回 `dict[str, Any]` 或字符串；异常由 `ToolExecutor.execute_one()` 捕获、记录并转成失败 `ToolResult`。

## 资源刷新

前端应优先根据 `resource_changes` 刷新缓存，而不是按工具名猜测副作用。

