# CLI

`dojoagents` is the console entry point for local chat, dashboard startup, gateway startup, model setup, scheduling, and data precomputation.

## Common Commands

```bash
dojoagents chat "Analyze BTC market structure" --market crypto --symbols BTC-USD --timeframe 1d
dojoagents dashboard --host 127.0.0.1 --port 8765
dojoagents gateway --host 127.0.0.1 --port 8766
dojoagents gateway setup all
dojoagents scheduler
dojoagents model
dojoagents precompute-sector
```

## Command Summary

| Command | Purpose |
| --- | --- |
| `chat` | Run a local agent request |
| `dashboard` | Start the FastAPI dashboard |
| `gateway` | Start the chat gateway |
| `gateway setup` | Configure platform adapters |
| `gateway pairing` | Manage pairing requests |
| `scheduler` | Load scheduled jobs |
| `model` | Configure an LLM provider |
| `mcp serve` | Start the MCP server |
| `precompute-sector` | Precompute sector daily data |

