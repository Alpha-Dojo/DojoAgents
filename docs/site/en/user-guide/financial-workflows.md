# Financial Workflows

DojoAgents is built around quantitative finance workflows: market data lookup, sector/theme analysis, portfolio construction and validation, structured task batching, reporting, and visualization.

## Capabilities

- **`dojo.sdk.*` finance reads** (primary path for agents and tasks). See [DojoSDK](../reference/dojo-sdk.md).
- **Structured tasks / pipelines** (daily market events, Theme Deep Dive). See [Tasks and Pipelines](tasks-and-pipelines.md).
- Dashboard financial services and stores (**UI / REST**; not dependencies for new tasks).
- `resource_changes` for UI refresh.
- `viz_blocks` for tables, K-lines, trend charts, and KPI cards.
- Harness logic for finance-specific completion checks.

## Recommended paths

### A. Interactive research (Dashboard chat)

1. Configure a provider through [Model Configuration](../getting-started/model-configuration.md).
2. Start the [Dashboard](dashboard.md) and confirm financial stores / SDK cache load.
3. Ask for market overview, sector comparison, ticker analysis, or portfolio diagnostics.
4. Let the agent read data through **`dojo.sdk.*` (plus web / session tools)**; the frontend renders structured output through `viz_blocks`.
5. When a tool changes portfolio or session data, refresh affected resources using `resource_changes`.

### B. Batch tasks

1. Ensure `tasks.enabled` and precompute data are available (see [CLI](../reference/cli.md)).
2. Run a pipeline, for example:
   - `dojoagents tasks run --pipeline daily-market-events --date YYYY-MM-DD`
   - (Designed) Theme Deep Dive: one sector with `trading_date + market + (L1/L2/L3 | name)`
3. Validate artifacts with `dojoagents tasks eval`.

### C. Portfolio workflows

Portfolio create / rebalance / performance can still use Dashboard portfolio tools and the Folio UI (write path remains on the Dashboard tool surface for now). Prefer SDK for market and sector evidence reads.

## Routing cheat sheet

| Scenario | Prefer |
| --- | --- |
| Sector resolve / day return / members / alpha / theme_state | `dojo.sdk.*` (including planned precomputed tools) |
| External news attribution | `web_search` / `web_extract` |
| Task artifacts | `write_session_file` / `read_session_output` |
| Portfolio writes | `portfolio_*` (Dashboard tools, for now) |
| UI and HTTP | Dashboard REST (`/api/v1`), not agent tool names |

## Related pages

- [DojoSDK Reference](../reference/dojo-sdk.md)
- [Tasks and Pipelines](tasks-and-pipelines.md)
- [Tool Contracts](../reference/tool-contracts.md)
- [Agent Loop](../architecture/agent-loop.md)
