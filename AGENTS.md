# Repository Agent Instructions

## Non-Negotiable Local Rules

- `git` commands are FORBIDDEN in this repository. Do NOT run `git status`, `git diff`, `git show`, `git checkout`, `git reset`, `git commit`, or any other `git` subcommand.
- Temporary scripts MUST be placed under `.agents/scripts/`.
- New third-party dependencies MUST NOT be introduced unless the primary lockfile is updated in the same change:
  - Python: `pyproject.toml` and `uv.lock`
  - Frontend: `dojoagents/dashboard/web/package.json` and `dojoagents/dashboard/web/package-lock.json`

## 1. High-Level Mental Map

### Core Purpose

DojoAgents is a quantitative finance agent runtime. It wires an LLM-driven agent loop, sandboxed tools, skills, memory, scheduled jobs, chat gateways, plugins, and a FastAPI/React dashboard for financial analysis workflows.

### Primary Tech Stack

- Python package: `dojoagents` version `0.0.1`
- Python runtime: `>=3.11`
- Backend/API: FastAPI `>=0.110.0,<0.112`, uvicorn `>=0.31.1,<0.33`
- LLM/API clients: OpenAI SDK `>=1.20.0,<2`, httpx `>=0.27.0,<1`
- Config/storage/data: PyYAML `>=6.0.1,<7`, pandas `>=2.2.0,<3`, pyarrow `>=14.0.0`, portalocker, APScheduler `>=3.10.0,<4`
- Agent/tooling: `mcp>=1.26.0,<2`, `strands-agents`, `strands-agents-tools`, `dojosdk==0.1.5`
- Frontend: React `^19.2.6`, React DOM `^19.2.6`, TypeScript `~5.8.3`, Vite `^8.0.12`
- Test stack: pytest `>=8.4.2`, pytest-asyncio `>=1.2.0`

## 2. Repository Directory Structure (Global Overview)

```text
.
├── AGENTS.md                         # This file: mandatory guidance for future agents.
├── README.md                         # User-facing setup, CLI, dashboard, and gateway overview.
├── VERSION                           # Package version marker.
├── pyproject.toml                    # Python package metadata, dependencies, console script.
├── requirements.txt                  # Runtime dependency mirror.
├── uv.lock                           # Primary Python lockfile.
├── docker/
│   └── Dockerfile                    # Container packaging.
├── docs/                             # Architecture, dashboard, protocol, plugin, and planning docs.
├── tests/                            # Pytest suite; mirrors agent, dashboard, gateway, plugin, tool surfaces.
├── .agents/
│   └── scripts/                      # REQUIRED location for temporary scripts.
└── dojoagents/
    ├── __init__.py                   # Package root.
    ├── logging.py                    # Unified logger configuration and LOGGER singleton.
    ├── agent/                        # Agent loop, runtime composition, providers, events, guardrails, harnesses.
    │   ├── runtime.py                # Main object graph wiring from ConfigStore.
    │   ├── loop.py                   # AgentLoop orchestration and streaming/tool flow.
    │   └── models.py                 # ChatRequest, ToolCall, ToolResult, LLMResult contracts.
    ├── cli/                          # `dojoagents` console entry point and interactive config/gateway setup.
    ├── config/                       # Central typed configuration system.
    │   ├── loader.py                 # ConfigStore, env expansion, deep merge, redaction, save.
    │   └── models.py                 # Frozen dataclass config schema.
    ├── cron/                         # Job storage and scheduler integration.
    ├── dashboard/                    # FastAPI server, routers, services, schemas, SSE, static assets, React app.
    │   ├── server.py                 # Dashboard app factory, lifespan, config/chat/jobs endpoints.
    │   ├── deps.py                   # FastAPI dependency accessors for initialized services.
    │   ├── routers/                  # API route modules. Add new dashboard routes here.
    │   ├── schemas/                  # Pydantic response/request models for dashboard APIs.
    │   ├── services/                 # Financial/domain services, stores, gateway wrappers, cache logic.
    │   ├── tools/                    # Dashboard-specific agent tool adapters.
    │   ├── static/                   # Packaged static HTML/assets.
    │   └── web/                      # React/Vite frontend source and frontend lockfile.
    ├── dojo_extensions/              # DojoExtension protocol and registry for first-class extensions.
    ├── gateway/                      # Chat gateway server, runner, state, pairing, platform adapters.
    │   └── adapters/                 # Slack/Telegram/WeChat/Feishu/etc adapters; subclass BaseGatewayAdapter.
    ├── memory/                       # Memory provider protocol, manager, local/skill-summary providers.
    ├── multi_agent/                  # Agent pool, delegation tools, orchestrator, triggers, automation.
    ├── planning/                     # Plan models, state store, execution engine, tools, triggers.
    ├── plugins/                      # Plugin discovery, manifests, hooks, plugin tool registration.
    │   └── built_in/                 # Built-in plugin examples and guardrails.
    ├── quant/                        # Quant context, risk, workflow primitives.
    ├── skills/                       # Skill manager/cache/loader and built-in procedural skills.
    ├── tools/                        # ToolSpec registry, executor, sandbox, terminal/code/MCP/web/skill tools.
    │   └── environments/             # Local/Docker/SSH/Modal execution environment adapters.
    └── utils/                        # Shared utility modules such as event bus and fuzzy matching.
```

