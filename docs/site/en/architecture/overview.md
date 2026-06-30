# Overview

DojoAgents combines LLM agents, quantitative finance data, tool execution, dashboard UI, gateway adapters, plugins, and scheduled jobs into an extensible local runtime.

## Module Map

| Module | Purpose |
| --- | --- |
| `dojoagents/agent/` | Agent loop, providers, runtime, events, guardrails |
| `dojoagents/config/` | ConfigStore and typed config schema |
| `dojoagents/tools/` | Tool registry, executor, sandbox, tools |
| `dojoagents/dashboard/` | FastAPI backend, services, routers, React app |
| `dojoagents/gateway/` | Chat gateway and adapters |
| `dojoagents/plugins/` | Plugin discovery and hooks |
| `dojoagents/skills/` | Skill loader/cache/manager |
| `dojoagents/memory/` | Memory providers |
| `dojoagents/multi_agent/` | Agent pool and delegation |
| `dojoagents/planning/` | Plan store, engine, tools, triggers |

## Flow

1. CLI, Dashboard, or Gateway creates a request.
2. `Runtime` builds providers, tools, skills, memory, scheduler, and plugins from config.
3. `AgentLoop` calls the LLM provider.
4. Tool calls are executed through `ToolExecutor`.
5. `ToolResult` is sent back to the model, event stream, and dashboard UI.

