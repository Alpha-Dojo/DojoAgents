# Plugin Manifest

Plugin discovery and loading are implemented in `dojoagents/plugins/registry.py`.

## Supported Files

- `plugin.yaml`
- `.claude-plugin/plugin.json`
- `plugin.json`
- `hooks.json`
- `hooks/hooks.json`
- `__init__.py`

## Valid Hooks

- `on_session_start`
- `pre_llm_call`
- `pre_api_request`
- `post_api_request`
- `pre_tool_call`
- `post_tool_call`
- `transform_tool_result`
- `transform_llm_output`
- `post_llm_call`
- `on_session_end`

