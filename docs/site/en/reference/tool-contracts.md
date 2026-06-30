# Tool Contracts

Tool contracts are defined by `ToolSpec` and `ToolResult`.

## ToolSpec

| Field | Purpose |
| --- | --- |
| `name` | Tool name |
| `description` | Model-facing description |
| `parameters` | JSON schema |
| `handler` | Async handler |
| `sandbox_policy` | Sandbox policy name |

## ToolResult

Important fields include `content`, `error`, `data`, `viz_blocks`, `artifacts`, `resource_changes`, `latency_ms`, `truncated`, and `metadata`.

