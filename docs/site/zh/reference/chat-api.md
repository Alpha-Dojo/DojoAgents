# Chat API

`POST /api/chat` 是 Dashboard 的主 Agent 入口，兼容 OpenAI Chat Completions 请求格式，也保留 legacy DojoAgents 请求格式。

## OpenAI-compatible 请求

```json
{
  "model": "default",
  "messages": [
    {"role": "system", "content": "你是量化金融助手"},
    {"role": "user", "content": "帮我分析今天的市场结构"}
  ],
  "stream": true,
  "metadata": {
    "session_id": "session-123",
    "event_format": "dojo.v2",
    "locale": "zh",
    "channel": "dashboard"
  }
}
```

解析规则：

- `messages` 必须是非空数组。
- 最后一条非空 `user` 消息会作为当前 Agent 输入。
- 该消息之前的内容会写入 `metadata.history`，用于兼容 OpenAI 风格历史。
- `metadata.session_id` 缺省时自动生成。
- `metadata.event_format` 可为 `openai.v1` 或 `dojo.v2`。
- `metadata.quant` 可传入 `market`、`symbols`、`timeframe` 等量化上下文。

## Legacy 请求

```json
{
  "message": "帮我分析今天的市场结构",
  "user_id": "local",
  "session_id": "cli",
  "channel": "dashboard",
  "metadata": {
    "locale": "zh"
  }
}
```

Legacy 请求不会启用 streaming，默认 `event_format` 是 `openai.v1`。

## 响应

非流式响应返回 OpenAI-compatible `chat.completion`：

```json
{
  "id": "chatcmpl-...",
  "object": "chat.completion",
  "choices": [
    {
      "index": 0,
      "message": {"role": "assistant", "content": "..."},
      "finish_reason": "stop"
    }
  ],
  "content": "...",
  "session_id": "session-123"
}
```

`dojo.v2` 非流式响应会在 metadata 中附带：

```json
{
  "metadata": {
    "dojo": {
      "schema_version": "2.0",
      "run_id": "run-...",
      "events": []
    }
  }
}
```

流式响应是 `text/event-stream`。每行 `data:` 是 OpenAI-compatible `chat.completion.chunk`；启用 `dojo.v2` 时，chunk 上附加 `dojo_event`。

## 错误

- `messages` 为空或没有非空 user message：422。
- legacy 请求缺少 `message`、`user_id` 或 `session_id`：请求解析失败。
- Agent 执行异常会结束 run，并在可用时写入 session 失败状态。

## 深入阅读

- [dojo.v2 协议](dojo-v2-protocol.md)
- [Dashboard API](dashboard-api.md)
