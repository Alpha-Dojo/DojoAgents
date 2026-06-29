# First Agent Run

## CLI

```bash
dojoagents chat "Analyze BTC market structure" --market crypto --symbols BTC-USD --timeframe 1d
```

Prompt interactively:

```bash
dojoagents chat
```

## Dashboard

1. Start the dashboard.
2. Open `http://127.0.0.1:8765/`.
3. Enter an analysis request in the chat input.
4. Watch agent messages, tool activity, visualization blocks, and the final answer.

## API

```bash
curl -N http://127.0.0.1:8765/api/chat \
  -H "Content-Type: application/json" \
  -d '{
    "model": "default",
    "messages": [{"role": "user", "content": "Summarize today market structure"}],
    "stream": true,
    "metadata": {"session_id": "quickstart", "event_format": "dojo.v2"}
  }'
```

