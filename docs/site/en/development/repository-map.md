# Repository Map

## Main Directories

| Directory | Purpose |
| --- | --- |
| `dojoagents/agent/` | Agent loop, runtime, providers, events |
| `dojoagents/config/` | ConfigStore and config schema |
| `dojoagents/tools/` | Tool registry, executor, sandbox; includes `dojo_sdk_tool.py`, web, session |
| `dojoagents/tasks/` | Structured tasks / pipelines (contracts, TASK.md, schemas, pipelines) |
| `dojoagents/dashboard/` | FastAPI dashboard and React app; `dashboard/tools/` for portfolio / legacy domain |
| `dojoagents/gateway/` | Gateway server, state, adapters |
| `dojoagents/plugins/` | Plugin discovery and hooks |
| `dojoagents/skills/` | Skill loader/cache/manager |
| `dojoagents/memory/` | Memory providers |
| `dojoagents/multi_agent/` | Agent pool and delegation |
| `dojoagents/planning/` | Plan store, engine, triggers |
| `dojoagents/quant/` | Quant context, risk, workflow |
| `tests/` | Pytest suite |
| `docs/` | MkDocs site and `docs/plans/` design notes |

Reuse `ConfigStore`, `dojoagents.logging`, `ToolRegistry`, `ToolExecutor`, and dashboard dependency accessors. Prefer `dojo.sdk.*` for agent finance reads ([DojoSDK](../reference/dojo-sdk.md)).
