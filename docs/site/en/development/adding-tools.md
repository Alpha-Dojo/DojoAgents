# Adding Tools

## Standard Path

1. Implement a tool module under `dojoagents/tools/`.
2. Define one or more `ToolSpec` objects.
3. Use async handlers returning `dict[str, Any]` or strings.
4. Register tools in `Runtime.from_config_store()` or through plugins.
5. Add focused tests.

## Notes

- Do not bypass `ToolExecutor`.
- Let the executor normalize result shapes.
- Side-effect tools should return `resource_changes`.
- Visualization tools should return `viz_blocks`.

