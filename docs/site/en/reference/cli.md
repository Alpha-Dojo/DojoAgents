# CLI Reference

The CLI parser is defined in `dojoagents/cli/main.py`. The installed console script is:

```bash
dojoagents
```

## Commands

| Command | Arguments | Purpose |
| --- | --- | --- |
| `chat` | `message`, `--profile`, `--market`, `--symbols`, `--timeframe` | Run a local agent request |
| `dashboard` | `--host`, `--port` | Start the FastAPI/React dashboard |
| `gateway` | `--host`, `--port`, `--config` | Start the chat gateway server |
| `gateway setup` | `adapter`, `--config` | Configure one adapter or `all` adapters |
| `gateway pairing list` | `--platform`, `--config` | List pending pairing requests |
| `gateway pairing approve` | `platform`, `code`, `--config` | Approve a pairing code |
| `gateway pairing deny` | `platform`, `code`, `--config` | Deny a pairing code |
| `sessions export` | `--config`, `--session-id`, `--output-dir`, `--format`, `--include-archived`, `--no-raw-strands`, `--no-dojo-sidecars`, `--no-memory`, `--no-token-usage` | Export stored session messages |
| `scheduler` | none | Load configured scheduled jobs and print the count |
| `model` | `--config` | Interactive model/provider configuration |
| `mcp serve` | none | Start the MCP server |
| `precompute-sector` | `--data-root`, `--start-date`, `--upload` | Precompute sector daily metrics and returns |

## Examples

```bash
dojoagents dashboard --host 127.0.0.1 --port 8765
dojoagents model --config ./agents.yaml
dojoagents gateway setup telegram
dojoagents gateway pairing list --platform telegram
dojoagents sessions export --output-dir ~/Desktop/dojo-chat-export
dojoagents sessions export --session-id session-123 --output-dir ~/Desktop/dojo-chat-export
dojoagents precompute-sector --start-date 2025-01-01
```

## Session Export

Use `sessions export` to export backend session messages without starting the dashboard. By default it exports all visible sessions; pass `--session-id` to export only one session:

```bash
dojoagents sessions export \
  --config ~/.dojo/agents.yaml \
  --session-id session-123 \
  --output-dir ~/Desktop/dojo-chat-export \
  --include-archived
```

The command reads `sessions.root`, `sessions.agent_id`, and `sessions.export_default_dir` from the config file. When `--output-dir` is omitted, the configured `sessions.export_default_dir` is used. If the requested session is archived, include `--include-archived`.

The export bundle includes `messages.jsonl` for audit records, `openai_dataset.jsonl` for OpenAI-compatible conversation data, `sessions.json`, `manifest.json`, Markdown transcripts, and raw Strands session files unless disabled with `--no-raw-strands`.

## Notes

- `dashboard` defaults to `127.0.0.1:8765`.
- `gateway` defaults to `127.0.0.1:8766`.
- Commands that read configuration default to `~/.dojo/agents.yaml`.
- `chat --market` accepts `stock` or `crypto`; `--symbols` is a comma-separated list.
