# Memory

Memory stores conversation summaries, skill summaries, and context across longer tasks.

## Modules

| Module | Purpose |
| --- | --- |
| `dojoagents/memory/provider.py` | Provider protocol |
| `dojoagents/memory/manager.py` | Memory manager |
| `dojoagents/memory/local_memory.py` | Local provider |
| `dojoagents/memory/skill_summary.py` | Skill summary provider |

Do not store provider secrets, tokens, or sensitive user configuration in memory.

