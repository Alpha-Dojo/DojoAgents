# Tools and Sandbox

Tools are the standard interface for agent actions. Sandbox policy applies safety and timeout boundaries before execution.

## Components

| Component | Purpose |
| --- | --- |
| `ToolSpec` | Tool name, description, schema, handler, sandbox policy |
| `ToolRegistry` | Register and look up tools |
| `ToolExecutor` | Execute tools and normalize results |
| `SandboxPolicy` | Safety and timeout policy |

Tool handlers return `dict[str, Any]` or strings. Results are normalized into `ToolResult`.

