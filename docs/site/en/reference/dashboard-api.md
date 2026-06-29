# Dashboard API

Dashboard API is registered by `dojoagents/dashboard/server.py`.

## Base Entrypoints

| Method | Path | Description |
| --- | --- | --- |
| `GET` | `/api/health` | Health check |
| `GET` | `/api/config` | Redacted config |
| `GET` | `/api/jobs` | Scheduled jobs |
| `GET` | `/api/extensions` | Registered extensions |
| `POST` | `/api/chat` | Chat completions |

Domain routers live under `dojoagents/dashboard/routers/`.

