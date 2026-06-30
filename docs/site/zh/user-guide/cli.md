# CLI

## 适用场景

`dojoagents` 是项目的控制台入口，用于本地聊天、启动 Dashboard、启动 Gateway、配置模型和运行调度器。

## 常用命令

```bash
dojoagents chat "Analyze BTC market structure" --market crypto --symbols BTC-USD --timeframe 1d
dojoagents dashboard --host 127.0.0.1 --port 8765
dojoagents gateway --host 127.0.0.1 --port 8766
dojoagents gateway setup all
dojoagents scheduler
dojoagents model
```

开发环境中可以通过 `uv run` 调用：

```bash
uv run --extra dev dojoagents --help
```

## 命令概览

| 命令 | 用途 |
| --- | --- |
| `chat` | 从命令行发起一次 Agent 请求 |
| `dashboard` | 启动 FastAPI Dashboard 服务 |
| `gateway` | 启动聊天网关服务 |
| `gateway setup` | 交互式配置 Slack、Telegram、WeChat 等 adapter |
| `gateway pairing` | 查看、批准或拒绝配对请求 |
| `scheduler` | 加载并检查计划任务 |
| `model` | 交互式配置 LLM provider |
| `mcp serve` | 启动 MCP server |

## 深入阅读

- [CLI Reference](../reference/cli.md)
- [模型配置](../getting-started/model-configuration.md)
- [Gateway](gateway.md)
