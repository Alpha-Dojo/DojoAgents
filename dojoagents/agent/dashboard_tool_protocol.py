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
| Market snapshot / 大盘概览 / cross-market valuation | `get_market_overview` (omit `market` for US+CN+HK) | Re-fetching per market |
| Sector lead/lag / 领涨领跌板块 / 行业涨跌排名 | `get_sector_movers` → optional `filter_sector_constituents` on ids | `screen_market_stocks` when sector-level ranking is needed |
| Full-market screen / 全市场异动 / 涨跌幅排名 (no specific sector) | `screen_market_stocks` per market → optional `get_ticker_financials` | `filter_sector_constituents` without taxonomy match |
| Resolve one company name → ticker | `search_company_ticker` (single q, known name) | Repeated keyword searches |
| Analyze existing portfolio / 候选池成分分析 | `portfolio_read_search` → `portfolio_read_detail` → `get_ticker_financials` batch → answer | `portfolio_write_create`, add candidates, eval_submit |
| Single stock deep dive | `get_ticker_realtime_quote`, `get_ticker_financials`, `get_ticker_price_trends` (pass `start_date`/`end_date`; same day for one bar) | — |

### Analyze portfolio candidates (分析候选池 / 成分股怎么样)

Read-only workflow — no portfolio writes:

1. `portfolio_read_search` with portfolio name from the user
2. `portfolio_read_detail` for candidates list
3. Batch `get_ticker_financials` (and optional quotes) on candidate tickers
4. Summarize quality, valuation, risks — **stop**. No create, no eval_submit.

### Market overview / sector movers (get_market_overview, get_sector_movers)

Use these for **market-wide** or **sector-level** window returns — not for individual stock screens.

**Window (both tools — pick ONE mode):**

| Mode | Args | Notes |
|------|------|-------|
| Latest N trade days | `days` (default 1, max 90) | e.g. `days=5` = last 5 trading sessions |
| Fixed calendar range | `start_date` + `end_date` (YYYY-MM-DD) | Both required; max 126 calendar days; **overrides `days`** |

**Response fields (read via `tool_meta(res)` in execute_code):**

- `window_mode`: `days` or `date_range`
- `window_start` / `window_end`: actual first/last **trade dates** used (may differ from requested dates on holidays)
- `as_of`: latest trade date (`get_market_overview` only)

**get_market_overview:**

- Omit `market` for one cross-market call (US, CN, HK).
- `markets.*`: current listed count, total cap, weighted PE — **snapshot**, not window return.
- `benchmarks.*`: index `change_percent` and klines are **scoped to the window**.

**get_sector_movers:**

- Returns L3 sector gainers/losers per market; default `limit=5` each side.
- `change_percent` = sector total return over the window (from precomputed daily data).
- Rankings exclude `member_count<5` (members are constituents above the ~10亿 ticker floor).
- Each row has `level1_id`, `level2_id`, `level3_id` — copy into `filter_sector_constituents` / `get_sector_analysis`.
- Default total-sector cap floor: `min_cap_us` / `min_cap_cn` / `min_cap_hk` = **200亿 (2e10)** when omitted (same as Market UI). Pass `0` to disable; pass an explicit value to override.

**Examples:**

- 近一周大盘: `get_market_overview({"days": 5})`
- 年初至今区间: `get_market_overview({"start_date": "2026-01-01", "end_date": "2026-07-07"})`
- 本周领涨板块: `get_sector_movers({"days": 5, "limit": 10})`  # uses default 200亿 sector floor
- 指定区间领跌: `get_sector_movers({"start_date": "2026-01-01", "end_date": "2026-03-31", "market": "us"})`
- 关闭市值门槛: `get_sector_movers({"days": 1, "min_cap_us": 0, "min_cap_cn": 0, "min_cap_hk": 0})`

**Do NOT** pass only one of `start_date` / `end_date`. **Do NOT** use `screen_market_stocks` when the user asked for sector/industry rankings.

### Full-market screen / 全市场异动 (screen_market_stocks)

Server defaults (do NOT re-specify unless overriding user intent):

