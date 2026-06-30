# Dashboard

Dashboard 是本地 Web UI，用于与 Agent 对话、查看工具执行过程、浏览金融数据、使用可视化结果，并管理会话历史。

## 启动

```bash
dojoagents dashboard --host 127.0.0.1 --port 8765
```

打开：

```text
http://127.0.0.1:8765/
```

首次使用建议先完成模型配置：

```bash
dojoagents model
```

也可以在 Dashboard 设置界面写入模型配置。配置会保存到 `~/.dojo/agents.yaml`。

## 常用工作流

1. 启动 Dashboard。
2. 在设置里确认 provider、model、base URL 和 API key。
3. 在 Agent 对话区输入金融分析问题。
4. 查看工具执行、结构化结果和可视化块。
5. 需要继续追问时复用同一个 session。
6. 需要归档或备份时使用 session 导出接口。

Dashboard 的后端是 session 权威来源；新一轮对话只需要发送当前输入，不需要前端重复提交完整 transcript。

## API 入口

| Method | Path | 说明 |
| --- | --- | --- |
| `GET` | `/api/health` | 健康检查 |
| `GET` | `/api/config` | 脱敏配置 |
| `PUT` | `/api/config` | 更新配置 |
| `GET` | `/api/jobs` | 计划任务 |
| `GET` | `/api/extensions` | 已注册扩展 |
| `POST` | `/api/chat` | OpenAI-compatible chat |
| `POST` | `/api/chat/runs` | 后台 Agent run |
| `GET` | `/api/chat/runs/{run_id}/events` | run event SSE |
| `GET` | `/api/v1/chat/sessions` | session 列表 |
| `GET` | `/` | React SPA |

完整接口见 [Dashboard API Reference](../reference/dashboard-api.md)。

## 数据目录

常用本地目录：

| 路径 | 用途 |
| --- | --- |
| `~/.dojo/agents.yaml` | 主配置文件 |
| `~/.dojo/dashboard-data` | Dashboard 金融数据和派生缓存 |
| `~/.dojo/agents/strands_sessions` | session 历史 |
| `~/Desktop/dojo-chat-export` | 默认 session 导出目录 |

这些路径可通过 [配置](../reference/configuration.md) 中的 `dashboard.financial` 和 `sessions` 段调整。

## 前端开发

```bash
cd dojoagents/dashboard/web
npm run dev
```

Vite 默认代理后端 `http://127.0.0.1:8765/api`。开发时通常同时运行：

```bash
dojoagents dashboard --host 127.0.0.1 --port 8765
```

## 网络暴露

默认建议只绑定 `127.0.0.1`。如果绑定 `0.0.0.0` 或部署到公网，需要先补充认证、访问控制、网络隔离和 secret 管理。`/api/config` 返回的是脱敏配置，但仍不建议把未加保护的 Dashboard 暴露到公网。

## 常见问题

Dashboard 无法打开：

- 确认后端命令仍在运行。
- 访问 `http://127.0.0.1:8765/api/health`。
- 如果从源码运行，确认前端已构建或开发服务已启动。

模型请求失败：

- 确认 `llm_provider.default` 指向存在的 provider。
- 确认 provider 的 `model`、`base_url`、`api_key_env` 或 `api_key` 正确。
- 本地模型服务需要确认 base URL 可访问。

SSE 中断：

- 先查询 `/api/chat/runs/{run_id}` 看 run 是否已经结束。
- 再从 `/api/chat/runs/{run_id}/events?cursor=N` 继续读事件。

看不到历史会话：

- 确认 `sessions.enabled` 为 `true`。
- 确认前端复用了同一个 `session_id`。
- 检查 `sessions.root` 是否指向持久可写目录。

## 深入阅读

- [Dashboard 架构](../architecture/dashboard.md)
- [Dashboard API Reference](../reference/dashboard-api.md)
- [Session 设计与集成](../development/session-history-design.md)
