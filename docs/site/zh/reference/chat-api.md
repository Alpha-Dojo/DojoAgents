# Chat API

## 状态

`POST /api/chat` 是 Dashboard 的主 Agent 入口，兼容 OpenAI Chat Completions 请求格式，也保留部分 legacy 请求字段。

## 请求

```json
{
  "model": "default",
  "messages": [
    {"role": "user", "content": "帮我分析今天的市场结构"}
  ],
  "stream": true,
  "metadata": {
    "session_id": "session-123",
    "event_format": "dojo.v2"
  }
}
```

## 响应

非流式响应返回 OpenAI-compatible `chat.completion`。当启用 `dojo.v2` 时，响应顶层可包含 `dojo` 扩展字段。

流式响应返回 SSE，每行是 OpenAI-compatible `chat.completion.chunk`；当启用 `dojo.v2` 时，chunk 顶层包含 `dojo_event`。

## 兼容性

- `stream=false` 用于普通 HTTP 响应。
- `stream=true` 用于 SSE。
- `metadata.event_format="dojo.v2"` 启用 Dojo typed events。
- 未请求 `dojo.v2` 时，客户端应只依赖 OpenAI 标准字段。

## 深入阅读

[dojo.v2 协议](dojo-v2-protocol.md)

