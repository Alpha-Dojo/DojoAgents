# Testing

## Python

```bash
uv run --extra dev python -m pytest -q
```

Focused tests:

```bash
uv run --extra dev python -m pytest tests/test_config_multi_agent_plan.py -q
uv run --extra dev python -m pytest tests/dashboard/routers -q
uv run --extra dev python -m pytest tests/test_tool_registry_clone.py tests/test_terminal_tool_integrated.py -q
```

## Frontend

```bash
cd dojoagents/dashboard/web
npm run build
```

## Documentation

```bash
uv run --extra docs mkdocs build --strict
```

