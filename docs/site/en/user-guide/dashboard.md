# Dashboard

The dashboard is the local web UI for agent chat, tool activity, financial data, visualization blocks, and session history.

## Start

```bash
dojoagents dashboard --host 127.0.0.1 --port 8765
```

Open:

```text
http://127.0.0.1:8765/
```

For first-time setup, configure a model provider:

```bash
dojoagents model
```

You can also write model settings from the dashboard settings UI. Config is saved to `~/.dojo/agents.yaml`.

## Common Workflow

1. Start the dashboard.
2. Confirm provider, model, base URL, and API key in settings.
3. Ask a financial analysis question in the agent chat.
4. Inspect tool execution, structured results, and visualization blocks.
5. Continue follow-up turns in the same session.
6. Export sessions when you need backup or audit artifacts.

The backend is the source of truth for session history. A new turn only needs the current user input; the frontend does not need to resend the full transcript.

## API Entrypoints

| Method | Path | Description |
| --- | --- | --- |
| `GET` | `/api/health` | Health check |
| `GET` | `/api/config` | Redacted config |
| `PUT` | `/api/config` | Update config |
| `GET` | `/api/jobs` | Scheduled jobs |
| `GET` | `/api/extensions` | Registered extensions |
| `POST` | `/api/chat` | OpenAI-compatible chat |
| `POST` | `/api/chat/runs` | Background agent run |
| `GET` | `/api/chat/runs/{run_id}/events` | Run event SSE |
| `GET` | `/api/v1/chat/sessions` | Session list |
| `GET` | `/` | React SPA |

See [Dashboard API Reference](../reference/dashboard-api.md) for the full API map.

## Data Directories

Common local paths:

| Path | Purpose |
| --- | --- |
| `~/.dojo/agents.yaml` | Main config file |
| `~/.dojo/dashboard-data` | Dashboard financial data and derived caches |
| `~/.dojo/agents/strands_sessions` | Session history |
| `~/Desktop/dojo-chat-export` | Default session export directory |

These can be changed through `dashboard.financial` and `sessions` in [Configuration](../reference/configuration.md).

## Frontend Development

```bash
cd dojoagents/dashboard/web
npm run dev
```

Vite proxies backend API calls to `http://127.0.0.1:8765/api`. During frontend development, also run:

```bash
dojoagents dashboard --host 127.0.0.1 --port 8765
```

## Network Exposure

The recommended default is `127.0.0.1`. If you bind to `0.0.0.0` or expose the dashboard publicly, add authentication, access control, network isolation, and secret-management controls first. `/api/config` is redacted, but an unprotected dashboard should not be exposed to the public internet.

## Troubleshooting

Dashboard does not open:

- Confirm the backend command is still running.
- Visit `http://127.0.0.1:8765/api/health`.
- If running from source, confirm the frontend is built or the Vite dev server is running.

Model request fails:

- Confirm `llm_provider.default` points to an existing provider.
- Confirm provider `model`, `base_url`, `api_key_env`, or `api_key`.
- For local model servers, confirm the base URL is reachable.

SSE disconnects:

- Query `/api/chat/runs/{run_id}` to see whether the run already ended.
- Continue reading events from `/api/chat/runs/{run_id}/events?cursor=N`.

Session history is missing:

- Confirm `sessions.enabled` is `true`.
- Confirm the frontend reused the same `session_id`.
- Check that `sessions.root` points to durable writable storage.

## Related Pages

- [Dashboard Architecture](../architecture/dashboard.md)
- [Dashboard API Reference](../reference/dashboard-api.md)
- [Session Design and Integration](../development/session-history-design.md)
