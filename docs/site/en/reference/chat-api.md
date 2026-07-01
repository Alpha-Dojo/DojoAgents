# Chat API

`POST /api/chat` is the main dashboard agent entrypoint. It accepts OpenAI Chat Completions-style requests and the legacy DojoAgents request shape.

## OpenAI-Compatible Request

```json
{
  "model": "default",
  "messages": [
    {"role": "system", "content": "You are a quantitative finance assistant"},
    {"role": "user", "content": "Analyze today's market structure"}
  ],
  "stream": true,
  "metadata": {
    "session_id": "session-123",
    "event_format": "dojo.v2",
    "locale": "en",
    "channel": "dashboard"
  }
}
```

Parsing rules:

- `messages` must be a non-empty array.
- The last non-empty `user` message becomes the current agent input.
- Messages before that user message are stored in `metadata.history` for OpenAI-style history compatibility.
- `metadata.session_id` is generated when omitted.
- `metadata.event_format` may be `openai.v1` or `dojo.v2`.
- `metadata.quant` may contain quantitative context such as `market`, `symbols`, and `timeframe`.

## Legacy Request

```json
{
  "message": "Analyze today's market structure",
  "user_id": "local",
  "session_id": "cli",
  "channel": "dashboard",
  "metadata": {
    "locale": "en"
  }
}
```

Legacy requests do not enable streaming and default to `openai.v1`.

## Response

Non-streaming responses return OpenAI-compatible `chat.completion` objects:

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

In `dojo.v2` mode, non-streaming responses also include metadata:

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

Streaming responses use `text/event-stream`. Each `data:` line is an OpenAI-compatible `chat.completion.chunk`; `dojo.v2` mode adds `dojo_event`.

## Errors

- Empty `messages` or no non-empty user message: 422.
- Legacy requests missing `message`, `user_id`, or `session_id`: request parsing failure.
- Agent execution exceptions end the run and, when sessions are enabled, mark the session run as failed.

## Related Pages

- [dojo.v2 Protocol](dojo-v2-protocol.md)
- [Dashboard API](dashboard-api.md)
