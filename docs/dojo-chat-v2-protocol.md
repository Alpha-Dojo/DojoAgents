# DojoAgents `/api/chat` `dojo.v2` 协议说明

## 1. 目标

`dojo.v2` 是建立在 OpenAI Chat Completions 兼容层之上的 DojoAgents 专用扩展，用于把 Agent 运行过程中的阶段、工具执行、结构化结果和结束状态暴露给前端。

设计原则：

- 继续保留唯一入口：`POST /api/chat`
- 普通 OpenAI 客户端无需修改即可忽略扩展字段
- Dashboard 主前端通过 `dojo_event` / `dojo` 获取 richer agent state

## 2. 请求协商

请求保持 OpenAI 兼容，仅通过 `metadata` 协商扩展：

```json
{
  "model": "gpt-4.1",
  "messages": [
    {"role": "user", "content": "帮我分析我的组合风险"}
  ],
  "stream": true,
  "user": "dashboard",
  "metadata": {
    "session_id": "session-123",
    "channel": "dashboard",
    "locale": "zh",
    "event_format": "dojo.v2"
  }
}
```

关键扩展字段：

| 字段 | 说明 |
| :--- | :--- |
| `metadata.session_id` | 会话归属 |
| `metadata.channel` | 渠道来源 |
| `metadata.locale` | 回答目标语言 |
| `metadata.event_format` | `openai.v1` 或 `dojo.v2` |

兼容规则：

- 缺省 `metadata.event_format` 时，保持 `openai.v1`
- 后端会从标准 `messages` 自动提取最后一个非空 `user` 消息作为本轮 prompt
- 后端会从 `messages` 自动构造历史，`metadata.history` 只作为旧客户端 fallback

## 3. 流式响应

流式响应仍是 `text/event-stream`，每帧 `data:` 都是 OpenAI-compatible chunk。

### 3.1 `openai.v1`

仅包含标准字段：

- `id`
- `object = "chat.completion.chunk"`
- `created`
- `model`
- `choices[0].delta`
- `choices[0].finish_reason`

### 3.2 `dojo.v2`

在标准 chunk 顶层增加 `dojo_event`：

```json
{
  "id": "chatcmpl-dojo-abc",
  "object": "chat.completion.chunk",
  "created": 1782230400,
  "model": "gpt-4.1",
  "choices": [{"index": 0, "delta": {}, "finish_reason": null}],
  "dojo_event": {
    "schema_version": "2.0",
    "run_id": "run-abc",
    "seq": 3,
    "type": "phase",
    "session_id": "session-123",
    "timestamp": "2026-06-24T10:00:00+00:00",
    "phase": "tools"
  }
}
```

公共字段：

| 字段 | 说明 |
| :--- | :--- |
| `schema_version` | 当前固定为 `2.0` |
| `run_id` | 一次 `/api/chat` 调用的唯一运行 ID |
| `seq` | 单次运行内严格递增 |
| `type` | 事件类型 |
| `session_id` | 会话 ID |
| `timestamp` | UTC ISO 时间戳 |

事件类型：

| `type` | 关键字段 | 说明 |
| :--- | :--- | :--- |
| `phase` | `phase` | `planning` / `tools` / `answering` |
| `delta` | `text` | 文本增量镜像 |
| `tool_start` | `call_id`, `tool`, `arguments` | 工具开始 |
| `tool_result` | `call_id`, `tool`, `ok`, `content`, `error`, `latency_ms`, `data`, `resource_changes` | 工具完成 |
| `retry` | `attempt`, `max_attempts`, `text` | 重试提示 |
| `eval_hint` | `text`, `issues` | 评估提示 |
| `done` | `model_id`, `tool_trace`, `tool_steps` | Agent 正常完成 |
| `error` | `message`, `code` | Agent 失败结束 |

## 4. 非流式响应

非流式时，仍返回 OpenAI `chat.completion` 响应；在 `dojo.v2` 模式下追加顶层 `dojo` 字段：

```json
{
  "id": "chatcmpl-dojo-abc",
  "object": "chat.completion",
  "created": 1782230400,
  "model": "gpt-4.1",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "分析已完成"
      },
      "finish_reason": "stop"
    }
  ],
  "usage": {
    "prompt_tokens": 120,
    "completion_tokens": 48,
    "total_tokens": 168
  },
  "dojo": {
    "schema_version": "2.0",
    "run_id": "run-abc",
    "events": [
      {"type": "phase", "phase": "planning"},
      {"type": "tool_start", "call_id": "call_001", "tool": "portfolio_read_detail"},
      {"type": "tool_result", "call_id": "call_001", "ok": true},
      {"type": "done", "tool_steps": 1}
    ]
  },
  "content": "分析已完成",
  "session_id": "session-123"
}
```

说明：

- `dojo.events` 为同一轮运行的完整 typed event 序列
- `content` / `session_id` 为兼容旧调用方保留

## 5. 工具结果扩展

`tool_result` 事件是这次升级的核心。相比只传文本，它额外保留：

| 字段 | 说明 |
| :--- | :--- |
| `latency_ms` | 工具耗时 |
| `truncated` | 结果是否被截断 |
| `data` | 结构化数据 |
| `viz_blocks` | 前端可消费的展示块 |
| `artifacts` | 附带产物 |
| `resource_changes` | 对前端缓存或领域资源的刷新提示 |

当前 Dashboard portfolio 写操作会产生 `resource_changes`，用于前端触发 Folio 数据刷新。

## 6. 前端消费建议

- 只需要兼容 OpenAI 的客户端：继续读取 `choices[0]`
- Dashboard React 主前端：显式请求 `metadata.event_format = "dojo.v2"`，并消费 `dojo_event`
- 新前端 reducer 应以 `run_id + seq` 作为事件排序与去重依据

## 7. 当前不承诺的能力

- 不返回原始 chain-of-thought
- 不提供第二套 `/api/v1/agent/*` 接口
- 不保证所有 provider 都产生 reasoning 事件
- 不要求所有工具都提供 `viz_blocks`
