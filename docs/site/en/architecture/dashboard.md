# Dashboard Architecture

The dashboard combines a FastAPI backend, React frontend, financial services, and the agent chat API.

## Backend Layers

| Layer | Path |
| --- | --- |
| App factory | `dojoagents/dashboard/server.py` |
| Dependencies | `dojoagents/dashboard/deps.py` |
| Routers | `dojoagents/dashboard/routers/` |
| Schemas | `dojoagents/dashboard/schemas/` |
| Services | `dojoagents/dashboard/services/` |
| Static/Web | `dojoagents/dashboard/static/`, `dojoagents/dashboard/web/` |

## Communication

- `POST /api/chat` is OpenAI-compatible.
- Streaming uses SSE.
- `dojo.v2` events are carried in `dojo_event`.

