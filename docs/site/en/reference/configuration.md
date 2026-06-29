# Configuration

Configuration is based on `dojoagents/config/loader.py::ConfigStore` and `dojoagents/config/models.py::AgentsConfig`.

## Default Path

```text
~/.dojo/agents.yaml
```

## Rules

- Typed reads use `ConfigStore.snapshot()`.
- User updates use `ConfigStore.raw()`, deep merge, and `ConfigStore.save_raw()`.
- Dashboard/API exposure uses `ConfigStore.redacted()`.
- Do not create a separate YAML parser or config singleton.

