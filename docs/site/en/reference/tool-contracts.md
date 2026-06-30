# Tool Contracts

Tool contracts are defined by `dojoagents/tools/registry.py::ToolSpec` and `dojoagents/agent/models.py::ToolResult`.

## ToolSpec

| Field | Purpose |
| --- | --- |
| `name` | Tool name registered in `ToolRegistry` |
| `description` | Model-facing capability description |
| `parameters` | JSON schema for tool arguments |
| `handler` | Async handler accepting `dict[str, Any]` |
| `sandbox_policy` | Sandbox policy name, default `default` |

`ToolSpec.schema()` exposes only `name`, `description`, and `parameters` to the model.

## ToolResult

| Field | Purpose |
| --- | --- |
| `call_id` | Tool call identifier |
| `name` | Tool name |
| `ok` | Whether execution succeeded |
| `content` | Text result for model and user surfaces |
| `error` | Error text for failed calls |
| `latency_ms` | Execution latency |
| `truncated` | Whether output was truncated |
| `data` | Structured data payload |
| `viz_blocks` | Agent visualization blocks |
| `artifacts` | Produced artifact references |
| `resource_changes` | Resource-change notices for frontend refresh |
| `metadata` | Extra metadata |

`ToolResult.to_message()` converts the result into an OpenAI-compatible `tool` message. Successful calls use `content`; failed calls use `error`.

## Handler Results

Handlers should return a `dict[str, Any]` or a string compatible with `ToolExecutor._coerce_result()`. Exceptions are caught by `ToolExecutor.execute_one()`, logged with the unified logger, and converted into failed `ToolResult` objects.

## Resource Refresh

Frontend code should prefer `resource_changes` when deciding what to refresh. It should not infer side effects from tool names when the tool can report the affected resource directly.

## Code Anchors

- `dojoagents/tools/registry.py`
- `dojoagents/tools/executor.py`
- `dojoagents/agent/models.py`
