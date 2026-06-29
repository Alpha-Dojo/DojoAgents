# Chat API

`POST /api/chat` is the main dashboard agent endpoint. It is compatible with OpenAI Chat Completions and supports Dojo-specific metadata.

## Request

```json
{
  "model": "default",
  "messages": [
    {"role": "user", "content": "Summarize today market structure"}
  ],
  "stream": true,
  "metadata": {
    "session_id": "session-123",
    "event_format": "dojo.v2"
  }
}
```

## Response

Non-streaming responses return `chat.completion`. Streaming responses return SSE `chat.completion.chunk` objects. With `dojo.v2`, chunks include `dojo_event`.

