# 测试

## 测试分类

DojoAgents 与 DojoSDK 使用相同的执行边界标记：

- `unit`：确定性的服务与模型测试；
- `offline_integration`：Dashboard 与 DojoSDK 本地快照集成测试；
- `online_integration`：依赖真实外部服务的测试；
- `contract`：API、配置和跨仓库契约测试；
- `slow`：长时间运行的数据集或端到端测试。

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

按标记运行：

```bash
uv run --extra dev python -m pytest -m "not online_integration and not slow" -q
uv run --extra dev python -m pytest -m offline_integration -q
uv run --extra dev python -m pytest -m contract -q
```

在线测试和慢速测试必须在 CI 中显式选择，并提供所需凭据与服务；不能根据开发者本机的离线配置自动推断。

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
