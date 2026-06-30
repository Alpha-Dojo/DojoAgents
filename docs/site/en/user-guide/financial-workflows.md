# Financial Workflows

DojoAgents is built around quantitative finance workflows such as market data lookup, sector analysis, portfolio construction, portfolio validation, reporting, and visualization.

## Capabilities

- DojoSDK tool integration.
- Dashboard financial services and stores.
- `resource_changes` for UI refresh.
- `viz_blocks` for tables, K-lines, trend charts, and KPI cards.
- Harness logic for finance-specific completion checks.

## Recommended Path

1. Configure a provider through [Model Configuration](../getting-started/model-configuration.md).
2. Start the [Dashboard](dashboard.md) and confirm financial stores load.
3. Ask for market overview, sector comparison, ticker analysis, or portfolio diagnostics.
4. Let the agent read data through tools; the frontend renders structured output through `viz_blocks`.
5. When a tool changes portfolio or session data, refresh affected resources using `resource_changes`.

## Related Pages

- [DojoSDK Reference](../reference/dojo-sdk.md)
- [Tool Contracts](../reference/tool-contracts.md)
- [Agent Loop](../architecture/agent-loop.md)
