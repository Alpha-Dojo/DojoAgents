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
| `sessions export` | `--config`, `--session-id`, `--output-dir`, `--format`, `--include-archived`, `--no-raw-strands`, `--no-dojo-sidecars`, `--no-memory`, `--no-token-usage` | 导出已存储的 session messages |
| `scheduler` | 无 | 加载计划任务 |
| `model` | `--config` | 交互式模型配置 |
| `mcp serve` | 无 | 启动 MCP server |
| `precompute-sector` | `--data-root`, `--start-date`, `--upload` | 预计算行业数据 |
| `precompute-sector-theme-state` | `--data-root`, `--input-dir`, `--output-dir`, `--start-date`, `--end-date`, `--upload`, `--skip-fundamentals`, `--skip-volume-enrich` | 读取 `precompute-sector` 快照，发布统一主题状态数据，并可上传到 `dojo_sector_precomputed` |

## 示例

```bash
dojoagents dashboard --host 127.0.0.1 --port 8765
dojoagents model --config ./agents.yaml
dojoagents gateway setup telegram
dojoagents sessions export --output-dir ~/Desktop/dojo-chat-export
dojoagents sessions export --session-id session-123 --output-dir ~/Desktop/dojo-chat-export
dojoagents precompute-sector-theme-state --upload
```

默认情况下，`precompute-sector-theme-state` 从
`<data-root>/dojo_sector_precomputed` 读取并发布到同一目录。需要保留独立的
Phase A 输入快照与统一输出时，可分别指定 `--input-dir` 和 `--output-dir`。

## Session 导出

使用 `sessions export` 可以在不启动 Dashboard 的情况下导出后端已存储的 session messages。默认导出所有可见 session；传 `--session-id` 时只导出指定 session：

```bash
dojoagents sessions export \
  --config ~/.dojo/agents.yaml \
  --session-id session-123 \
  --output-dir ~/Desktop/dojo-chat-export \
  --include-archived
```

该命令会从配置文件读取 `sessions.root`、`sessions.agent_id` 和 `sessions.export_default_dir`。未传 `--output-dir` 时，会使用配置中的 `sessions.export_default_dir`。如果指定的 session 已归档，需要同时传 `--include-archived`。

导出目录包含用于审计的 `messages.jsonl`、符合 OpenAI 对话格式的数据集文件 `openai_dataset.jsonl`、`sessions.json`、`manifest.json`、Markdown transcript，以及原始 Strands session 文件；如不需要原始 Strands 文件，可传 `--no-raw-strands`。
