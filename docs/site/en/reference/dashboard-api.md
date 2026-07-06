# Dashboard API

The Dashboard API is registered by `dojoagents/dashboard/server.py` and `dojoagents/dashboard/routers/`. `/api/chat` is the main agent entrypoint, `/api/chat/runs` exposes background run lifecycle control, and `/api/v1/*` contains dashboard financial-domain and session APIs.

## Base Entrypoints

| Method | Path | Description |
| --- | --- | --- |
| `GET` | `/api/health` | Health check, returns `{"ok": true}` |
| `GET` | `/api/config` | Redacted configuration from `ConfigStore.redacted()` |
| `PUT` | `/api/config` | Deep-merge user config and save it |
| `GET` | `/api/jobs` | Current scheduler jobs |
| `GET` | `/api/extensions` | Registered Dojo extension status |
| `GET` | `/` | React dashboard SPA |

## Chat

### `POST /api/chat`

Accepts OpenAI-compatible requests and the legacy DojoAgents request shape.

OpenAI-compatible request:

```json
{
  "model": "default",
  "messages": [
    {"role": "user", "content": "Analyze the semiconductor sector"}
  ],
  "stream": true,
  "metadata": {
    "session_id": "session-123",
    "event_format": "dojo.v2",
    "locale": "en"
  }
}
```

Parsing rules:

- `messages` must be a non-empty array with at least one non-empty `user` message.
- The last non-empty `user` message is the current input; earlier messages are stored in `metadata.history`.
- `metadata.session_id` is generated when omitted.
- `metadata.event_format` defaults to `openai.v1`; set it to `dojo.v2` for typed Dojo events.
- `metadata.quant` may contain `QuantContext` fields.

Legacy request:

```json
{
  "message": "Analyze my portfolio",
  "user_id": "local",
  "session_id": "cli",
  "channel": "dashboard"
}
```

Non-streaming responses are OpenAI-compatible `chat.completion` objects with legacy `content` and `session_id` fields. Streaming responses are SSE chunks compatible with OpenAI `chat.completion.chunk`; `dojo.v2` mode also attaches `dojo_event`.

## Run Lifecycle

| Method | Path | Description |
| --- | --- | --- |
| `POST` | `/api/chat/runs` | Create a background agent run and return `run_id`, `session_id`, `status`, and `model` |
| `GET` | `/api/chat/runs/{run_id}` | Read run status and event count |
| `POST` | `/api/chat/runs/{run_id}/cancel` | Cancel an active run |
| `GET` | `/api/chat/runs/{run_id}/events?cursor=0` | Stream run events from a cursor over SSE |
| `GET` | `/api/chat/sessions/{session_id}/tokens` | Return token ledger state; not a full session query API |

`/api/chat/runs/{run_id}/events` stops once the run is no longer active. Unknown `run_id` values return 404.

## Session API

The `chat_sessions` router is mounted at `/api/v1/chat/sessions`.

| Method | Path | Description |
| --- | --- | --- |
| `GET` | `/api/v1/chat/sessions?limit=50&cursor=&include_archived=false` | List sessions |
| `GET` | `/api/v1/chat/sessions/{session_id}` | Read session sidecar metadata |
| `GET` | `/api/v1/chat/sessions/{session_id}/messages?limit=200&offset=0` | Read session messages |
| `POST` | `/api/v1/chat/sessions/{session_id}/archive` | Archive a session |
| `POST` | `/api/v1/chat/sessions/export` | Export all sessions, or one session when `session_id` is provided, to the configured or requested directory |

Default session and export paths are controlled by `sessions.root` and `sessions.export_default_dir`.

Export request body:

```json
{
  "session_id": "session-123",
  "output_dir": "~/Desktop/dojo-chat-export",
  "include_archived": true
}
```

Omit `session_id` to export all visible sessions.

## Domain Routers

All domain routers are mounted under `/api/v1`.

| Router | Main paths | Description |
| --- | --- | --- |
| `utility` | `/utility/search/company-ticker`, `/utility/taxonomy/tree` | Company/ticker search and taxonomy tree |
| `market` | `/market/overview`, `/market/sector-movers`, `/market/screener` | Market overview, sector movers, stock screening |
| `markets` | `/markets/stats`, `/markets/{market}/stats` | Market statistics |
| `sector` | `/sector/analysis`, `/sector/constituents` | Sector analysis and constituents |
| `sectors` | `/sectors/taxonomy` | L1/L2/L3 sector taxonomy document |
| `ticker` | `/ticker/quote`, `/ticker/financials`, `/ticker/news-events`, `/ticker/price-trends` | Aggregated ticker queries |
| `portfolio` | `/portfolio`, `/portfolio/manage`, `/portfolio/holdings`, `/portfolio/allocate` | v1 portfolio operations and analysis |
| `dojo-core` | `/dojo-core/tickers/search`, `/dojo-core/ticker/*` | DojoCore ticker search, quote, sector, kline, PE band, financials, news |
| `dojo-folio` | `/dojo-folio/portfolios`, `/dojo-folio/portfolios/{id}` | Native portfolio CRUD, holdings, allocation |
| `dojo-mesh` | `/dojo-mesh/benchmarks`, `/dojo-mesh/sectors`, `/dojo-mesh/sectors/cross-market` | Cross-market benchmarks and sector leaders/laggards |
| `dojo-sphere` | `/dojo-sphere/sectors/*`, `/dojo-sphere/constituents/*` | Sector metrics, constituents, performance, and klines |

Common market parameters:

- legacy domain APIs use `cn|sh|hk|us`.
- most DojoCore/DojoSphere APIs use `sh|hk|us`.

## Errors

- Invalid JSON or invalid fields return 422 or 400.
- Unknown sessions, runs, tickers, portfolios, or sector paths return 404.
- Expected business failures use `fastapi.HTTPException` or `JSONResponse(status_code=..., content={"error": ...})`.
- `PUT /api/config` returns 403 when the config file is not writable.

## Code Anchors

- `dojoagents/dashboard/server.py`
- `dojoagents/dashboard/routers/`
- `dojoagents/dashboard/schemas/`
- `dojoagents/agent/events.py`
