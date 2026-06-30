# 测试

## Python

完整测试：

```bash
uv run --extra dev python -m pytest -q
```

常用目标测试：

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

## Runtime Smoke

```bash
uv run --extra dev dojoagents --help
uv run --extra dev dojoagents dashboard --host 127.0.0.1 --port 8765
```

Dashboard smoke 启动服务后，需要在验证结束前停止服务。

## Documentation

```bash
uv run --extra docs mkdocs build --strict
```

