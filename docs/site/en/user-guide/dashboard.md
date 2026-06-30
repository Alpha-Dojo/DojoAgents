# Dashboard

The dashboard is the local web UI for agent chat, tool activity, financial data, and visualization blocks.

## Start

```bash
dojoagents dashboard --host 127.0.0.1 --port 8765
```

Open:

```text
http://127.0.0.1:8765/
```

## API Entrypoints

| Method | Path | Description |
| --- | --- | --- |
| `GET` | `/api/health` | Health check |
| `GET` | `/api/config` | Redacted config |
| `GET` | `/api/jobs` | Scheduled jobs |
| `GET` | `/api/extensions` | Registered extensions |
| `POST` | `/api/chat` | OpenAI-compatible chat |
| `GET` | `/` | React SPA |

