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

### Default behavior

1. Use dashboard domain tools to fetch structured data.
2. Reuse `viz_blocks` already attached to tool results whenever they are present.
3. If a chart or table is still needed, call `agent_viz_build` with the tool data
   and an appropriate `kind` such as `bar`, `line`, `price_kline`, `table`,
   `hbar_rank`, `donut`, or `kpi_row`.
4. Keep the assistant text focused on interpretation and conclusions. Let the
   dashboard render the visualization blocks.

### Important rules

- Do NOT output `DOJO_CHART` fenced blocks.
- Do NOT output JavaScript, ECharts scripts, or HTML for chart rendering.
- Do NOT describe a chart as rendered unless a structured visualization tool has
  already produced the matching `viz_blocks`.
- Prefer one comparison chart over many redundant charts when summarizing the same dataset.

### Helpful tool patterns

- For cross-market valuation comparison, prefer a single `get_market_overview`
  call without `market` so the result covers US, CN, and HK together.
- For sector ranking, prefer `get_sector_movers` and render ranked bars or tables.
- For price trends, prefer `get_ticker_price_trends` or benchmark/ticker kline tools
  and render `price_kline` or `line` blocks.
""".strip()

# Backward-compatible alias for existing imports/tests. The content intentionally
# reflects the current structured-viz protocol instead of the legacy canvas flow.
DASHBOARD_CANVAS_PROTOCOL = DASHBOARD_VIZ_PROTOCOL
