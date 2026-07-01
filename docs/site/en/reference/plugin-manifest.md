# Plugin Manifest

Plugin discovery and loading are implemented in `dojoagents/plugins/registry.py`.

## Supported Files

A plugin directory may contain:

- `plugin.yaml`
- `.claude-plugin/plugin.json`
- `plugin.json`
- `hooks.json`
- `hooks/hooks.json`
- `__init__.py`

User plugins are discovered from `~/.dojo/plugins`. Built-in plugins live under `dojoagents/plugins/built_in/`.

## Manifest Fields

| Field | Purpose |
| --- | --- |
| `name` | Plugin name |
| `version` | Version, default `0.1.2` |
| `description` | Human-readable description |
| `provides_tools` | Tool names exposed by the plugin |
| `provides_hooks` | Hook names exposed by the plugin |

Runtime manifests also track `path`, `source`, and `is_claude`.

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

Claude-style hooks are mapped through `CLAUDE_TO_DOJO_HOOKS`; unsupported hook names are logged but should not be used for new plugins.

## Plugin Capabilities

Plugins may register:

- hooks through `DojoPluginContext.register_hook()`;
- tools through `DojoPluginContext.register_tool()`;
- skill directories;
- MCP server configs;
- default multi-agent configs.

## Code Anchors

- `dojoagents/plugins/registry.py`
- `dojoagents/plugins/__init__.py`
- `dojoagents/tools/plugin_manage.py`
