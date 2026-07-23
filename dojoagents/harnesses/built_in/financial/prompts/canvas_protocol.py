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

### agent_viz_build data shapes (JSON examples)

Call `agent_viz_kinds` to list supported kinds. Prefer reusing `viz_blocks` already attached to
data-tool results. Use explicit `kind` when the target chart type is known.

**price_kline** — OHLC history (`mapping_hint`: `ticker_kline`, or pass `klines` with `kind=auto`):
```json
{"kind":"auto","source_tool":"get_ticker_price_trends","data":{"ticker":"SNDK","market":"us","klines":[{"datetime":"2025-01-02","open":150,"high":155,"low":148,"close":152}]}}
```

**line** — time series / NAV / drawdown curves:
```json
{"kind":"line","data":{"title":"NAV","series":[{"id":"nav","label":"NAV","points":[{"date":"2025-01-02","value":1.0},{"date":"2025-01-03","value":1.02}]}]}}
```

**drawdown_analysis** — execute_code `VIZ_DATA` (`dates` + `prices` + optional `drawdown_pcts`):
```json
{"mapping_hint":"drawdown_analysis","kind":"auto","data":{"dates":["2025-01-02","2025-01-03"],"prices":[150.0,145.0],"drawdown_pcts":[0.0,-3.3],"summary":{"ticker":"SNDK","max_drawdown_pct":17.5}}}
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

### execute_code → visualization workflow

1. After computation, print structured `VIZ_DATA` JSON (see drawdown example above).
2. The tool result includes a `--- viz_hint ---` footer describing how to call `agent_viz_build`.
3. Pass the parsed `VIZ_DATA` object as `agent_viz_build.data` with `mapping_hint=drawdown_analysis`.
4. Do NOT pass raw stdout text or nested `data['data']` wrappers to `agent_viz_build`.

### Default behavior

Visualization policy is defined in the **Visualization policy** system section
(scene IDs such as `portfolio_mutating_task`, `exploratory_read_analysis`). Follow that matrix.

1. Use dashboard domain tools to fetch structured data.
2. **Prefer auto-attached `viz_blocks`** on data-tool results — no extra tool call.
3. Call `agent_viz_build` only when the active viz-policy scene is **encouraged** or **optional**
   AND the chart adds information auto blocks cannot express.
4. When the scene is **forbidden** (portfolio writes, eval accepted, trade confirmations),
   summarize in markdown only — do NOT call `agent_viz_build`.
5. Keep assistant text focused on interpretation; do not duplicate markdown tables as kpi_row.

### Important rules

- Do NOT output `DOJO_CHART` fenced blocks.
- Do NOT output JavaScript, ECharts scripts, or HTML for chart rendering.
- Do NOT describe a chart as rendered unless a structured visualization tool has
  already produced the matching `viz_blocks`.
- Prefer one comparison chart over many redundant charts when summarizing the same dataset.

### Helpful tool patterns

- For cross-market valuation comparison, prefer a single `get_market_overview`
  call without `market` so the result covers US, CN, and HK together.
  Use `days` for recent N trade days, or `start_date`+`end_date` for a fixed range
  (dates override days; read `window_start`/`window_end` from the response).
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
message. Use `agent_viz_build` for charts/tables. `execute_code` is only for dojo_tools batch
orchestration and pandas/numpy computation on fetched data.
""".strip()

# Backward-compatible alias for existing imports/tests. The content intentionally
# reflects the current structured-viz protocol instead of the legacy canvas flow.
DASHBOARD_CANVAS_PROTOCOL = DASHBOARD_VIZ_PROTOCOL
