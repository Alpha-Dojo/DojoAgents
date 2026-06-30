# Session Design and Integration

## Overview

DojoAgents treats sessions as part of the agent runtime instead of leaving persistence to the dashboard frontend. The runtime creates a Strands `SessionManager` for each `session_id`, stores the canonical transcript through a Dojo-backed `SessionRepository`, and lets the dashboard query, archive, and export through API calls.

This design is meant to:

- make the backend the source of truth for chat history;
- let the same `session_id` automatically restore context for the next turn;
- keep memory synced with session history without storing the exact transcript inside memory files;
- let the dashboard and export workflows reuse the same runtime session layer.

## Storage Layout

Default session root:

```text
~/.dojo/agents/strands_sessions
```

Each session uses a Strands-compatible directory layout:

```text
session_<session_id>/
├── session.json
├── dojo_session.json
├── dojo_turns.jsonl
├── dojo_memory.json
├── agents/
│   └── agent_<agent_id>/
│       ├── agent.json
│       └── messages/
│           ├── message_0.json
│           ├── message_1.json
│           └── ...
└── multi_agents/
```

Responsibility split:

- `session.json`, `agent.json`, and `message_*.json`: native Strands session and message storage.
- `dojo_session.json`: Dojo dashboard-facing metadata such as title, status, message count, turn count, token state, and memory state.
- `dojo_turns.jsonl`: per-run events, tool traces, and usage snapshots.
- `dojo_memory.json`: memory synchronization output tied to the session.

## Configuration

Configure sessions through the `sessions` block in `~/.dojo/agents.yaml`:

```yaml
sessions:
  enabled: true
  provider: dojo_repository
  root: ~/.dojo/agents/strands_sessions
  agent_id: dojo-agent
  persist_openai_history: true
  sync_memory: true
  export_default_dir: ~/Desktop/dojo-chat-export
```

Field summary:

- `enabled`: enables runtime session support.
- `provider`: `dojo_repository` is the recommended setting. `strands_file` remains compatible, but the richer dashboard sidecars are centered on `dojo_repository`.
- `root`: session storage root.
- `agent_id`: Strands agent identifier. Changing it changes which stored agent state is restored for a session.
- `persist_openai_history`: compatibility switch for requests that still send OpenAI-style history arrays.
- `sync_memory`: syncs completed turns into memory after each successful run.
- `export_default_dir`: default export directory when the API payload does not specify one.

## Runtime Behavior

Both `/api/chat` and `/api/chat/runs` go through the same runtime session lifecycle:

1. `begin_run` creates or updates `dojo_session.json` and marks the session as running.
2. Strands `SessionManager` restores existing messages for the `session_id`.
3. The agent continues from the current input instead of requiring the frontend to resend the entire transcript.
4. `finish_run` updates sidecars, records turn events, and syncs memory.
5. Failures or cancellations update session status and error metadata.

Recommended contract:

- the frontend sends a stable `session_id`;
- the backend restores context from session storage;
- the dashboard sends only the latest user input for the next run.

## Dashboard APIs

Use the `/api/v1` session APIs for dashboard features:

- `GET /api/v1/chat/sessions`
- `GET /api/v1/chat/sessions/{session_id}`
- `GET /api/v1/chat/sessions/{session_id}/messages`
- `POST /api/v1/chat/sessions/{session_id}/archive`
- `POST /api/v1/chat/sessions/export`

These endpoints are intended for session lists, session detail views, transcript loading, archival, and full exports.

Compatibility endpoint:

- `GET /api/chat/sessions/{session_id}/tokens`

That route only returns token ledger state. It is not a replacement for the session query APIs.

## Export

Export endpoint:

```text
POST /api/v1/chat/sessions/export
```

If no output directory is provided, exports go to:

```text
~/Desktop/dojo-chat-export
```

An export bundle includes:

- `sessions.json`
- `messages.jsonl`
- `manifest.json`
- `transcripts/*.md`
- a `strands/` copy of raw session files

This is suitable for audit, replay, backup, and external archival workflows.

## Development Notes

- Mount `sessions.root` on durable storage instead of ephemeral container layers.
- If the dashboard is deployed with multiple instances, either share the same session storage or intentionally isolate session roots per instance.
- If exports are enabled, make sure `export_default_dir` is writable by the runtime user.
- If memory sync is enabled, back up memory data together with the session storage root.
- If `agent_id` or `sessions.root` changes, treat that as a session-restore boundary change and review visibility of existing sessions before rollout.

## Common Issues

### No history appears after switching sessions

Check:

- whether the frontend calls `GET /api/v1/chat/sessions/{session_id}/messages` after switching;
- whether `agents/agent_<agent_id>/messages/` exists for that session;
- whether `agent_id` changed and split the visible restore scope.

### A new turn does not inherit prior context

Check:

- whether the frontend reused the original `session_id`;
- whether `sessions.enabled` is on;
- whether `AgentLoop` successfully attached a `session_manager`.

### Export output is empty or incomplete

Check:

- whether the export target directory is writable;
- whether the target session has completed at least one `finish_run`;
- whether sidecar files were cleaned up externally.
