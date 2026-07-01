# dojo.v2 协议

`dojo.v2` 是 DojoAgents 在 OpenAI-compatible Chat API 上附加 typed event 的协议层。客户端通过请求：

```json
{
  "metadata": {
    "event_format": "dojo.v2"
  }
}
```

启用该协议。

## 传输形态

| 模式 | 传输 | Dojo event 位置 |
| --- | --- | --- |
| `stream=false` | 普通 JSON 响应 | `metadata.dojo.events`，同时响应体保留 `content`、`session_id` legacy 字段 |
| `stream=true` | SSE | OpenAI-compatible chunk 上附加 `dojo_event` |
| `/api/chat/runs/{run_id}/events` | SSE | 每条 `data:` 直接是一个 Dojo event JSON |

未启用 `dojo.v2` 时，客户端应只依赖 OpenAI-compatible 字段。

## 公共字段

每个 Dojo event 都包含：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `schema_version` | string | 当前为 `2.0` |
| `run_id` | string | 本轮运行 ID |
| `seq` | integer | run 内递增事件序号，从 1 开始 |
| `session_id` | string | 会话 ID |
| `timestamp` | string | UTC ISO timestamp |
| `type` | string | 事件类型 |

客户端应使用 `(run_id, seq)` 去重和排序。工具事件使用 `call_id` 关联 `tool_start` 和 `tool_result`。

## 事件类型

| `type` | 关键字段 | 说明 |
| --- | --- | --- |
| `phase` | `phase` | Agent 阶段变化，例如 planning、tooling、answering |
| `delta` | `text` | 模型输出文本增量 |
| `think_start` | `summary` | thinking 段开始；内容可能已脱敏或摘要化 |
| `think_delta` | `text` | thinking 文本增量；受 `agent.enable_think_scrubbing` 影响 |
| `think_end` | `summary` | thinking 段结束 |
| `retry` | `attempt`, `max_attempts`, `text` | provider 或运行时重试提示 |
| `tool_start` | `call_id`, `tool`, `arguments` | 工具开始执行 |
| `tool_result` | `call_id`, `tool`, `ok`, `content`, `error`, `latency_ms` | 工具执行完成 |
| `eval_hint` | `text`, `issues` | 评估或 guardrail 提示 |
| `token_usage` | token 快照字段 | session token 账本快照 |
| `context_compacted` | `compression_count`, `estimated_prompt_tokens` | 上下文压缩完成 |
| `done` | `model_id`, `tool_trace`, `tool_steps` | run 成功结束 |
| `error` | `message`, `code` | run 失败 |

## `tool_result` 扩展

`tool_result` 可携带结构化展示数据：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `data` | any | 工具结构化结果 |
| `viz_blocks` | array | Agent 可视化块 |
| `artifacts` | array | 文件、图表、导出等产物 |
| `resource_changes` | array | 资源变更提示，例如 portfolio/session 数据变化 |
| `truncated` | boolean | 工具输出是否被截断 |
| `latency_ms` | integer | 工具执行耗时 |

工具结果仍应通过 `ToolExecutor` 归一化，不要让 handler 返回任意不可预期结构。

## `token_usage`

`token_usage` 包含：

- `last_prompt_tokens`
- `last_completion_tokens`
- `last_total_tokens`
- `session_max_tokens`
- `compression_threshold_ratio`
- `utilization_ratio`
- `cumulative_total_tokens`
- `compression_count`
- `model_context_window`
- `loop_count`

它用于 Dashboard 显示 session token 状态，也用于判断上下文压缩是否接近阈值。

## 兼容性

- OpenAI-compatible 客户端可以忽略 `dojo_event` 和 `metadata.dojo`。
- Dojo-aware 客户端应优先消费 `dojo.v2` event，而不是解析自然语言内容中的工具痕迹。
- 前端恢复运行状态时，应以 `run_id`、`seq`、`call_id` 为稳定标识。
- 历史 session 查询使用 `/api/v1/chat/sessions/*`，不要用 `/api/chat/sessions/{session_id}/tokens` 还原 transcript。

## 相关代码

- `dojoagents/agent/events.py`
- `dojoagents/dashboard/server.py`
- `dojoagents/agent/models.py`
