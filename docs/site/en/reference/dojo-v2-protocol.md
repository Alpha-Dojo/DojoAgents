# dojo.v2 Protocol

`dojo.v2` adds typed Dojo events to OpenAI-compatible streaming chunks.

## Event Fields

- `schema_version`
- `run_id`
- `seq`
- `session_id`
- `timestamp`
- `type`

Tool events should use `call_id` to correlate `tool_start` and `tool_result`.

## Common Events

- `phase`
- `delta`
- `tool_start`
- `tool_result`
- `eval_hint`
- `done`
- `error`

