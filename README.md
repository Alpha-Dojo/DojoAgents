<div align="center">
  <img src="https://github.com/Alpha-Dojo/DojoAgents/blob/main/dojoagents/dashboard/web/public/logo.png" alt="DojoAgents Logo">
</div>

# DojoAgents

**English** · [**中文说明**](README_ZH.md)

**DojoAgents** is a quantitative-finance agent runtime. It wires an LLM-driven agent loop, sandboxed tools, procedural skills, memory, scheduled jobs, chat gateways, plugins, and a FastAPI/React dashboard into a cohesive local analysis workflow.

Use it to run market research agents, explore multi-market dashboards, manage portfolios, and deliver analysis through Slack, Telegram, WeChat, and other chat platforms.

---

## Table of Contents

- [Features](#features)
- [Architecture](#architecture)
- [Dashboard Views](#dashboard-views)
- [Tech Stack](#tech-stack)
- [Quick Start](#quick-start)
- [Installation](#installation)
- [Configuration](#configuration)
- [CLI Reference](#cli-reference)
- [Module Guide](#module-guide)
  - [Agent Runtime](#agent-runtime-dojoagentsagent)
  - [Configuration](#configuration-dojoagentsconfig)
  - [Tools & Sandbox](#tools--sandbox-dojoagentstools)
  - [Skills](#skills-dojoagentsskills)
  - [Memory](#memory-dojoagentsmemory)
  - [Cron & Scheduler](#cron--scheduler-dojoagentscron)
  - [Gateway](#gateway-dojoagentsgateway)
  - [Plugins](#plugins-dojoagentsplugins)
  - [Dojo Extensions](#dojo-extensions-dojoagentsdojo_extensions)
  - [Multi-Agent & Planning](#multi-agent--planning)
  - [Quant Context](#quant-context-dojoagentsquant)
  - [Dashboard Backend](#dashboard-backend-dojoagentsdashboard)
  - [Dashboard Frontend](#dashboard-frontend-dojoagentsdashboardweb)
  - [CLI](#cli-dojoagentscli)
- [API Overview](#api-overview)
- [Development](#development)
- [Testing](#testing)
- [Building a Wheel](#building-a-wheel)
- [Documentation Index](#documentation-index)
- [License](#license)

---

## Features

| Area | Capabilities |
|------|--------------|
| **Agent loop** | Multi-turn tool calling, streaming SSE, context compression, guardrails, task harnesses |
| **LLM providers** | OpenAI-compatible endpoints, Gemini native, interactive `dojoagents model` setup |
| **Financial data** | Dojo SDK tools for quotes, K-lines, sectors, fundamentals, news, forex |
| **Dashboard** | Four analysis views — Portfolio, Markets, Sectors, Equities — plus embedded DojoAgent panel |
| **Agent UX** | Run-based chat (`/api/chat/runs`), typed `dojo.v2` events, inline viz blocks, canvas charts |
| **Skills** | Built-in and user skills (`SKILL.md`), lazy loading, Claude skills compatibility |
| **Tools** | Terminal, code execution, web search/extract, MCP servers, plugin tools |
| **Memory** | Pluggable providers; default skill-summary memory writes reusable procedures |
| **Scheduler** | APScheduler-backed cron jobs with YAML persistence |
| **Gateway** | Slack, Telegram, Discord, Feishu, WeCom, WeChat adapters with pairing |
| **Plugins** | Native and Claude-format plugin discovery from `~/.dojo/plugins` |
| **Multi-agent** | Optional agent pool with delegation, orchestrator, and automation hooks |
| **Planning** | Optional plan-driven execution with state store and activation hooks |

---

## Architecture

All entry points — CLI, Dashboard, Gateway, Scheduler — converge on a single **`Runtime`** object built from `ConfigStore`. The runtime owns the agent loop, tool registry, skills, memory, extensions, and job store.

```text
┌─────────────┐  ┌──────────────┐  ┌─────────────┐  ┌──────────────┐
│ CLI chat    │  │ Dashboard    │  │ Gateway     │  │ Scheduler    │
└──────┬──────┘  └──────┬───────┘  └──────┬──────┘  └──────┬───────┘
       │                │                 │                │
       └────────────────┴────────┬────────┴────────────────┘
                                   ▼
                          ┌─────────────────┐
                          │ Runtime         │
                          │  ConfigStore    │
                          │  AgentLoop      │
                          │  ToolExecutor   │
                          │  SkillManager   │
                          │  MemoryManager  │
                          │  Extensions     │
                          └────────┬────────┘
                                   │
              ┌────────────────────┼────────────────────┐
              ▼                    ▼                    ▼
        LLM Provider         Tool Registry         Dojo SDK / MCP
        (OpenAI / Gemini)    (sandboxed)           / Web / Terminal
```

**Design principles**

- **Single config source** — `~/.dojo/agents.yaml` via `ConfigStore`; no ad-hoc YAML parsers.
- **Structured tool results** — every tool returns `{ok, content, error, metadata}` through `ToolExecutor`.
- **Decoupled delivery** — Gateway and Scheduler never bypass `AgentLoop`.
- **Finance at the edges** — market data and dashboard domain logic live in services/extensions, not in the loop itself.

See [`docs/architecture.md`](docs/architecture.md) for the full design document.

---

## Dashboard Views

The React SPA exposes four primary tabs (default homepage: **Portfolio**). Routes use hash-based navigation:

| Route | Tab ID | EN | 中文 | Purpose |
|-------|--------|----|------|---------|
| `/` | `folio` | Portfolio | 组合分析 | Portfolio management, NAV curves, benchmark comparison, holdings, risk exposure, return attribution |
| `#/market` | `market` | Markets | 市场动态 | Multi-market column layout (US/HK/CN), sector movers, cross-market sector links |
| `#/sector` | `sector` | Sectors | 板块发现 | Hierarchical sector taxonomy (L1/L2/L3), scope metrics, performance charts, constituents |
| `#/entity` | `entity` | Equities | 个股分析 | Single-stock deep dive — K-line, PE band, financials, news, events, sector context |

Example URLs (dashboard at `http://127.0.0.1:8765`):

```text
http://127.0.0.1:8765/              # Portfolio (default)
http://127.0.0.1:8765/#/folio       # Portfolio
http://127.0.0.1:8765/#/market      # Markets
http://127.0.0.1:8765/#/sector      # Sectors
http://127.0.0.1:8765/#/entity      # Equities
```

Legacy hash aliases (`#/mesh`, `#/sphere`, `#/core`) are still accepted and automatically rewritten to the new routes.

The **DojoAgent** panel slides in from the right for conversational analysis. On the Portfolio tab it stays pinned; on other tabs it opens on demand. Agent chat uses run-based SSE with `metadata.event_format = "dojo.v2"` for typed tool/phase events.

See [`docs/dashboard.md`](docs/dashboard.md) for the streaming protocol, canvas sandbox, and API details.

---

## Tech Stack

| Layer | Technologies |
|-------|--------------|
| **Python** | `>=3.11`, package `dojoagents` v0.0.1 |
| **Agent core** | `strands-agents`, OpenAI SDK, custom providers |
| **API server** | FastAPI, uvicorn, APScheduler |
| **Data** | pandas, pyarrow, `dojosdk`, exchange-calendars |
| **Integrations** | MCP (`mcp`), httpx, ddgs (web search) |
| **Frontend** | React 19, TypeScript 5.8, Vite 8 |
| **Testing** | pytest, pytest-asyncio |

---

## Quick Start

### Prerequisites

- Python `>=3.11`
- Node.js `>=18` and npm `>=9` (required for frontend development or building from source)
- An LLM API key (e.g. `OPENAI_API_KEY`) or run `dojoagents model` to configure interactively

### Install and run

```bash
# Clone and enter the repository
cd DojoAgents

# Create virtualenv and install with dev extras
uv venv
source .venv/bin/activate
uv pip install -e ".[dev]"

# Build the dashboard frontend
cd dojoagents/dashboard/web
npm install
npm run build
cd ../../..

# Configure LLM (optional if OPENAI_API_KEY is already set)
dojoagents model

# Start the dashboard
dojoagents dashboard --host 127.0.0.1 --port 8765
```

Open **http://127.0.0.1:8765/** in your browser.

For Dojo SDK market data, set:

```bash
export DOJO_API_KEY="your-key"
# optional: export DOJO_BASE_URL="https://api.flowhale.ai"
```

---

## Installation

### Editable install (development)

```bash
uv venv && source .venv/bin/activate
uv pip install -e ".[dev]"
```

### Runtime dependencies only

```bash
uv pip install -r requirements.txt
```

### Install from a pre-built wheel

End users installing a published wheel do **not** need Node.js — the frontend is bundled inside the wheel:

```bash
uv pip install dist/dojoagents-0.0.1-py3-none-any.whl
dojoagents dashboard
```

See [Building a Wheel](#building-a-wheel) for how to produce the wheel locally.

---

## Configuration

Default config path: **`~/.dojo/agents.yaml`**

`ConfigStore` deep-merges user YAML with built-in defaults, expands `${ENV_VAR}` placeholders, redacts secrets for API exposure, and hot-reloads on file change.

Minimal example:

```yaml
version: 1

llm_provider:
  default: openai
  providers:
    openai:
      model: gpt-4.1
      api_key_env: OPENAI_API_KEY

agent:
  max_iterations: 100
  max_tool_workers: 4
  default_skills: []

tools:
  sandbox:
    allowed_roots: ["${PWD}", "/tmp"]
    allow_network: false
    timeout_seconds: 120

memory:
  provider: skill_summary
  generated_skill_dir: "~/.dojo/skills/generated"

scheduler:
  enabled: true
  timezone: Asia/Shanghai
  store: "~/.dojo/agents/jobs.yaml"

gateway:
  enabled: true
  hooks: {}

dashboard:
  host: "127.0.0.1"
  port: 8765
  financial:
    dashboard_data_root: "~/.dojo/dashboard-data"

dojo_extensions:
  enabled:
    - dojo_research

dojosdk:
  cache_dir: "~/.cache/dojo"
```

**Key config sections**

| Section | Purpose |
|---------|---------|
| `llm_provider` | Provider name, model, base URL, API keys |
| `agent` | Iteration limits, skill defaults, compression, guardrails |
| `tools.sandbox` | Filesystem roots, network policy, command allowlist, timeout |
| `tools.web` | Web search/extract backends and limits |
| `memory` | Memory provider selection |
| `skills` | Skill directories, disabled skills, Claude skills import |
| `scheduler` | Job store path and timezone |
| `gateway.hooks` | Per-platform adapter credentials |
| `dashboard.financial` | Local data cache paths, refresh intervals |
| `multi_agent` | Agent pool and delegation (opt-in) |
| `planning` | Plan store and execution engine (opt-in) |
| `mcp_servers` | MCP server connections |
| `logging` | Level and format |

Use `dojoagents model` for interactive LLM setup and `dojoagents gateway setup <adapter>` for chat platform setup. The dashboard **Settings** modal also exposes a redacted config editor via `GET/PUT /api/config`.

---

## CLI Reference

Console entry point: **`dojoagents`** (`dojoagents.cli.main:main`)

| Command | Description |
|---------|-------------|
| `dojoagents chat [message]` | Run a one-shot or interactive local agent session |
| `dojoagents chat --market stock --symbols AAPL,MSFT --timeframe 1d "..."` | Attach quant context |
| `dojoagents dashboard [--host HOST] [--port PORT]` | Start the FastAPI + React dashboard |
| `dojoagents gateway [--host HOST] [--port PORT]` | Start the chat gateway server |
| `dojoagents gateway setup all\|<adapter>` | Interactive gateway adapter configuration |
| `dojoagents gateway pairing list\|approve\|deny` | Manage DM pairing codes |
| `dojoagents model [--config PATH]` | Interactive LLM provider setup |
| `dojoagents scheduler` | Load and report scheduled jobs |
| `dojoagents mcp serve` | Start the MCP server bridge |
| `dojoagents precompute-sector` | Precompute sector daily metrics (see `docs/precompute_sector_daily.md`) |

Development invocation without global install:

```bash
uv run dojoagents dashboard --host 127.0.0.1 --port 8765
# or
uv run dojoagents/cli/main.py dashboard --host 127.0.0.1 --port 8765
```

More usage examples: [`docs/usage.md`](docs/usage.md)

---

## Module Guide

### Agent Runtime (`dojoagents/agent/`)

The heart of the system. **`Runtime.from_config_store()`** wires all dependencies; **`AgentLoop.run()`** executes the turn lifecycle:

1. Build system prompt from config, skills, memory, extensions, and quant context
2. Prefetch memory for the incoming request
3. Call the configured LLM provider
4. Dispatch tool calls through `ToolExecutor` (with optional task harnesses)
5. Repeat until a final answer or iteration budget is exhausted
6. Sync turn memory and emit typed events to SSE sinks

| File | Role |
|------|------|
| `runtime.py` | Object graph composition from `ConfigStore` |
| `loop.py` | AgentLoop orchestration and streaming |
| `models.py` | `ChatRequest`, `ToolCall`, `ToolResult`, OpenAI-compatible completion types |
| `providers.py` | OpenAI-compatible LLM provider |
| `gemini_provider.py` | Gemini native provider |
| `guardrails.py` | Output and tool-call guardrails |
| `compressor.py` | Context-length compression |
| `harnesses/` | Task completion validators (e.g. `PortfolioTaskHarness`) |
| `events.py` | Typed agent event sink for `dojo.v2` protocol |
| `canvas_protocol.py` | DOJO_CHART canvas block protocol |

### Configuration (`dojoagents/config/`)

| File | Role |
|------|------|
| `loader.py` | `ConfigStore` — load, merge, env expansion, redaction, save |
| `models.py` | Frozen dataclass schema (`AgentsConfig` and nested configs) |

Always read config through `ConfigStore.snapshot()` and write updates through `ConfigStore.raw()` + `_deep_merge()` + `save_raw()`.

### Tools & Sandbox (`dojoagents/tools/`)

| Component | Description |
|-----------|-------------|
| `registry.py` | `ToolSpec` / `ToolRegistry` — central tool catalog |
| `executor.py` | Async execution with timeout, sandbox checks, structured errors |
| `sandbox.py` | Filesystem roots, network policy, command allowlist |
| `dojo_sdk_tool.py` | Dojo SDK bindings (`dojo.sdk.stock.kline`, `dojo.sdk.sector.info`, …) |
| `terminal_tool.py` | Sandboxed shell execution |
| `code_execution_tool.py` | In-process Python execution |
| `web_searcher.py` | `web_search` + `web_extract` (ddgs + fetch) |
| `agent_viz.py` | `agent_viz_build` — structured inline chart blocks |
| `mcp_tool.py` | MCP server tool discovery |
| `skill_manage.py` | `skills_list`, `skill_view` |
| `plugin_manage.py` | `plugin_list`, `plugin_delete` |
| `environments/` | Execution backends: local, Docker, SSH, Modal |

### Skills (`dojoagents/skills/`)

Procedural memory as filesystem skills. Each skill is a directory with a `SKILL.md` (YAML frontmatter + instructions).

| Built-in skill | Purpose |
|----------------|---------|
| `canvas-chart` | DOJO_CHART protocol for dashboard canvas rendering |
| `plan` | Plan authoring guidance |
| `writing-plans` | Structured planning templates |
| `subagent-driven-development` | Multi-step subagent workflow |

`SkillManager` discovers skills from `~/.dojo/skills`, generated skills, built-in skills, plugin skill dirs, and optionally `~/.claude/skills`.

### Memory (`dojoagents/memory/`)

| File | Role |
|------|------|
| `provider.py` | `MemoryProvider` protocol (initialize, prefetch, sync_turn, …) |
| `manager.py` | Provider registration and lifecycle fan-out |
| `skill_summary.py` | Default provider — summarizes sessions into generated skills |

### Cron & Scheduler (`dojoagents/cron/`)

| File | Role |
|------|------|
| `jobs.py` | `JobStore` — YAML job definitions, run output persistence |
| `scheduler.py` | APScheduler integration |

Jobs specify schedule, agent prompt, quant context, and optional gateway delivery target.

### Gateway (`dojoagents/gateway/`)

Normalizes external chat platforms into `ChatRequest` and delivers `AgentResponse` back.

| Adapter | Module |
|---------|--------|
| Slack | `adapters/slack.py` |
| Telegram | `adapters/telegram.py` |
| Discord | `adapters/discord.py` |
| Feishu | `adapters/feishu.py` |
| WeCom | `adapters/wecom.py` |
| WeChat | `adapters/wechat.py` |

Also includes `server.py` (FastAPI gateway app), `runner.py` (stateful runner), `pairing.py` (DM pairing store), and `registry.py`.

Gateway endpoints:

```text
GET  /api/health
GET  /api/platforms
POST /api/webhook/{platform}
POST /api/send/{platform}/{target}
```

### Plugins (`dojoagents/plugins/`)

Discovers plugins from `dojoagents/plugins/built_in/` and `~/.dojo/plugins`. Supports:

- Native `plugin.yaml` manifests
- Claude-format `.claude-plugin/plugin.json`
- Skills, agents, hooks, MCP/LSP configs, shell PATH injection

See [`docs/plugins.md`](docs/plugins.md).

### Dojo Extensions (`dojoagents/dojo_extensions/`)

First-class domain plugins for the Dojo ecosystem — not generic tools, but finance-aware capabilities:

| Method | Returns |
|--------|---------|
| `health()` | Extension health status |
| `tool_specs()` | Tools registered into the agent |
| `dashboard_cards()` | Dashboard card definitions |
| `prompt_context(quant_context)` | Prompt injection text |

Built-in: **`dojo_research`** — research artifact facade (see `research.py`).

### Multi-Agent & Planning

Optional subsystems activated via config:

| Package | Purpose |
|---------|---------|
| `multi_agent/` | `AgentPool`, delegation tool, `Orchestrator`, automation dispatcher, trigger hooks |
| `planning/` | `PlanStateStore`, `PlanExecutionEngine`, plan tools, activation hooks, auto plan manager |

See [`docs/multi_agent_plan_architecture.md`](docs/multi_agent_plan_architecture.md).

### Quant Context (`dojoagents/quant/`)

Typed market boundaries injected into agent prompts and job definitions:

```python
QuantContext(
    market="stock",       # "stock" | "crypto"
    symbols=["AAPL"],
    timeframe="1d",
    currency="USD",
    data_freshness="latest_available",
)
```

Modules: `context.py`, `workflow.py`, `risk.py`.

### Dashboard Backend (`dojoagents/dashboard/`)

FastAPI application factory: **`create_app(runtime)`**.

| Directory | Role |
|-----------|------|
| `server.py` | App factory, `/api/chat`, `/api/chat/runs/*`, config, jobs, static files |
| `routers/` | Domain REST routes under `/api/v1` |
| `services/` | Financial data services, stores, gateway wrappers, refresh jobs |
| `schemas/` | Pydantic request/response models |
| `deps.py` | FastAPI dependency accessors |
| `agent_runs.py` | Background run manager for resumable agent sessions |
| `sse.py` | OpenAI-compatible SSE chunk encoder with `dojo.v2` events |
| `tools/` | Dashboard-specific agent tool adapters (portfolio, domain) |
| `static/` | Packaged static assets and canvas iframe template |

**Domain routers** (`/api/v1/...`):

| Router | Domain |
|--------|--------|
| `dojo_folio.py` | Portfolio analytics |
| `dojo_mesh.py` | Multi-market overview |
| `dojo_sphere.py` | Sector scope metrics and performance |
| `dojo_core.py` | Single-stock quotes and fundamentals |
| `ticker.py` | Ticker quote and search |
| `market.py` / `markets.py` | Market-level stats |
| `sector.py` / `sectors.py` | Sector constituents and scope |
| `portfolio.py` | Portfolio CRUD and holdings |
| `utility.py` | Health and misc utilities |

Local financial data is cached under `dashboard.financial.dashboard_data_root` (default `~/.dojo/dashboard-data`).

### Dashboard Frontend (`dojoagents/dashboard/web/`)

React 19 + TypeScript SPA built with Vite.

| Directory | Role |
|-----------|------|
| `src/views/` | `FolioView`, `MarketView`, `SectorView`, `EntityView` (routes: `folio`, `market`, `sector`, `entity`) |
| `src/components/Market/` | Market view components |
| `src/components/Sector/` | Sector discovery components |
| `src/components/Entity/` | Single-stock analysis components |
| `src/components/Folio/` | Portfolio components |
| `src/navigation/appTab.ts` | Hash routing — `#/market`, `#/sector`, `#/entity`, `#/folio` |
| `src/types/` | `market.ts`, `sector.ts`, `entity.ts`, `folio.ts` |
| `src/api/` | Typed HTTP clients for backend routes |
| `src/components/DojoAgent/` | Agent panel, tool activity, viz blocks, thinking UI |
| `src/agent/` | Run context, SSE client, session storage |
| `src/hooks/` | Data-fetching and layout hooks per view |
| `src/utils/` | Shared calculations (metrics, charts, filters) |
| `src/i18n/` | English / Chinese locale messages |
| `src/navigation/` | Tab routing, cross-view context (ticker, sector) |

Frontend development with HMR:

```bash
# Terminal 1 — backend
dojoagents dashboard --host 127.0.0.1 --port 8765

# Terminal 2 — Vite dev server (proxies /api to backend)
cd dojoagents/dashboard/web
npm run dev
# open http://localhost:5173
```

UI style reference: [`docs/frontend-style-guide.md`](docs/frontend-style-guide.md)

### CLI (`dojoagents/cli/`)

| File | Role |
|------|------|
| `main.py` | Argument parser and command dispatch |
| `gateway_setup.py` | Interactive gateway adapter wizard |
| `model_setup.py` | Interactive LLM provider wizard |
| `mcp_serve.py` | MCP server entry |
| `precompute_sector.py` | Sector precompute batch job |

---

## API Overview

### Dashboard core routes

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/health` | Health check |
| `GET` | `/api/config` | Redacted configuration |
| `PUT` | `/api/config` | Partial config merge and save |
| `GET` | `/api/jobs` | Scheduled jobs |
| `GET` | `/api/extensions` | Extension health |
| `POST` | `/api/chat` | OpenAI-compatible chat (stream or JSON) |
| `POST` | `/api/chat/runs` | Create background agent run |
| `GET` | `/api/chat/runs/{run_id}/events` | SSE event stream with cursor |
| `POST` | `/api/chat/runs/{run_id}/cancel` | Cancel a run |
| `GET` | `/` | React SPA |

Domain financial APIs are mounted at **`/api/v1/`** (ticker, sector, portfolio, dojo-folio, dojo-mesh, dojo-sphere, dojo-core, …).

Chat protocol extensions: set `metadata.event_format = "dojo.v2"` for typed agent events. See [`docs/dojo-chat-v2-protocol.md`](docs/dojo-chat-v2-protocol.md).

---

## Development

### Repository layout

```text
.
├── dojoagents/           # Python package
│   ├── agent/            # Agent loop, providers, harnesses
│   ├── cli/              # Console entry point
│   ├── config/           # ConfigStore and typed schema
│   ├── cron/             # Scheduler and job store
│   ├── dashboard/        # FastAPI server + React web app
│   ├── dojo_extensions/  # Domain extension protocol
│   ├── gateway/          # Chat platform adapters
│   ├── memory/           # Memory providers
│   ├── multi_agent/      # Agent pool and delegation
│   ├── planning/         # Plan engine
│   ├── plugins/          # Plugin discovery and hooks
│   ├── quant/            # QuantContext and workflow types
│   ├── skills/           # Skill manager and built-in skills
│   └── tools/            # Tool registry, executor, sandbox
├── docs/                 # Architecture and design documents
├── tests/                # Pytest suite
├── pyproject.toml        # Package metadata and dependencies
├── uv.lock               # Python lockfile
└── AGENTS.md             # Agent coding guidelines for contributors
```

### Agent contributor guidelines

See [`AGENTS.md`](AGENTS.md) for mandatory patterns: unified `ConfigStore`, unified `LOGGER`, storage primitives, and extension paths.

Temporary scripts belong under **`.agents/scripts/`**.

---

## Testing

Run the full suite:

```bash
uv run --extra dev python -m pytest -q
```

Targeted subsets:

```bash
uv run --extra dev python -m pytest tests/dashboard/routers -q
uv run --extra dev python -m pytest tests/test_dashboard_config_update.py -q
uv run --extra dev python -m pytest tests/test_tool_registry_clone.py -q
```

Frontend type-check and production build:

```bash
cd dojoagents/dashboard/web
npm run build
```

Smoke checks:

```bash
uv run --extra dev dojoagents --help
uv run --extra dev dojoagents dashboard --host 127.0.0.1 --port 8765
```

---

## Building a Wheel

From the repository root (requires Node.js for the embedded frontend build):

```bash
uv build
# or: python -m pip install build && python -m build
```

The build hook automatically:

1. Runs `npm install && npm run build` under `dojoagents/dashboard/web`
2. Removes `node_modules` after a successful frontend build
3. Bundles `web/dist/` into the wheel

Output:

```text
dist/dojoagents-0.0.1-py3-none-any.whl
dist/dojoagents-0.0.1.tar.gz
```

Install:

```bash
uv pip install dist/dojoagents-0.0.1-py3-none-any.whl
```

---

## Documentation Index

| Document | Topic |
|----------|-------|
| [`docs/architecture.md`](docs/architecture.md) | System architecture and design goals |
| [`docs/usage.md`](docs/usage.md) | CLI, gateway setup, model setup, dev workflow |
| [`docs/dashboard.md`](docs/dashboard.md) | Dashboard protocol, canvas, SSE, API design |
| [`docs/dojo-chat-v2-protocol.md`](docs/dojo-chat-v2-protocol.md) | `dojo.v2` typed event schema |
| [`docs/plugins.md`](docs/plugins.md) | Plugin system and Claude compatibility |
| [`docs/dojo_sdk_integration.md`](docs/dojo_sdk_integration.md) | Dojo SDK tool registration |
| [`docs/multi_agent_plan_architecture.md`](docs/multi_agent_plan_architecture.md) | Multi-agent and planning design |
| [`docs/event_driven_architecture.md`](docs/event_driven_architecture.md) | Event bus and automation |
| [`docs/session_context_memory_design.md`](docs/session_context_memory_design.md) | Session memory design |
| [`docs/backtest.md`](docs/backtest.md) | Backtest integration notes |
| [`docs/precompute_sector_daily.md`](docs/precompute_sector_daily.md) | Sector precompute pipeline |
| [`docs/frontend-style-guide.md`](docs/frontend-style-guide.md) | Dashboard UI conventions |
| [`docs/performance_profiler.md`](docs/performance_profiler.md) | PyInstrument profiling middleware |
| [`AGENTS.md`](AGENTS.md) | Contributor agent instructions |

---

## License

DojoAgents is licensed under the [Apache License 2.0](LICENSE).
