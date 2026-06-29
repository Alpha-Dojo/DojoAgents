# Runtime

Runtime builds the DojoAgents object graph from configuration.

## Entrypoints

| Entrypoint | Purpose |
| --- | --- |
| `Runtime.from_default_config()` | Use default `~/.dojo/agents.yaml` |
| `Runtime.from_config_store(ConfigStore(...))` | Use a specific config source |

## Boundaries

Runtime should not reimplement config parsing, logging, or tool execution. New capabilities should register through existing extension points:

- Tools: `ToolSpec`
- Plugins: plugin registry
- Extensions: `DojoExtension`
- Dashboard services: `dojoagents/dashboard/deps.py`

