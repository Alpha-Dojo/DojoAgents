# Dashboard API

Dashboard API 由 `dojoagents/dashboard/server.py` 和 `dojoagents/dashboard/routers/` 注册。`/api/chat` 是 Agent 主入口；`/api/chat/runs` 提供后台 run 生命周期；`/api/v1/*` 提供 Dashboard 金融领域数据和 session 查询。

## 基础入口

| Method | Path | 说明 |
| --- | --- | --- |
| `GET` | `/api/health` | 健康检查，返回 `{"ok": true}` |
| `GET` | `/api/config` | 返回 `ConfigStore.redacted()` 的脱敏配置 |
| `PUT` | `/api/config` | deep-merge 用户配置并保存到配置文件 |
| `GET` | `/api/jobs` | 返回 scheduler 当前 job 列表 |
| `GET` | `/api/extensions` | 返回已注册 Dojo extension 状态 |
| `GET` | `/` | React Dashboard SPA |

## Chat

### `POST /api/chat`

支持 OpenAI-compatible 请求，也保留 legacy 请求格式。

OpenAI-compatible 请求：

```json
{
  "model": "default",
  "messages": [
    {"role": "user", "content": "分析半导体板块"}
  ],
  "stream": true,
  "metadata": {
    "session_id": "session-123",
    "event_format": "dojo.v2",
    "locale": "zh"
  }
}
```

解析规则：

- `messages` 必须是非空数组，并且包含至少一条非空 `user` 消息。
- 最后一条非空 `user` 消息作为当前输入；它之前的消息写入 `metadata.history`。
- `metadata.session_id` 缺省时由后端生成。
- `metadata.event_format` 缺省为 `openai.v1`；设置为 `dojo.v2` 时返回 Dojo typed events。
- `metadata.quant` 可传入 `QuantContext` 字段。

Legacy 请求：

```json
{
  "message": "分析我的组合",
  "user_id": "local",
  "session_id": "cli",
  "channel": "dashboard"
}
```

非流式响应是 OpenAI-compatible `chat.completion`，并额外保留 `content` 与 `session_id` legacy 字段。流式响应是 SSE，每个 `data:` chunk 兼容 OpenAI `chat.completion.chunk`；`dojo.v2` 模式下 chunk 附带 `dojo_event`。

## Run Lifecycle

| Method | Path | 说明 |
| --- | --- | --- |
| `POST` | `/api/chat/runs` | 创建后台 Agent run，返回 `run_id`、`session_id`、`status`、`model` |
| `GET` | `/api/chat/runs/{run_id}` | 查询 run 状态和事件数量 |
| `POST` | `/api/chat/runs/{run_id}/cancel` | 取消运行中的 run |
| `GET` | `/api/chat/runs/{run_id}/events?cursor=0` | 从指定事件序号开始以 SSE 读取 run events |
| `GET` | `/api/chat/sessions/{session_id}/tokens` | 返回 token ledger 快照；不是完整 session 查询接口 |

`/api/chat/runs/{run_id}/events` 在 run 结束后停止输出；未知 `run_id` 返回 404。

## Session API

Session API 由 `chat_sessions` router 挂在 `/api/v1/chat/sessions`。

| Method | Path | 说明 |
| --- | --- | --- |
| `GET` | `/api/v1/chat/sessions?limit=50&cursor=&include_archived=false` | 分页列出 session |
| `GET` | `/api/v1/chat/sessions/{session_id}` | 查询 session sidecar 元数据 |
| `GET` | `/api/v1/chat/sessions/{session_id}/messages?limit=200&offset=0` | 查询 session 消息 |
| `POST` | `/api/v1/chat/sessions/{session_id}/archive` | 归档 session |
| `POST` | `/api/v1/chat/sessions/export` | 导出所有 session 到配置或请求指定目录 |

默认 session 根目录和导出目录由 `sessions.root`、`sessions.export_default_dir` 控制。

## Domain Routers

所有 domain router 都挂在 `/api/v1` 前缀下。

| Router | 主要路径 | 说明 |
| --- | --- | --- |
| `utility` | `/utility/search/company-ticker`, `/utility/taxonomy/tree` | 公司/股票搜索和行业树 |
| `market` | `/market/overview`, `/market/sector-movers`, `/market/screener` | 市场概览、行业涨跌、股票筛选 |
| `markets` | `/markets/stats`, `/markets/{market}/stats` | 市场统计 |
| `sector` | `/sector/analysis`, `/sector/constituents` | 行业分析和成分股 |
| `sectors` | `/sectors/taxonomy` | L1/L2/L3 行业分类文档 |
| `ticker` | `/ticker/quote`, `/ticker/financials`, `/ticker/news-events`, `/ticker/price-trends` | ticker 聚合查询 |
| `portfolio` | `/portfolio`, `/portfolio/manage`, `/portfolio/holdings`, `/portfolio/allocate` | v1 portfolio 操作和分析 |
| `dojo-core` | `/dojo-core/tickers/search`, `/dojo-core/ticker/*` | DojoCore ticker 搜索、quote、sector、kline、PE band、财务和资讯 |
| `dojo-folio` | `/dojo-folio/portfolios`, `/dojo-folio/portfolios/{id}` | 原生 portfolio CRUD、持仓、自动配置 |
| `dojo-mesh` | `/dojo-mesh/benchmarks`, `/dojo-mesh/sectors`, `/dojo-mesh/sectors/cross-market` | 跨市场基准和行业领先/落后 |
| `dojo-sphere` | `/dojo-sphere/sectors/*`, `/dojo-sphere/constituents/*` | 行业范围指标、成分股、表现和 K 线 |

常见 market 参数：

- legacy domain API 使用 `cn|sh|hk|us`。
- DojoCore/DojoSphere 多数新接口使用 `sh|hk|us`。

## 错误处理

- 请求体不是 JSON 或字段不合法时，返回 422 或 400。
- 未找到 session、run、ticker、portfolio、sector 时，返回 404。
- 可预期业务失败使用 `fastapi.HTTPException` 或 `JSONResponse(status_code=..., content={"error": ...})`。
- 配置文件不可写时，`PUT /api/config` 返回 403。

## 相关代码

- `dojoagents/dashboard/server.py`
- `dojoagents/dashboard/routers/`
- `dojoagents/dashboard/schemas/`
- `dojoagents/agent/events.py`
