# CLI Reference

## 状态

CLI parser 定义在 `dojoagents/cli/main.py`。

## 命令

| 命令 | 参数 | 说明 |
| --- | --- | --- |
| `chat` | `message`, `--profile`, `--market`, `--symbols`, `--timeframe` | 发起本地 Agent 请求 |
| `dashboard` | `--host`, `--port` | 启动 Dashboard |
| `gateway` | `--host`, `--port`, `--config` | 启动 Gateway |
| `gateway setup` | `adapter`, `--config` | 配置 adapter |
| `gateway pairing list` | `--platform`, `--config` | 查看待批准配对 |
| `gateway pairing approve` | `platform`, `code`, `--config` | 批准配对 |
| `gateway pairing deny` | `platform`, `code`, `--config` | 拒绝配对 |
| `scheduler` | 无 | 加载计划任务 |
| `model` | `--config` | 交互式模型配置 |
| `mcp serve` | 无 | 启动 MCP server |
| `precompute-sector` | `--data-root`, `--start-date`, `--upload` | 预计算行业数据 |

## 示例

```bash
dojoagents dashboard --host 127.0.0.1 --port 8765
dojoagents model --config ./agents.yaml
dojoagents gateway setup telegram
```

