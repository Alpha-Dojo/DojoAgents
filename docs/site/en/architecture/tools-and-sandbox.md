# Tools and Sandbox

Tools are the standard interface for agent actions. Sandbox policy applies safety and timeout boundaries before execution.

## Components

| Component | Purpose |
| --- | --- |
| `ToolSpec` | Tool name, description, schema, handler, sandbox policy |
| `ToolRegistry` | Register and look up tools |
| `ToolExecutor` | Execute tools and normalize results |
| `SandboxPolicy` | Safety and timeout policy |

## Tool families

| Family | Registration | Notes |
| --- | --- | --- |
| `dojo.sdk.*` | `Runtime` → `get_dojo_sdk_specs()` | **Primary finance read path** (HF offline / qdata) |
| web | `get_web_searcher_specs()` | `web_search` / `web_extract` |
| session | write/read session file specs | Task and session artifacts |
| portfolio / domain | `register_dashboard_*_tools` (dashboard boot or tasks CLI) | Portfolio writes; domain finance reads are **legacy** — do not add new task deps |

Tool handlers return `dict[str, Any]` or strings. Results are normalized into `ToolResult` (`data`, `viz_blocks`, `artifacts`, `resource_changes`).

## Related code

- `dojoagents/tools/registry.py`
- `dojoagents/tools/executor.py`
- `dojoagents/tools/sandbox.py`
- `dojoagents/tools/dojo_sdk_tool.py`
- `dojoagents/tools/web_searcher.py`
- `dojoagents/tools/session_file_tool.py`
- `dojoagents/tools/agent_viz.py`
- `dojoagents/dashboard/tools/domain_tools.py` (legacy)
- `dojoagents/dashboard/tools/portfolio_tools.py`

## Further reading

- [DojoSDK](../reference/dojo-sdk.md)
- [Tasks and Pipelines](../user-guide/tasks-and-pipelines.md)
- [Adding Tools](../development/adding-tools.md)
