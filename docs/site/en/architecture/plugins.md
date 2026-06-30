# Plugins

Plugins let DojoAgents load tools, hooks, skills, MCP config, and agent config from built-in and user directories.

## Discovery Paths

- Built-in plugins: `dojoagents/plugins/built_in/`
- User plugins: `~/.dojo/plugins`

## Supported Files

- `plugin.yaml`
- `.claude-plugin/plugin.json`
- `plugin.json`
- `hooks.json`
- `hooks/hooks.json`
- `__init__.py`

Hooks must use names from `VALID_HOOKS` in `dojoagents/plugins/registry.py`.

