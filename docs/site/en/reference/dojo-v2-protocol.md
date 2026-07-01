# dojo.v2 Protocol

`dojo.v2` adds typed Dojo events to the OpenAI-compatible Chat API. Enable it with:

```json
{
  "metadata": {
    "event_format": "dojo.v2"
  }
}
```

## Transport Forms

| Mode | Transport | Dojo event location |
| --- | --- | --- |
| `stream=false` | JSON response | `metadata.dojo.events`, with legacy `content` and `session_id` fields on the response body |
| `stream=true` | SSE | OpenAI-compatible chunks with an added `dojo_event` field |
| `/api/chat/runs/{run_id}/events` | SSE | Each `data:` line is a Dojo event JSON object |

When `dojo.v2` is not requested, clients should rely only on OpenAI-compatible fields.

## Common Fields

Every Dojo event contains:

| Field | Type | Description |
| --- | --- | --- |
| `schema_version` | string | Currently `2.0` |
| `run_id` | string | Run identifier |
| `seq` | integer | Monotonic event sequence within the run, starting at 1 |
| `session_id` | string | Session identifier |
| `timestamp` | string | UTC ISO timestamp |
| `type` | string | Event type |

Clients should deduplicate and order by `(run_id, seq)`. Tool events use `call_id` to correlate `tool_start` and `tool_result`.

## Event Types

| `type` | Key fields | Description |
| --- | --- | --- |
| `phase` | `phase` | Agent phase change, such as planning, tooling, answering |
| `delta` | `text` | Model output text delta |
| `think_start` | `summary` | Thinking segment begins; content may be scrubbed or summarized |
| `think_delta` | `text` | Thinking text delta; affected by `agent.enable_think_scrubbing` |
| `think_end` | `summary` | Thinking segment ends |
| `retry` | `attempt`, `max_attempts`, `text` | Provider or runtime retry notice |
| `tool_start` | `call_id`, `tool`, `arguments` | Tool execution begins |
| `tool_result` | `call_id`, `tool`, `ok`, `content`, `error`, `latency_ms` | Tool execution finishes |
| `eval_hint` | `text`, `issues` | Evaluation or guardrail hint |
| `token_usage` | token snapshot fields | Session token ledger snapshot |
| `context_compacted` | `compression_count`, `estimated_prompt_tokens` | Context compression completed |
| `done` | `model_id`, `tool_trace`, `tool_steps` | Run completed successfully |
| `error` | `message`, `code` | Run failed |

## `tool_result` Extensions

`tool_result` may carry structured display data:

| Field | Type | Description |
| --- | --- | --- |
| `data` | any | Structured tool result |
| `viz_blocks` | array | Agent visualization blocks |
| `artifacts` | array | Files, charts, exports, or other produced artifacts |
| `resource_changes` | array | Resource change notices, such as portfolio or session updates |
| `truncated` | boolean | Whether tool output was truncated |
| `latency_ms` | integer | Tool latency |

Tool outputs should still be normalized by `ToolExecutor`; handlers should not invent arbitrary result shapes.

## `token_usage`

`token_usage` includes:

- `last_prompt_tokens`
- `last_completion_tokens`
- `last_total_tokens`
- `session_max_tokens`
- `compression_threshold_ratio`
- `utilization_ratio`
- `cumulative_total_tokens`
- `compression_count`
- `model_context_window`
- `loop_count`

It drives dashboard token state and helps identify when context compression is near its threshold.

## Compatibility

- OpenAI-compatible clients can ignore `dojo_event` and `metadata.dojo`.
- Dojo-aware clients should consume `dojo.v2` events instead of parsing tool traces from natural-language output.
- Frontend run recovery should use `run_id`, `seq`, and `call_id` as stable identifiers.
- Historical transcript loading uses `/api/v1/chat/sessions/*`; `/api/chat/sessions/{session_id}/tokens` is only a token ledger endpoint.

## Code Anchors

- `dojoagents/agent/events.py`
- `dojoagents/dashboard/server.py`
- `dojoagents/agent/models.py`
