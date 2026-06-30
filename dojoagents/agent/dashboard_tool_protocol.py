"""Precise dashboard tool calling guidelines injected into the agent system prompt."""

from __future__ import annotations

DASHBOARD_TOOL_PROTOCOL = """
## Dashboard Tool Calling Protocol (MANDATORY)

Pick the workflow by user intent. Do NOT default to search_company_ticker or web_search for stock picking.

### Task routing (choose ONE path)

| User intent | Required tools (in order) | Do NOT use |
|-------------|---------------------------|------------|
| Theme / concept / industry basket (具身智能, 机器人, 半导体, AI…) | `search_sector_taxonomy` → `filter_sector_constituents` (per market) → optional `get_ticker_financials` batch → portfolio writes | `search_company_ticker`, `web_search` as primary discovery |
| Sector analysis / compare industries | `get_taxonomy_tree` or `search_sector_taxonomy` → `get_sector_analysis` | Guessing sector ids |
| Full-market screen (市值/PE/涨跌幅 filters, no specific sector) | `screen_market_stocks` per market → optional `get_ticker_financials` | `filter_sector_constituents` without taxonomy match |
| Resolve one company name → ticker | `search_company_ticker` (single q, known name) | Repeated keyword searches |
| Single stock deep dive | `get_ticker_realtime_quote`, `get_ticker_financials`, `get_ticker_price_trends` | — |

### Theme / concept stock picking (e.g. 具身智能, 高息, 半导体)

Concept names are NOT tickers. `search_company_ticker("具身智能")` or `search_company_ticker("Tesla")` will NOT return a complete universe.

**Required workflow:**

1. `search_sector_taxonomy` with the user's concept and close synonyms
   (e.g. 具身智能 → also try 机器人, 自动化, robotics, industrial automation).
2. From matches, pick the best L3 sector (`best_match` or highest `match_score`).
3. For each target market (`us`, `cn`, `hk`), call `filter_sector_constituents`
   with `sector_path_id` or the three ids from step 2 — do NOT pass sector names.
4. Apply numeric filters on the result set:
   - market cap: use `min_market_cap` in `screen_market_stocks` only if you pivoted to market-wide screen;
     otherwise filter constituent rows by `market_cap` field.
   - profitability: batch `get_ticker_financials` on candidate tickers, keep net_profit > 0.
5. Portfolio: `portfolio_write_create` → `portfolio_write_add_holdings` (batch) →
   `portfolio_read_detail` (read `eval_summary`) → `portfolio_eval_submit` with criteria **≤ actual counts**.

**Eval rules (avoid retry loops):**
- `min_candidates_by_market` must come from `portfolio_read_detail.eval_summary`, NOT from pre-filter estimates.
- Do NOT invent per-market minimums (e.g. US≥40) unless the user explicitly asked for a count.
- If `add_result.skipped_duplicates` is non-empty, those tickers did NOT increase the count — pick new symbols.
- After eval failure: fix only the gap; do NOT re-print the full portfolio report.

**Optional:** `get_sector_analysis` on the chosen path for sector-level context before picking names.

### Sector taxonomy ids

1. `search_sector_taxonomy` with the user's concept (synonyms auto-expanded: 具身智能 → 机器人, robotics…).
2. Copy `sector_path_id` OR `level1_id` + `level2_id` + `level3_id` verbatim from `best_match` — exact ID lookup, no guessing.
3. `filter_sector_constituents` with those ids + `market` + `scope: "L3"`.
4. `get_sector_analysis` with the same ids when sector-level stats are needed.

### search_company_ticker — ONLY for single-name resolution

Use when the user names ONE company or ticker (Apple, 茅台, 0700.HK).
FORBIDDEN as stock-universe builder:
- thematic keywords (具身智能, 机器人, embodied AI)
- looping famous names (NVIDIA, Tesla, BYD) to assemble a concept basket
- replacing `filter_sector_constituents` or `screen_market_stocks`

### web_search — supplementary only

Use for news/macro context AFTER dashboard tools return candidates.
FORBIDDEN as the primary way to discover investable tickers when sector/screen tools exist.

### Portfolio tools

**Create / populate:** create → add_holdings (batch) → read_detail → eval_submit
**Delete:** read_list → write_delete → done (no read_detail, no eval_submit)

### Batch calls

- `get_ticker_realtime_quote` / `get_ticker_financials`: pass all tickers in one `tickers` array (≤50).
""".strip()