- **Hard exclude** (always): delisted, no quote, `market_cap≤0`, zero session volume/amount/turnover.
- **Default min market cap**: ~10亿 per ticker when `min_market_cap` is omitted (ticker floor; distinct from sector-movers' 200亿 *total sector* floor).
- **Mover ranking**: `sort_by=change_percent` or `return_pct` ranks by `change × log(market_cap)` (highest significance first; `sort_order` ignored for these fields).

**When to override `min_market_cap` / `max_market_cap`:**

| User intent | Tool args |
|-------------|-----------|
| 异动 / 涨跌幅 / 跌幅最大 / 涨幅最大 (default) | omit `min_market_cap`; `sort_by=change_percent` (significance-ranked; use `min_change_percent`/`max_change_percent` to split gainers vs losers) |
| 小市值 / 微盘 / 仙股 / penny / 壳股 / 低价暴涨 | `min_market_cap=0`; optional `max_market_cap` (e.g. 1e9 for sub-10B only) |
| 大盘股 / 蓝筹 / 千亿 | `min_market_cap=1e10` or `1e11` |
| 市值不高且涨幅巨大 (explicit small-cap momentum) | `min_market_cap=0`, `max_market_cap=1e9`, `sort_by=change_percent`, `min_change_percent` > 0 |

**Do NOT** pass `min_market_cap=0` unless the user clearly asked for small/micro caps.
**Do NOT** sort movers by raw `change_percent` alone — the tool applies significance weighting automatically.

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
   - market cap: filter constituent rows by `market_cap` field; for `screen_market_stocks` omit `min_market_cap`
     unless the user asked for small/micro caps (see Full-market screen section).
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
| Watchlist | 候选股 | Track symbols, no capital spent | `portfolio_write_add_candidate(s)` / `portfolio_write_remove_candidate(s)` | `min_candidate_count` |
| Filled buy | 持仓 / 建仓 | Spend capital at price × qty | `portfolio_write_create_order(s)` | `min_position_count` |
| Position sync | 仓位同步 | Import absolute shares + avg cost from external account (NOT a trade) | `portfolio_write_sync_positions` | `min_position_count` |
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

**User says 卖出 / 减仓 / negative share notation (e.g. 买入 NVDA -100 股 = sell 100):**
1. `portfolio_read_list` or `portfolio_read_search` → portfolio_id
2. `portfolio_read_detail` → verify held shares ≥ requested sell qty
3. `portfolio_write_create_order` with `order_side=sell`, explicit `qty`, optional `price` from quote.
   - Server infers `order_time` when omitted — **do NOT** call `get_ticker_price_trends` again just to confirm latest kline date.
   - If you already fetched price trends this turn, read `latest_kline.datetime` / `as_of` from the artifact pointer.
4. `portfolio_read_detail` → verify position / cash after fill

**User says 卖出 / 减仓 (partial, no qty given):**
- Do NOT guess share count. Wait for user to pick 50%, 75%, 100%, or an exact `qty`.
- After confirmation, call `portfolio_write_create_order(s)` with `qty` or `qty_pct`.

**User says 按现价 / 当前价 / 现在买入 (market order at quote):**
1. `get_ticker_realtime_quote` → `last_price`
2. `get_ticker_price_trends` once (omit dates or set `end_date` to today) → read `latest_kline.datetime`
   from the response or artifact pointer (`as_of` / `period_end`). **Do NOT** call again with a guessed date.
3. `portfolio_write_create_order` with `price=last_price` and optional `order_time=<latest kline datetime>`
   (server infers `order_time` when omitted)
4. Limit price must fall within that day's `[low, high]` inclusive (open may equal high/low).

**User says 建仓 / 买入 / 创建交易 (new trade in this portfolio):**
1. `portfolio_read_search` or `portfolio_read_list` → target portfolio_id
2. If price/date is specified (e.g. 2026-06-18 开盘价): call `get_ticker_price_trends` with
   `start_date` AND `end_date` both set to that day (YYYY-MM-DD), then read `open` from klines.
   Do NOT call kline tools with only ticker/kline_t — that returns the full history.
3. Call `portfolio_write_create_order` (or batch) with `ticker` + `order_side=buy`.
   Optional fields — server resolves defaults:
   - no `order_time` + no `price` → latest daily **close**
   - `order_time` only → that day's **open**
   - `price` only → **latest trading day first** if price fits that bar; else nearest historical day
   - `price` + `order_time` → validate price within that day's `[low, high]` inclusive
   - no `qty` on buy → **10%** of available market cash (lot-normalized)
   - US qty: integer shares; HK/A-share qty: multiples of 100
4. `portfolio_read_detail` → verify `eval_summary.position_count` (NOT candidate_count)
5. `portfolio_eval_submit` with **min_position_count** matching filled positions

**User says 仓位同步 / 同步持仓 / 从其他交易所导入 / 外部账户持仓 / 按成本价同步 (import existing holdings):**
This is **NOT** a buy trade — do NOT use `portfolio_write_create_order` (kline validation and cash deduction apply).

1. `portfolio_read_search` or `portfolio_read_list` → target portfolio_id
2. Collect absolute target `qty` + average `cost` per ticker (from user message or screenshot).
3. **One call:** `portfolio_write_sync_positions` with `items: [{ticker, market?, qty, cost}, ...]`.
   - `qty` = absolute shares after sync; `cost` required when `qty > 0`.
   - `qty=0` clears that ticker from positions.
   - Sync time defaults to server now — do NOT pass historical `order_time`.
4. `portfolio_read_detail` → verify `eval_summary.position_count` and holdings cost/shares
5. Optional `portfolio_eval_submit` with **min_position_count** when the task requires verification

**User says 建仓 / 买入 / 按成本价 / 创建交易 / 持仓页面截图 with shares & cost:**
If the user is **recording a new trade** in Alpha Dojo → use `portfolio_write_create_order` workflow above.
If the user is **importing holdings from another broker** → use `portfolio_write_sync_positions` workflow above.

**Capital preflight (batch 建仓):**
- Before large batch buys, ensure `Σ(price × qty)` per market fits `capital_by_market`.
- If the tool returns `capital_budget_exceeded`, **stop** and ask the user whether to raise
  Folio initial capital or reduce symbols/share counts. Do NOT silently lower qty.
- A-share min lot is 100 shares; do not auto-reduce below user-requested sizing.

**FORBIDDEN for 建仓:** `portfolio_write_add_candidate`, `portfolio_write_add_holding`, `portfolio_write_add_holdings`
(these only add 候选股; they never buy or set cost).

**Theme basket without 建仓:** use add_candidates only — positions stay 0 until user asks to buy.

**Remove watchlist / 剔除候选股 (2+ tickers):**
1. `portfolio_read_detail` → read `candidates[]` or artifact pointer candidate rows
2. **One call:** `portfolio_write_remove_candidates` with `holdings: [{ticker, market?}, ...]`
3. `portfolio_read_detail` → verify `eval_summary.candidate_count` if eval follows

**Remove watchlist rules (avoid concurrent single removes):**
- **≥2 tickers:** MUST use `portfolio_write_remove_candidates` once — never parallel/repeated `portfolio_write_remove_holding`
- **1 ticker:** `portfolio_write_remove_holding` is OK
- Tickers with open positions are skipped (`remove_result.blocked_open_position`); sell first via `portfolio_write_create_order(s)`
- If `remove_result.skipped_not_in_watchlist` is non-empty, those tickers were not on the watchlist

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

Query rules (see also Temporal context in system prompt):
- Use event/entity/topic keywords (e.g. `Meta 卖算力`, `Meta sell compute`).
- Do NOT append a year to the query unless the user named a specific year.
- Do NOT use the model training cutoff year (e.g. 2025) when the user says 最近/近期/recent/latest.
- After results return, judge freshness against Temporal context. If articles look stale, tell the
  user and broaden or refine the query — do NOT fix staleness by swapping in a guessed year.

### Save analysis files (JSON / JSONL / text) — user request only

Only use `write_session_file` or `execute_code` with `dojo_tools.write_session_file(...)` when the
user explicitly asked to save, export, or download a file. Do NOT write files proactively for routine
analysis — deliver results in the assistant reply.

- Files are written under `{sessions.root}/{session_id}/outputs/` (tool returns absolute `path`).
- After writing, **repeat the returned `path` in your reply** so the user can open the file.
- `format`: `json` | `jsonl` | `text`. Pass structured Python objects when using execute_code.
- **FORBIDDEN:** `terminal` heredoc / `cat > /workspace/...` / guessing output directories.
- **FORBIDDEN:** saving analysis output without an explicit user file request (blocked at call time).
- `execute_code` sets `DOJO_SESSION_OUTPUT_DIR` for the current session when saving from Python.

### User-uploaded session input files

Users may attach files to a chat turn. Uploads are stored under `{sessions.root}/{session_id}/inputs/`.

- The user message includes each file's absolute `path`, `kind`, and a truncated preview when available.
- Start from the preview for text/code/csv/json/excel/pdf attachments.
- When preview is truncated or you need more lines/rows/pages, call `read_session_input(filename, offset=..., limit=..., sheet=...)`.
- `execute_code` sets `DOJO_SESSION_INPUT_DIR` to the current session inputs directory.
- **FORBIDDEN:** guessing upload paths, shell `cat` on unknown paths, or re-uploading files the user already attached.

Typical execute_code pattern for an attached Excel/CSV file:

```python
import os
import pandas as pd
path = os.path.join(os.environ["DOJO_SESSION_INPUT_DIR"], "model.xlsx")
df = pd.read_excel(path, sheet_name=0)
print(df.head(20).to_string())
```

Typical execute_code pattern:

```python
import dojo_tools
payload = {"items": [...]}
res = dojo_tools.write_session_file("analysis.json", payload, format="json")
print(dojo_tools.tool_json(res)["path"])
```

### portfolio_read_detail artifact pointers (CRITICAL)

Large portfolio responses are compressed to an artifact pointer. The pointer **always includes**
`eval_summary` and `positions[]` (ticker, name, shares, weight) — read those for 卖出/减仓/清仓.

- **Do NOT** use `terminal` or shell `python3 -c` to call `dojo_tools.load_tool_result` — that bridge
  exists only inside `execute_code`.
- **Do NOT** re-call `portfolio_read_detail` just to re-read holdings already in the pointer.
- For **order workflows** (买入/卖出/减仓/清仓), pass `include_performance=false` to avoid bloating
  the response with NAV series you do not need.
- Only use `execute_code` + `load_tool_result(call_id)` when you need full candidate rows or
  performance series for computation — not for pretty-printing JSON.

### Portfolio tools

**Watchlist / 候选股:** create → add_candidates → read_detail → eval_submit (min_candidate_count)
**剔除候选股:** read_detail → remove_candidates (batch) → read_detail → eval_submit if needed
**建仓 / 买入:** read_search → create_order(s) with price+qty → read_detail → eval_submit (min_position_count)
**仓位同步 / 外部导入:** read_search → sync_positions (items qty+cost) → read_detail → eval_submit if needed
**清仓 / 全部卖出:** read_search → read_detail → create_order(s) sell → read_detail → eval_submit (max_position_count=0)
**Delete:** read_list → write_delete → done (no read_detail, no eval_submit)

### Batch calls

- `get_ticker_realtime_quote` / `get_ticker_financials`: pass all tickers in one `tickers` array (≤50).
- `portfolio_write_add_candidates` / `portfolio_write_remove_candidates`: pass all watchlist tickers in one `holdings` array.
- `portfolio_write_sync_positions`: pass all imported holdings in one `items` array.

### execute_code (computation only — NOT for text formatting)

Use `execute_code` ONLY when you must batch-call dojo_tools or run pandas/numpy transforms on
fetched tool data inside one script. pd/np/dojo_tools are pre-imported.
After `load_tool_result`, prefer `dojo_tools.tool_print(res)` or
`dojo_tools.tool_print(res, table='benchmarks', columns=[...])` — safe, no KeyError.
Metadata: `dojo_tools.tool_meta(res)`. Columns: `dojo_tools.tool_columns(res[, table])`.

Only persist output to a file when the user explicitly requested a save/export — call
`dojo_tools.write_session_file(filename, content, format=...)` and print the returned `path`.
Unrequested file writes are blocked at call time. Do NOT use terminal heredoc for file writes.

FORBIDDEN uses of `execute_code`:

- knowledge-graph schema design, node/edge taxonomy docs, ASCII diagrams
- printing multi-section design proposals or formatted reports via `print()`
- any deliverable that should be normal assistant markdown

Misuse is blocked at call time by execute_code guardrails — do NOT use execute_code for text
formatting even when the task is analysis or design. Use agent_viz_build for structured charts.
""".strip()
