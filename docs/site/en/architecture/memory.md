# Memory Architecture

Memory provides pluggable session memory, summaries, and longer-context continuity.

## Modules

| Module | Purpose |
| --- | --- |
| `dojoagents/memory/provider.py` | Provider protocol |
| `dojoagents/memory/manager.py` | Manager |
| `dojoagents/memory/local_memory.py` | Local provider |
| `dojoagents/memory/skill_summary.py` | Skill summary provider |

Do not store provider secrets, API keys, or sensitive user configuration in memory.

