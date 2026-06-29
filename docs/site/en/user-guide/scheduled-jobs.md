# Scheduled Jobs

DojoAgents uses cron and scheduler modules for background work such as data precomputation, cache maintenance, and workflow triggers.

## CLI Check

```bash
dojoagents scheduler
```

## Modules

| Module | Purpose |
| --- | --- |
| `dojoagents/cron/jobs.py` | Job models and storage |
| `dojoagents/cron/scheduler.py` | Scheduler integration |
| `dojoagents/planning/triggers.py` | Plan triggers |