## 3. Core Infrastructure & Utilities (CRITICAL: Do NOT Reinvent)

### Unified CONFIG (MANDATORY)

- Central config store: `dojoagents/config/loader.py::ConfigStore`
- Typed schema: `dojoagents/config/models.py::AgentsConfig` and nested frozen dataclasses
- Default config path: `~/.dojo/agents.yaml`
- Runtime entry point: `dojoagents/agent/runtime.py::Runtime.from_config_store(ConfigStore(...))`
- Dashboard config API: `dojoagents/dashboard/server.py` uses `runtime.config_store.redacted()`, `raw()`, and `save_raw()`

Future agents MUST use `ConfigStore.snapshot()` for typed config reads. Future agents MUST use `ConfigStore.raw()` plus `_deep_merge()` plus `ConfigStore.save_raw()` for user config updates. Creating a separate YAML parser, environment expansion layer, config singleton, or unrelated config path is FORBIDDEN.

### Unified LOGGER (MANDATORY)

- Central logger module: `dojoagents/logging.py`
- Root logger singleton: `dojoagents.logging.LOGGER`
- Named logger factory: `dojoagents.logging.get_logger(name)`
- Logger configuration: `dojoagents.logging.configure_logging(config)`
- Log config model: `dojoagents.config.models.LoggingConfig`

Future agents MUST import `LOGGER` or `get_logger()` from `dojoagents.logging` for new Python logging. Raw `print()` for product output, ad hoc `logging.basicConfig()`, new root logger configuration, and unconfigured standalone loggers are FORBIDDEN in new code. CLI output should still go through the configured logger unless a test explicitly requires stdout capture.

### Database/Storage & Errors

- SQLite session/gateway state: `dojoagents/gateway/state.py`
- Gateway state runner integration: `dojoagents/gateway/runner.py`
- Dashboard service registry: `dojoagents/dashboard/services/financial_registry.py::FinancialDomainRegistry`
- Legacy/global dashboard store manager: `dojoagents/dashboard/store_manager.py::stores`
- FastAPI service accessors: `dojoagents/dashboard/deps.py`
- Atomic JSON/JSONL storage and store errors: `dojoagents/dashboard/services/file_store_base.py`
  - `AtomicJsonStore`
  - `AtomicJsonlStore`
  - `FileStoreError`
  - `CorruptStoreError`
  - `SchemaVersionError`
  - `InvalidStoreKeyError`
- Dojo SDK/domain gateway error family: `dojoagents/dashboard/services/dojo_data_gateway.py`
  - `GatewayError`
  - `GatewayBadResponseError`
  - `GatewayTimeoutError`
  - `GatewayUnavailableError`
  - `GatewayResult`
- Tool error boundary: `dojoagents/tools/executor.py::ToolExecutor.execute_one()` logs with `LOGGER.exception()` and returns `ToolResult(ok=False, error=str(exc))`.
- Dashboard route error pattern: raise `fastapi.HTTPException` for expected HTTP failures, or return `JSONResponse(status_code=..., content={"error": ...})` where existing handlers do so.

Future agents MUST reuse these storage and error primitives. Do NOT write direct unsafe path joins for user-controlled store keys. Do NOT persist JSON with non-atomic plain writes when `file_store_base.py` applies.

## 4. Extension Paths & Golden Patterns

### Standard Extension Routes

- New agent tools:
  - Define a `dojoagents.tools.registry.ToolSpec`.
  - Register it in `dojoagents/agent/runtime.py::Runtime.from_config_store()` or expose it through an extension/plugin registry.
  - Tool handlers MUST be async and return `dict[str, Any]` or a string compatible with `ToolExecutor._coerce_result()`.
- New Dojo first-class extension:
  - Implement `dojoagents/dojo_extensions/base.py::DojoExtension`.
  - Register it in `dojoagents/agent/runtime.py` based on `config.dojo_extensions.enabled`.
- New plugin:
  - Built-in plugins live under `dojoagents/plugins/built_in/<plugin_name>/`.
  - User plugins are discovered from `~/.dojo/plugins`.
  - Use `plugin.yaml`, `.claude-plugin/plugin.json`, `hooks.json`, `.mcp.json`, or `__init__.py` according to `dojoagents/plugins/registry.py`.
  - Hooks MUST use names from `VALID_HOOKS` in `dojoagents/plugins/registry.py`.
