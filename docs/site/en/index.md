# DojoAgents

DojoAgents is a quantitative finance agent runtime. It combines an LLM-driven agent loop, tool execution, skills, memory, scheduled jobs, plugins, chat gateways, and a FastAPI/React dashboard for local financial analysis workflows.

## Start Here

- New users: read [Installation](getting-started/installation.md) and [Start Dashboard](getting-started/quickstart-dashboard.md).
- Model setup: read [Model Configuration](getting-started/model-configuration.md).
- API integration: read [Chat API](reference/chat-api.md) and [dojo.v2 Protocol](reference/dojo-v2-protocol.md).
- Development: read [Repository Map](development/repository-map.md), [Adding Tools](development/adding-tools.md), and [Testing](development/testing.md).
- Architecture: read [Overview](architecture/overview.md).

## Core Areas

| Area | Entry |
| --- | --- |
| Agent runtime | [Runtime](architecture/runtime.md) |
| Dashboard | [Dashboard User Guide](user-guide/dashboard.md) |
| OpenAI-compatible chat | [Chat API](reference/chat-api.md) |
| Tools and sandbox | [Tools and Sandbox](architecture/tools-and-sandbox.md) |
| Skills | [Skills](user-guide/skills.md) |
| Gateway | [Gateway](user-guide/gateway.md) |
| Plugins | [Plugins](architecture/plugins.md) |
| Multi-agent and planning | [Multi-Agent and Planning](architecture/multi-agent-planning.md) |

## Quick Commands

```bash
uv venv
source .venv/bin/activate
uv pip install -e ".[dev]"
```

```bash
cd dojoagents/dashboard/web
npm install
npm run build
```

```bash
dojoagents dashboard --host 127.0.0.1 --port 8765
```

