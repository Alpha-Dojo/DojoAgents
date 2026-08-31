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
| `precompute-sector` | `--data-root`, `--start-date`, `--trade-date`, `--market`, `--upload-api`, `--upload` | 预计算行业数据；可按市场通过 qdata API 写入云服务 |
| `precompute-sector-theme-state` | `--data-root`, `--input-dir`, `--output-dir`, `--start-date`, `--end-date`, `--upload`, `--skip-fundamentals`, `--skip-volume-enrich` | 读取 `precompute-sector` 快照，发布统一主题状态数据，并可上传到 `dojo_sector_precomputed` |
| `attribution-factor-crawl` | `--date`, `--concurrency`, `--top-n`, `--min-cap`, `--force-rerun`, `--write-only`, `--skip-write` | 爬取单日板块归因，并通过 `create_attribution_factor` 批量写入 |
| `sector-brief-extract` | `--date`, `--market`, `--lookback-days`, `--concurrency`, `--max-attempts`, `--model`, `--force-rerun`, `--write-only`, `--skip-write` | 从归因因子提取板块简报，并通过 `create_sector_brief_extract` 批量写入 |
| `tasks run` | `--pipeline`, `--date`, `--config`, `--local`, `--force`, `--force-rerun`, … | 运行 Task 流水线（需 `tasks.enabled`） |
| `tasks eval` | `--task`, `--date`, `--config`, `--artifact` | 按 contract schema 校验任务产物 |

## 示例

```bash
dojoagents dashboard --host 127.0.0.1 --port 8765
dojoagents model --config ./agents.yaml
dojoagents gateway setup telegram
dojoagents sessions export --output-dir ~/Desktop/dojo-chat-export
dojoagents sessions export --session-id session-123 --output-dir ~/Desktop/dojo-chat-export
dojoagents precompute-sector --market cn --start-date 2026-08-12 --trade-date 2026-08-12 --upload-api
dojoagents precompute-sector-theme-state --upload
dojoagents attribution-factor-crawl --date 2026-07-31
dojoagents attribution-factor-crawl --date 2026-07-31 --market cn
dojoagents attribution-factor-crawl  # 日期默认为本机当天
dojoagents sector-brief-extract --date 2026-07-31 --market cn
dojoagents sector-brief-extract --date 2026-07-31 --market cn --model deepseek-v4-flash-0731
dojoagents sector-brief-extract  # 日期默认为本机当天
dojoagents tasks run --pipeline daily-market-events --date 2026-07-22
dojoagents tasks eval --task event-trigger --date 2026-07-22
```

默认情况下，`precompute-sector-theme-state` 从
`<data-root>/dojo_sector_precomputed` 读取并发布到同一目录。需要保留独立的
Phase A 输入快照与统一输出时，可分别指定 `--input-dir` 和 `--output-dir`。

Precompute 产物由 Agent 侧 **`dojo.sdk.sector.precomputed_*`** 消费（见 [DojoSDK](dojo-sdk.md)）。  
任务流水线说明见 [任务与流水线](../user-guide/tasks-and-pipelines.md)。

`attribution-factor-crawl` 会校验当日 JSONL，并通过 `analysis.create_attribution_factor` 批量写入。
它不再下载、合并或上传 `dojo_attribution_factor` 的 HF/ModelScope 数据集，也不再需要 HF/ModelScope
token。任一板块任务失败时默认停止写入；确认接受部分结果时才使用 `--allow-partial`。仅重试接口写入
可使用 `--write-only`，本地只校验可使用 `--skip-write`；旧的 `--merge-only`、`--skip-upload` 仍作为
兼容别名。所选日期已有合法且非空的板块输出时，会按板块复用并跳过对应任务；使用 `--force-rerun`
可强制重新生成全部所选板块。省略 `--date`，或只写 `--date` 而不跟值时，使用本机时区当天日期。
普通爬取默认依赖 Dashboard 运行时：命令会复用健康的本地 Dashboard；如果不存在，则使用同一份
`agents.yaml` 自动启动临时 Dashboard，等待服务就绪，并在任务结束后关闭。临时进程会跳过 DojoSDK
全量离线预下载和周期刷新，但仍正常加载爬取 API 与任务运行时所需的 Dashboard registry。`--write-only` 不会启动
Dashboard。远程 `--dashboard-url` 必须由调用方保证服务已运行。

`sector-brief-extract` 会在所选日期向前 `--lookback-days` 个日历日的 AttributionFactor
中发现板块，为每个 `(market, sector_id)` 运行一次 Task，校验 JSON 产物后通过
`analysis.create_sector_brief_extract` 批量写入接口。已有合法产物默认复用；
`--force-rerun` 强制重跑，`--write-only` 仅提交已有产物，`--skip-write` 仅校验。
远程 Task 与归因爬取一样需要 Dashboard；没有待运行 Task 时不会启动临时 Dashboard。
每个板块 job 默认最多执行 3 次，并在每次执行后立即校验产物；连续失败后仅记录并跳过，
其他板块和有效产物的写入继续进行。可用 `--max-attempts` 调整次数。`--model` 可覆盖本次
Task 使用的模型 ID，但沿用 `agents.yaml` 当前配置的 provider。

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
