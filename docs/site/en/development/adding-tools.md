# Adding Tools

## Standard path (generic tools)

1. Implement a tool module under `dojoagents/tools/`.
2. Define one or more `ToolSpec` objects.
3. Use async handlers returning `dict[str, Any]` or strings.
4. Register tools in `Runtime.from_config_store()` or through plugins.
5. Add focused tests.

## Finance read tools (preferred)

For new market / sector / precompute / news **read** capabilities:

1. Prefer adding an `OFFLINE_TOOL_BINDINGS` entry in `dojoagents/tools/dojo_sdk_tool.py` (or a sibling SDK wrapper module).
2. Support **filtered queries** (date / market / L1–L3 / ticker); avoid full-table dumps.
3. Cover registration and calls in `tests/test_dojo_sdk_tool.py` (or sibling tests).
4. Update the [DojoSDK](../reference/dojo-sdk.md) catalog.

**Do not** add new agent finance-read dependencies to `dashboard/tools/domain_tools.py`.

## Dashboard tools (limited)

| Kind | Path | When |
| --- | --- | --- |
| Portfolio writes | `dashboard/tools/portfolio_tools.py` | Portfolio mutations (kept for now) |
| Domain reads | `dashboard/tools/domain_tools.py` | **Legacy** only; do not add new task deps |

Registration: `register_dashboard_domain_tools` / `register_dashboard_portfolio_tools` (`dashboard/server.py`, tasks CLI).

## Notes

- Do not bypass `ToolExecutor`.
- Let the executor normalize result shapes.
- Side-effect tools should return `resource_changes`.
- Visualization tools should return `viz_blocks`.