- New dashboard API:
  - Add routes under `dojoagents/dashboard/routers/`.
  - Add request/response schemas under `dojoagents/dashboard/schemas/`.
  - Put business logic in `dojoagents/dashboard/services/`.
  - Access stores/services through `dojoagents/dashboard/deps.py`.
  - Include the router in `dojoagents/dashboard/server.py` under `/api/v1`.
- New dashboard frontend feature:
  - API calls go under `dojoagents/dashboard/web/src/api/`.
  - Types go under `dojoagents/dashboard/web/src/types/`.
  - Views go under `dojoagents/dashboard/web/src/views/`.
  - Reusable controls go under `dojoagents/dashboard/web/src/components/` or `components/ui/`.
  - Shared calculations belong in `dojoagents/dashboard/web/src/utils/`.
- New gateway adapter:
  - Add `dojoagents/gateway/adapters/<platform>.py`.
  - Subclass or follow `dojoagents/gateway/adapters/base.py::BaseGatewayAdapter`.
  - Return `GatewayEvent` from `normalize_message()` and `GatewaySendResult` from sending paths.
  - Register the adapter through `dojoagents/gateway/registry.py`.
- New config fields:
  - Add frozen dataclass fields in `dojoagents/config/models.py`.
  - Parse them in `dojoagents/config/loader.py::_to_config()`.
  - Add focused tests under `tests/`.

### The Golden Code Snippet

This pattern from `dojoagents/tools/executor.py` is the model for bounded async execution, unified logging, and structured error propagation:

```python
async def execute_one(self, call: ToolCall, *, session_id: str = "") -> ToolResult:
    spec = self.registry.get(call.name)
    if spec is None:
        LOGGER.error(f"Tool '{call.name}' is not registered")
        return ToolResult(
            call_id=call.id,
            name=call.name,
            ok=False,
            error=f"Tool '{call.name}' is not registered",
        )
    from dojoagents.tools.process_registry import active_session_id

    token = active_session_id.set(session_id)
    try:
        self.sandbox.check_tool(call.name)
        started_at = time.perf_counter()
        raw = await asyncio.wait_for(
            spec.handler(dict(call.arguments)),
            timeout=self.sandbox.timeout_seconds,
        )
        latency_ms = int((time.perf_counter() - started_at) * 1000)
        return self._coerce_result(call, raw, session_id=session_id, latency_ms=latency_ms)
    except Exception as exc:
        LOGGER.exception(f"Error executing tool '{call.name}' (call_id: {call.id})")
        return ToolResult(call_id=call.id, name=call.name, ok=False, error=str(exc))
    finally:
        active_session_id.reset(token)
```

## 5. Architectural Guardrails & Anti-Patterns (Must NOT)

- MUST NOT use `git` commands.
- MUST NOT place temporary scripts outside `.agents/scripts/`.
- MUST NOT block the async runtime thread. Use async I/O, existing async clients, background tasks, or bounded executors for blocking work.
- MUST NOT create new config parsing logic. Use `ConfigStore`.
- MUST NOT create new logger configuration. Use `dojoagents.logging`.
- MUST NOT bypass `SandboxPolicy` for terminal/code/tool execution.
- MUST NOT register tools outside `ToolRegistry`/`ToolSpec`.
- MUST NOT return arbitrary tool result shapes. Let `ToolExecutor` normalize handler output.
- MUST NOT add dashboard route logic that directly reaches into global stores when a `deps.py` accessor exists.
- MUST NOT introduce new storage formats for dashboard JSON/JSONL data when `AtomicJsonStore` or `AtomicJsonlStore` fits.
- MUST NOT silently swallow broad exceptions. Log with `LOGGER.exception()` at boundaries or convert to typed errors/HTTP errors.
- MUST NOT leak API keys or provider secrets. Use `ConfigStore.redacted()` for dashboard/API exposure.
- MUST NOT add dependencies without updating the matching lockfile.
- MUST NOT edit generated/cache folders such as `.venv/`, `.pytest_cache/`, `__pycache__/`, `dojoagents.egg-info/`, or dashboard TypeScript build info except as an explicit cleanup task.

## 6. Verification & Validation Workflow

Run the smallest relevant subset first, then the broader commands before declaring success.

### Python

```bash
uv run --extra dev python -m pytest -q
```

For targeted validation while iterating:

```bash
uv run --extra dev python -m pytest tests/test_config_multi_agent_plan.py -q
uv run --extra dev python -m pytest tests/dashboard/routers -q
uv run --extra dev python -m pytest tests/test_tool_registry_clone.py tests/test_terminal_tool_integrated.py -q
```

### Frontend

```bash
cd dojoagents/dashboard/web
npm run build
```

### Runtime Smoke Checks

```bash
uv run --extra dev dojoagents --help
uv run --extra dev dojoagents dashboard --host 127.0.0.1 --port 8765
```

Use the dashboard smoke command only when a local server is appropriate for the task. Stop the server before ending the work session.
