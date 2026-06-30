# Multi-Agent and Planning

Multi-agent and planning modules support delegation, plan persistence, plan execution, and event-driven automation.

## Modules

| Module | Purpose |
| --- | --- |
| `dojoagents/multi_agent/models.py` | Agent and delegation models |
| `dojoagents/multi_agent/pool.py` | Agent pool |
| `dojoagents/multi_agent/orchestrator.py` | Orchestration |
| `dojoagents/planning/models.py` | Plan models |
| `dojoagents/planning/store.py` | Plan state store |
| `dojoagents/planning/engine.py` | Plan execution |

Multi-agent orchestration is a higher-level capability and should not replace the generic agent loop.

