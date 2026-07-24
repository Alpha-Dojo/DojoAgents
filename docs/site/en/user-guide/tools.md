# Tools

Tools are the standard way for agents to execute external capabilities, including code execution, terminal access, MCP, DojoSDK, web search, skill management, plugin management, and visualization building.

## Tool Results

`ToolExecutor` normalizes tool handler output into `ToolResult`, including:

- `content`
- `data`
- `viz_blocks`
- `artifacts`
- `resource_changes`
- `latency_ms`
- `error`

Dashboard renders tool activity and visualization blocks from these fields.

## Related pages

- [Tools and Sandbox](../architecture/tools-and-sandbox.md)
- [Tool Contracts](../reference/tool-contracts.md)
- [DojoSDK](../reference/dojo-sdk.md)
- [Tasks and Pipelines](tasks-and-pipelines.md)
- [Adding Tools](../development/adding-tools.md)

