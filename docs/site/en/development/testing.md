# Testing

## Suite categories

DojoAgents uses the same execution-boundary markers as DojoSDK:

- `unit`: deterministic service and model tests;
- `offline_integration`: Dashboard and DojoSDK local snapshot integration;
- `online_integration`: live external service tests;
- `contract`: API, configuration, and cross-repository contracts;
- `slow`: long-running dataset or end-to-end tests.

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

Marker-based runs:

```bash
uv run --extra dev python -m pytest -m "not online_integration and not slow" -q
uv run --extra dev python -m pytest -m offline_integration -q
uv run --extra dev python -m pytest -m contract -q
```

Live and slow suites must be selected explicitly in CI with their required credentials and services. Do not infer them from a developer's local offline configuration.

## Frontend

```bash
cd dojoagents/dashboard/web
npm run build
```

## Documentation

```bash
uv run --extra docs mkdocs build --strict
```
