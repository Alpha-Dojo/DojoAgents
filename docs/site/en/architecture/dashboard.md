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

## Agent tool registration (separate from REST)

- Dashboard boot calls `register_dashboard_domain_tools` / `register_dashboard_portfolio_tools` so chat can use those tools from the same Runtime registry.
- **REST domain APIs are not agent tool names.** The **target** finance-read path is always-on `dojo.sdk.*` from Runtime ([DojoSDK](../reference/dojo-sdk.md)).
- Domain read tools are legacy; new tasks should not add dependencies on them. Portfolio write tools remain on the Dashboard tool surface for now.

## Further reading

- [Dashboard API](../reference/dashboard-api.md)
- [Dashboard user guide](../user-guide/dashboard.md)
- [Tasks and Pipelines](../user-guide/tasks-and-pipelines.md)
