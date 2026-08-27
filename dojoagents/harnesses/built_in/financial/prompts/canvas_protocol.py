"""Dashboard visualization protocol for the current chat UI.

The dashboard chat surface renders structured ``viz_blocks`` from tool results.
Unlike the legacy Canvas panel, the current React source does not render
``DOJO_CHART`` fenced blocks, so the dashboard prompt must steer the model
toward structured visualization outputs only.
"""

from __future__ import annotations

DASHBOARD_VIZ_PROTOCOL = """
## Dashboard Visualization Protocol

This dashboard chat renders structured `viz_blocks` from tool results. Prefer the
existing visualization pipeline over free-form chart code.

### agent_viz_build data shapes (escape hatch only)

Call `agent_viz_kinds` to list supported kinds. Prefer reusing `viz_blocks` already attached to
data-tool / `execute_code` results. Use `agent_viz_build` **only when auto viz_blocks are missing
or the wrong chart type**. The JSON examples below are shapes for that escape hatch — not a
required second step after every computation.

**price_kline** — OHLC history (`mapping_hint`: `ticker_kline`, or pass `klines` with `kind=auto`):
```json
{"kind":"auto","source_tool":"get_ticker_price_trends","data":{"ticker":"SNDK","market":"us","klines":[{"datetime":"2025-01-02","open":150,"high":155,"low":148,"close":152}]}}
```

**line** — time series / NAV / drawdown curves:
```json
{"kind":"line","data":{"title":"NAV","series":[{"id":"nav","label":"NAV","points":[{"date":"2025-01-02","value":1.0},{"date":"2025-01-03","value":1.02}]}]}}
```

**kpi_row** — compact headline metrics:
```json
{"kind":"kpi_row","data":{"metrics":[{"label":"Max drawdown","value":"17.50%","trend":"down"},{"label":"Total return","value":"+12.3%","trend":"up"}]}}
```

**table** — rankings / holdings / screen results:
```json
{"kind":"table","data":{"columns":[{"key":"ticker","label":"Ticker"},{"key":"score","label":"Score"}],"rows":[{"ticker":"AAPL","score":98}]}}
```

**bar** — category comparison:
```json
{"kind":"bar","data":{"categories":["US","CN","HK"],"series":[{"label":"Weighted PE","values":[23.7,17.2,10.4]}]}}
```

**hbar_rank** — gainers/losers:
```json
{"kind":"hbar_rank","data":{"gainers":[{"label":"NVDA","value":5.2}],"losers":[{"label":"TSLA","value":-3.1}]}}
```

**donut** — allocation weights:
```json
{"kind":"donut","data":{"slices":[{"key":"us","label":"US","value":60},{"key":"hk","label":"HK","value":40}]}}
```

**sparkline** — mini trend:
```json
{"kind":"sparkline","data":{"values":[1,2,3,2,4],"change_percent":2.5}}
```

**quote_card** — single-ticker snapshot:
```json
{"kind":"quote_card","data":{"ticker":"AAPL","market":"us","last_price":200,"change_percent":1.5}}
```

**timeline** — news/events:
```json
{"kind":"timeline","data":{"news":[{"date":"2025-01-02","title":"Earnings beat","summary":"..."}]}}
```

### execute_code → after computation (MANDATORY)

When computation in `execute_code` has already produced the numbers you need:

1. Write conclusions, key metrics, and caveats in assistant markdown.
2. **Stop.** Do NOT start another `execute_code` round only to package charts.
3. **FORBIDDEN:** print `=== VIZ_DATA ===` / chart JSON from `execute_code`.
4. **FORBIDDEN:** call `agent_viz_build` or `agent_viz_kinds` to finish an analysis turn.
5. Do NOT debug calendar NaNs, reindex, or series alignment solely to build visualization payloads.

### Default behavior

Visualization policy is defined in the **Visualization policy** system section
(scene IDs such as `portfolio_mutating_task`, `exploratory_read_analysis`). Follow that matrix.

1. Use dashboard domain tools to fetch structured data.
2. Deliver analysis as markdown conclusions. Charts are not a required deliverable.
3. When the scene is **forbidden** (portfolio writes, eval accepted, trade confirmations),
   summarize in markdown only — do NOT call `agent_viz_build`.
4. Keep assistant text focused on interpretation; do not duplicate markdown tables as kpi_row.

### Important rules

- Do NOT output `DOJO_CHART` fenced blocks.
- Do NOT output JavaScript, ECharts scripts, or HTML for chart rendering.
- Do NOT describe a chart as rendered unless a structured visualization tool has
  already produced the matching `viz_blocks`.
- Prefer one comparison chart over many redundant charts when summarizing the same dataset.

### Helpful tool patterns

- For cross-market valuation comparison, prefer a single `get_market_overview`
  call without `market` so the result covers US, CN, and HK together.
  Use `days` for recent N trade sessions, `as_of`+`days` for N sessions ending on a date
  (non-trading as_of falls back; days defaults to 1), or `start_date`+`end_date` for a fixed calendar range
  (cannot combine with as_of; read `window_start`/`window_end` from the response).
- For sector ranking, prefer `get_sector_movers` with the same window args and render
  ranked bars or tables. Copy taxonomy ids from movers into follow-up sector tools.
- For price trends, prefer `get_ticker_price_trends`. For one trading day, set both
  `start_date` and `end_date` to that date (e.g. `2026-06-18`). Omit dates only for full
  history since 2025-01-01.

### execute_code data fidelity (MANDATORY)

When Python computation is required:

1. NEVER hardcode OHLC prices, financial statement rows, or quote values in `execute_code`.
2. Fetch live data inside the script via `import dojo_tools` — e.g.
   `dojo_tools.get_ticker_price_trends({"ticker": "0700", "market": "hk", "start_date": "2025-01-01"})`.
3. For large prior tool outputs, use `dojo_tools.load_tool_result(call_id)` instead of
   copying JSON from memory. The artifact pointer includes `schema_hint` and `parse_hint`.
4. Parse tool payloads with `dojo_tools.tool_json(res)`; metadata scalars via
   `dojo_tools.tool_meta(res)` (as_of, match_count, … — NOT on the RPC wrapper `res`).
   Prefer `dojo_tools.tool_print(res)` or `dojo_tools.tool_print(res, table='benchmarks')`
   for tabular output; use `dojo_tools.tool_pick(df, columns)` to avoid KeyError.
   Example:
   `res = dojo_tools.load_tool_result(call_id); dojo_tools.tool_print(res, table='items')`
   Kline rows use field `datetime` for the trade date (fields: datetime, open, high, low, close, volume).

### execute_code misuse (FORBIDDEN)

Do NOT call `execute_code` to:

- print ASCII boxes, taxonomy tables, or knowledge-graph schema docs
- format design proposals or multi-section text reports via `print()`
- substitute for normal assistant markdown when no computation is needed

For analysis, design, and interpretation turns, write deliverables directly in the assistant
message. Do NOT print `VIZ_DATA` or call visualization tools just to finish the answer.
`execute_code` is only for dojo_tools batch orchestration and pandas/numpy computation on fetched data.
""".strip()

# Backward-compatible alias for existing imports/tests. The content intentionally
# reflects the current structured-viz protocol instead of the legacy canvas flow.
DASHBOARD_CANVAS_PROTOCOL = DASHBOARD_VIZ_PROTOCOL
