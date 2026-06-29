# Repository Map

## Main Directories

| Directory | Purpose |
| --- | --- |
| `dojoagents/agent/` | Agent loop, runtime, providers, events |
| `dojoagents/config/` | ConfigStore and config schema |
| `dojoagents/tools/` | Tool registry, executor, sandbox |
| `dojoagents/dashboard/` | FastAPI dashboard and React app |
| `dojoagents/gateway/` | Gateway server, state, adapters |
| `dojoagents/plugins/` | Plugin discovery and hooks |
| `dojoagents/skills/` | Skill loader/cache/manager |
| `dojoagents/memory/` | Memory providers |
| `dojoagents/multi_agent/` | Agent pool and delegation |
| `dojoagents/planning/` | Plan store, engine, triggers |
| `tests/` | Pytest suite |
| `docs/` | MkDocs site and design notes |

Reuse `ConfigStore`, `dojoagents.logging`, `ToolRegistry`, `ToolExecutor`, and dashboard dependency accessors instead of creating parallel infrastructure.

