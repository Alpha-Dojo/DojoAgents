# Tasks and Pipelines

## When to use

Structured tasks are for repeatable finance batch jobs: given a trading date (or a sector), gather evidence with a fixed tool order, then write schema-validated artifacts.  
Unlike free-form chat, a task has `contract.yaml`, `TASK.md`, output schemas, and optional pipeline chaining.

## Entry points

```bash
# Run a pipeline (example: daily market events)
dojoagents tasks run --pipeline daily-market-events --date 2026-07-22

# Validate a task artifact for a date
dojoagents tasks eval --task event-trigger --date 2026-07-22
```

Config: `tasks.enabled`, `tasks.output_root` (default outputs under `~/.dojo/tasks/outputs/<task-id>/`).  
See [CLI Reference](../reference/cli.md).

Code root: `dojoagents/tasks/` (`built_in/`, `pipelines/`, manager / activator / schema_validator).

## Tool policy (target)

| Family | Role | Notes |
| --- | --- | --- |
| `dojo.sdk.*` | Finance reads | **Primary path**; see [DojoSDK](../reference/dojo-sdk.md) |
| `web_search` / `web_extract` | External news evidence | Separate family |
| `write_session_file` / `read_session_output` | Task artifacts | Session / task output tools |

**Do not add new task dependencies on Dashboard domain tools** (for example `get_sector_movers`, `search_sector_taxonomy`).  
`daily-market-events` may still reference domain tools until migrated; new pipelines (Theme Deep Dive) are designed SDK-first.

## Existing pipeline: `daily-market-events`

```text
sector-attribution  →  market_news_raw_pack_{date}.json
        │
        ▼
event-trigger       →  market_event_triggers_{date}.jsonl
```

| Task | Harness | Role |
| --- | --- | --- |
| `sector-attribution` | `tool_orchestrated` | Find mover sectors, gather explanatory news, write raw pack |
| `event-trigger` | `artifact_synthesis` | Read pack, synthesize event cards + `sector_impacts` |

Definitions:

- `dojoagents/tasks/pipelines/daily-market-events.yaml`
- `dojoagents/tasks/built_in/sector-attribution/`
- `dojoagents/tasks/built_in/event-trigger/`

This pipeline is a **market-wide event** view. It is independent from Theme Deep Dive and does not share news packs.

## Designed: Theme Deep Dive

### Goal

For one locked sector from Daily Discovery or a user request (for example CN semiconductors +7.7% on the day), produce:

- Key Drivers
- News Event Impact (sentiment + impact score)
- Key Risks
- Top Components

### Minimal trigger

```text
Required:
  trading_date
  market: cn | us | hk
  exactly one of:
    A) level1_id + level2_id + level3_id
    B) sector_name

Do not require caller-supplied change_percent / direction (fetch to backfill)
```

Resolve rules:

- IDs → validate existence; fail hard on missing (no silent fuzzy remap)
- Name → taxonomy search; lock on a single high-confidence L3; fail or return candidates otherwise
- Default grain: **L3**

### Recommended two-task pipeline (independent)

```text
theme-deep-dive
  sector-theme-research   (tool_orchestrated)
        → sector_theme_research_pack_{…}.json
  sector-theme-synthesis  (artifact_synthesis)
        → theme_deep_dive_{…}.json
```

Fully independent from `daily-market-events`: re-fetch news; do not read the other pipeline’s artifacts.

### Research stage

1. **Quant**: sector day return, member returns, contribution Top-N, `rally_type`; optional theme_state / alpha.  
2. **News (two channels)**  
   - Channel A: Top-K contributor ticker news/events (prefer SDK batch + date window)  
   - Channel B: theme-level `web_search` / `web_extract`  
3. Write an evidence pack only; do not write final card copy.

### Synthesis stage

Read the research pack only; emit four-card JSON with hard constraints:

- Do not rewrite fetched `change_percent` / component whitelist  
- Every driver / impact / risk binds `evidence_ids`  
- `top_components` ⊆ quant `top_contributors`

Required SDK capabilities: [DojoSDK gaps](../reference/dojo-sdk.md#sdk-gaps).

## Related pages

- [DojoSDK](../reference/dojo-sdk.md)
- [Financial Workflows](financial-workflows.md)
- [CLI](../reference/cli.md)
- [Tool Contracts](../reference/tool-contracts.md)
