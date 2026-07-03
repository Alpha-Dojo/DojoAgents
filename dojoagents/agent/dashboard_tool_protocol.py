"""Precise dashboard tool calling guidelines injected into the agent system prompt."""

from __future__ import annotations

DASHBOARD_TOOL_PROTOCOL = """
## Dashboard Tool Calling Protocol (MANDATORY)

Pick the workflow by user intent. Do NOT default to search_company_ticker or web_search for stock picking.

### Multi-turn sessions (CRITICAL — avoid intent drift)

Each user message is a **new, independent task**. Prior turns are closed context.

- If the **latest message** asks to **analyze / 分析 / 解读 / 怎么样** an existing portfolio or its candidates:
  use read + financial tools only (`portfolio_read_search`, `portfolio_read_detail`, `get_ticker_financials`, …).
  **Do NOT** call `portfolio_write_create`, batch add candidates, or `portfolio_eval_submit`.
- If the **latest message** asks to **create / 创建 / 选股 / 建组合**:
  use the portfolio build workflow below.
- Never resume a prior turn's unfinished create/build work unless the **current message** explicitly asks.

When session history mentions an old portfolio task, treat it as **already done** unless the user repeats that request now.

### Task routing (choose ONE path per message)

| User intent | Required tools (in order) | Do NOT use |
|-------------|---------------------------|------------|
| Theme / concept / industry basket (具身智能, 机器人, 半导体, AI…) | `search_sector_taxonomy` → `filter_sector_constituents` (per market) → optional `get_ticker_financials` batch → portfolio writes | `search_company_ticker`, `web_search` as primary discovery |
| Sector analysis / compare industries | `get_taxonomy_tree` or `search_sector_taxonomy` → `get_sector_analysis` | Guessing sector ids |
| Full-market screen (市值/PE/涨跌幅 filters, no specific sector) | `screen_market_stocks` per market → optional `get_ticker_financials` | `filter_sector_constituents` without taxonomy match |
| Resolve one company name → ticker | `search_company_ticker` (single q, known name) | Repeated keyword searches |
| Analyze existing portfolio / 候选池成分分析 | `portfolio_read_search` → `portfolio_read_detail` → `get_ticker_financials` batch → answer | `portfolio_write_create`, add candidates, eval_submit |
| Single stock deep dive | `get_ticker_realtime_quote`, `get_ticker_financials`, `get_ticker_price_trends` (pass `start_date`/`end_date`; same day for one bar) | — |

### Analyze portfolio candidates (分析候选池 / 成分股怎么样)

Read-only workflow — no portfolio writes:

1. `portfolio_read_search` with portfolio name from the user
2. `portfolio_read_detail` for candidates list
3. Batch `get_ticker_financials` (and optional quotes) on candidate tickers
4. Summarize quality, valuation, risks — **stop**. No create, no eval_submit.

### Theme / concept stock picking (e.g. 具身智能, 高息, 半导体)

Concept names are NOT tickers. `search_company_ticker("具身智能")` or `search_company_ticker("Tesla")` will NOT return a complete universe.

**Required workflow:**

1. `search_sector_taxonomy` with the user's concept and close synonyms
   (e.g. 具身智能 → also try 机器人, 自动化, robotics, industrial automation).
2. From matches, pick the best L3 sector (`best_match` or highest `match_score`).
3. For each target market (`us`, `cn`, `hk`), call `filter_sector_constituents`
   with the full `sector_path_id` (three segments) or all three ids from step 2.
   Use `scope: "L2"` to list the whole L2 branch — never shorten the path to two segments (e.g. `1/2`).
4. Apply numeric filters on the result set:
   - market cap: use `min_market_cap` in `screen_market_stocks` only if you pivoted to market-wide screen;
     otherwise filter constituent rows by `market_cap` field.
   - profitability: batch `get_ticker_financials` on candidate tickers, keep net_profit > 0.
5. Portfolio watchlist (选股/候选池): `portfolio_write_create` → `portfolio_write_add_candidates` →
   `portfolio_read_detail` (read `eval_summary.candidate_count`) → `portfolio_eval_submit` with **min_candidate_count**.

**Eval rules (avoid retry loops):**
- `min_candidates_by_market` must come from `portfolio_read_detail.eval_summary`, NOT from pre-filter estimates.
- Do NOT invent per-market minimums (e.g. US≥40) unless the user explicitly asked for a count.
- If `add_result.skipped_duplicates` is non-empty, those tickers did NOT increase the count — pick new symbols.
- After eval failure: fix only the gap; do NOT re-print the full portfolio report.

**Optional:** `get_sector_analysis` on the chosen path for sector-level context before picking names.

### Portfolio: candidates vs positions (CRITICAL)

| Concept | UI label | Meaning | Tool | Eval field |
|---------|----------|---------|------|------------|
| Watchlist | 候选股 | Track symbols, no capital spent | `portfolio_write_add_candidate(s)` | `min_candidate_count` |
| Filled buy | 持仓 / 建仓 | Spend capital at price × qty | `portfolio_write_create_order(s)` | `min_position_count` |
| Filled sell / 清仓 | 卖出 / 清仓 | Reduce or close positions via orders | `portfolio_write_create_order(s)` sell | `max_position_count=0` |

**User says 清仓 / 全部卖出 / liquidate all (existing portfolio):**
1. `portfolio_read_search` or `portfolio_read_list` → target portfolio_id
2. `portfolio_read_detail` → read current positions (shares per ticker)
3. `portfolio_write_create_orders` with `order_side=sell` for each held ticker.
   - **清仓 intent:** omit `qty` — server defaults to all held shares per ticker.
   - **Partial sell without qty:** server stops and asks the user (suggest 50%, 75%, 100% via `qty_pct`).
   - Optional explicit sizing: `qty` (shares) or `qty_pct` (0.5 = 50%) or `liquidate_all=true`.
4. `portfolio_read_detail` → verify `eval_summary.position_count` is **0**
5. `portfolio_eval_submit` with **max_position_count=0** and **require_kind_agent=false**
   (manual portfolios are never `require_kind_agent=true` unless you used `portfolio_write_create` this run).

**Do NOT for 清仓:** `portfolio_write_add_candidate`, `portfolio_write_create`, or `require_kind_agent=true`.

**User says 卖出 / 减仓 (partial, no qty given):**
- Do NOT guess share count. Wait for user to pick 50%, 75%, 100%, or an exact `qty`.
- After confirmation, call `portfolio_write_create_order(s)` with `qty` or `qty_pct`.

**User says 建仓 / 买入 / 按成本价 / 创建交易 / 持仓页面截图 with shares & cost:**
1. `portfolio_read_search` or `portfolio_read_list` → target portfolio_id
2. If price/date is specified (e.g. 2026-06-18 开盘价): call `get_ticker_price_trends` with
   `start_date` AND `end_date` both set to that day (YYYY-MM-DD), then read `open` from klines.
   Do NOT call kline tools with only ticker/kline_t — that returns the full history.
3. Call `portfolio_write_create_order` (or batch) with `ticker` + `order_side=buy`.
   Optional fields — server resolves defaults:
   - no `order_time` + no `price` → latest daily **close**
   - `order_time` only → that day's **open**
   - `price` only → nearest day where price is within daily low/high
   - no `qty` on buy → **10%** of available market cash (lot-normalized)
   - US qty: integer shares; HK/A-share qty: multiples of 100
   - limit price must be within the trade day's high/low (preflight rejects otherwise)
4. `portfolio_read_detail` → verify `eval_summary.position_count` (NOT candidate_count)
5. `portfolio_eval_submit` with **min_position_count** matching filled positions

**Capital preflight (batch 建仓):**
- Before large batch buys, ensure `Σ(price × qty)` per market fits `capital_by_market`.
- If the tool returns `capital_budget_exceeded`, **stop** and ask the user whether to raise
  Folio initial capital or reduce symbols/share counts. Do NOT silently lower qty.
- A-share min lot is 100 shares; do not auto-reduce below user-requested sizing.

**FORBIDDEN for 建仓:** `portfolio_write_add_candidate`, `portfolio_write_add_holding`, `portfolio_write_add_holdings`
(these only add 候选股; they never buy or set cost).

**Theme basket without 建仓:** use add_candidates only — positions stay 0 until user asks to buy.

### Sector taxonomy ids

1. `search_sector_taxonomy` with the user's concept (synonyms auto-expanded: 具身智能 → 机器人, robotics…).
2. Copy `sector_path_id` OR `level1_id` + `level2_id` + `level3_id` verbatim from `best_match` — exact ID lookup, no guessing.
3. `filter_sector_constituents` with those ids + `market` + `scope` (`L3` for one L3 leaf, `L2` for the whole L2 branch).
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

**Watchlist / 候选股:** create → add_candidates → read_detail → eval_submit (min_candidate_count)
**建仓 / 买入:** read_search → create_order(s) with price+qty → read_detail → eval_submit (min_position_count)
**清仓 / 全部卖出:** read_search → read_detail → create_order(s) sell → read_detail → eval_submit (max_position_count=0)
**Delete:** read_list → write_delete → done (no read_detail, no eval_submit)

### Batch calls

- `get_ticker_realtime_quote` / `get_ticker_financials`: pass all tickers in one `tickers` array (≤50).
""".strip()
