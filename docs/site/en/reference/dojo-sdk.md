# DojoSDK

## Principles (agent finance reads)

1. **The primary finance read path for agents and tasks is `dojo.sdk.*`** (`dojoagents/tools/dojo_sdk_tool.py` → `AsyncDojo`, HF offline / qdata).
2. **Dashboard domain tools and HTTP APIs are the product UI surface**, not task dependencies. New finance read capabilities belong in the SDK, not in `dashboard/tools/domain_tools.py`.
3. **Precompute outputs are consumed through SDK precomputed tools**: `dojoagents precompute-sector*` → `dojo_sector_precomputed` → `dojo.sdk.sector.precomputed_*`.

Non-finance tools (`web_search` / `web_extract`, `write_session_file` / `read_session_output`) stay in their own families and are not listed here.

## Status

DojoAgents exposes finance data tools through the `dojosdk` dependency and `dojoagents/tools/dojo_sdk_tool.py`.  
`get_dojo_sdk_specs()` registers only entries that appear in both `OFFLINE_TOOL_BINDINGS` and `HF_REGISTRY`.

Dashboard services may still use domain services / the Dojo data gateway for UI. That path is decoupled from agent SDK tools.

## Configuration

DojoSDK is managed in `pyproject.toml`. A local source override is supported:

```toml
[tool.uv.sources]
dojosdk = { path = "../DojoSDK" }
```

| Field | Purpose |
| --- | --- |
| `dojosdk` (`DojoSDKConfig`) | API key, base_url, timeout, retries |
| `dashboard.financial.sdk_cache_dir` | HF hub cache (default `~/.cache/huggingface/hub`) |

## Data flow

```text
precompute-sector / precompute-sector-theme-state
        │
        ▼
dojo_sector_precomputed/   (constituents, sector_daily, ticker_daily,
                            theme_state_daily, horizon, alpha factors, …)
        │
        ▼
AsyncDojo (HF offline / qdata)
        │
        ▼
dojo.sdk.*  ToolSpec  ←── Agent / Task (target primary path)
```

```text
Dashboard UI / REST (/api/v1/…)
        │
        ▼
FinancialDomainRegistry / stores
        │
        └── May share the same precompute bundle; tasks should not depend on domain_tools
```

## Registered `dojo.sdk.*` tools

| Tool | Capability | Typical use |
| --- | --- | --- |
| `dojo.sdk.sector.info` | Sector taxonomy (name / level / parent_id) | Weak resolve; **not** the primary L1/L2/L3 locator for precompute ids |
| `dojo.sdk.sector.symbol_relations` | Sector↔symbol relations | Coarse membership |
| `dojo.sdk.sector.precomputed_sector_alpha_factors_daily` | Sector alpha by date/market/L1–L3 | Quantitative support for drivers/risks |
| `dojo.sdk.sector.precomputed_ticker_alpha_factors_daily` | Ticker alpha by date/market/ticker/L1–L3 | Top-component ranking aid |
| `dojo.sdk.stock.news` | Per-ticker news (page / page_size) | Constituent news (needs date window) |
| `dojo.sdk.stock.event_remind` | Per-ticker event reminders | Corporate-event aid |
| `dojo.sdk.stock.ystock_info` | Stock profile | Role / industry aid |
| `dojo.sdk.stock.current_quote` | Live quotes | Live use; limited for historical `trading_date` |
| `dojo.sdk.stock.kline` | Equity klines | Single-name series; not sector contribution |
| `dojo.sdk.stock.fin_indicators` | Financial indicators | Fundamentals color |
| `dojo.sdk.stock.main_income` | Main-income breakdown | Optional |
| `dojo.sdk.benchmark.kline` | Benchmark klines | Relative market (prefer benchmark daily) |
| `dojo.sdk.analysis.market_dynamics` | Market-dynamics records | Optional macro context |
| `dojo.sdk.forex.kline` | Forex klines | Not used by sector theme tasks |

Code entry: `dojoagents/tools/dojo_sdk_tool.py` (`OFFLINE_TOOL_BINDINGS`).

## Gaps (vs Dashboard domain tools / Theme Deep Dive) {#sdk-gaps}

### P0 — Theme Deep Dive / minimal trigger loop

Minimal input: `trading_date + market + (level1_id+level2_id+level3_id | sector_name)`.  
Everything else (`change_percent`, direction, canonical names, contribution leaders) is fetched.

| Proposed capability | Replaces Dashboard tool | Notes |
| --- | --- | --- |
| `resolve_sector` / taxonomy search aligned to precompute L1/L2/L3 | `search_sector_taxonomy`, `get_taxonomy_tree` | Name→unique L3; candidates; ID validation |
| Filtered `precomputed_sector_daily` | `get_sector_movers` / analysis day return | Backfill `change_percent` / direction |
| Filtered `precomputed_constituents` | `filter_sector_constituents` membership | Members, weights, roles |
| Filtered `precomputed_ticker_daily` or merged `get_sector_members_with_returns` | Members + day returns | Top components / news fan-out list |
| `get_sector_contribution_leaders` (or in-SDK aggregate) | Mover leader concentration | `top_contributors` / `rally_type` |
| Date-window `stock.news` or `get_sector_constituent_news` | `get_ticker_news_and_events` (news) | Top-K batch + dedupe + `[T-2,T]` |

Note: `DojoSDKToolManager` already has some precomputed handlers (constituents / sector_daily / ticker_daily / theme_state) that are not in `OFFLINE_TOOL_BINDINGS` and often dump full tables. Add filters, then register.

### P1 — Driver / risk quality

| Proposed capability | Notes |
| --- | --- |
| Filtered `precomputed_theme_state_daily` | Breadth / RS / rotation / `stage_hint` |
| Filtered `precomputed_sector_horizon_metrics` | Mid/long mom, drawdown, PE percentiles |
| Filtered `precomputed_market_benchmark_daily` | Relative to market |
| Dated equity events | Filings / earnings evidence |

### P2 — If `daily-market-events` also moves to pure SDK

| Proposed capability | Replaces |
| --- | --- |
| Market-overview equivalent | `get_market_overview` |
| Sector-movers equivalent | `get_sector_movers` |

### Explicitly out of SDK

| Capability | Why |
| --- | --- |
| `web_search` / `web_extract` | Separate web tool family |
| `write_session_file` / `read_session_output` | Task artifact I/O |
| Portfolio write tools | Separate product surface; may remain in `portfolio_tools.py` for now |

## Error boundary

Dashboard Dojo data gateway errors live in `dojoagents/dashboard/services/dojo_data_gateway.py`:

- `GatewayError`
- `GatewayBadResponseError`
- `GatewayTimeoutError`
- `GatewayUnavailableError`
- `GatewayResult`

## Related pages

- [Tasks and Pipelines](../user-guide/tasks-and-pipelines.md)
- [Financial Workflows](../user-guide/financial-workflows.md)
- [CLI Reference](cli.md)
- [Tool Contracts](tool-contracts.md)
- [Adding Tools](../development/adding-tools.md)

## Further reading

Historical migration notes live under `docs/plans/` (not in site nav).
