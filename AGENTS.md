# Repository Agent Instructions

## Non-Negotiable Local Rules

- `git` commands are FORBIDDEN in this repository. Do NOT run `git status`, `git diff`, `git show`, `git checkout`, `git reset`, `git commit`, or any other `git` subcommand.
- Temporary scripts MUST be placed under `.agents/scripts/`.
- New production business code MUST use AnyIO. Outside the explicit compatibility allowlist (see §3 "Unified ASYNC RUNTIME"), adding an `asyncio` import, a bare background task, or an unbounded async queue is FORBIDDEN.
- New third-party dependencies MUST NOT be introduced unless the primary lockfile is updated in the same change:
  - Python: `pyproject.toml` and `uv.lock`
  - Frontend: `dojoagents/dashboard/web/package.json` and `dojoagents/dashboard/web/package-lock.json`

## 1. High-Level Mental Map

### Core Purpose

DojoAgents is a quantitative finance agent runtime. It wires an LLM-driven agent loop, sandboxed tools, skills, memory, scheduled jobs, chat gateways, plugins, and a FastAPI/React dashboard for financial analysis workflows.

### Primary Tech Stack

- Python package: `dojoagents` version `0.2.8`
- Python runtime: `>=3.11`
- Async runtime: **AnyIO `>=4.8,<5`** (the only sanctioned concurrency layer; see §3)
- Backend/API: FastAPI `>=0.115.2,<0.116`, uvicorn `>=0.31.1,<0.36`
- LLM/API clients: OpenAI SDK `>=1.20.0,<2`, httpx `>=0.27.0,<1`
- Config/storage/data: PyYAML `>=6.0.1,<7`, pandas `>=2.2.0,<3`, pyarrow `>=14.0.0`, portalocker, APScheduler `>=3.10.0,<4`
- Agent/tooling: `mcp>=1.26.0,<2`, `strands-agents`, `strands-agents-tools`, `dojosdk>=0.1.29`
- Frontend: React `^19.2.6`, React DOM `^19.2.6`, TypeScript `~5.8.3`, Vite `^8.0.12`
- Test stack: pytest `>=8.4.2`, pytest-asyncio `>=1.2.0` (legacy `@pytest.mark.asyncio` tests), AnyIO via `@pytest.mark.anyio` with the shared `anyio_backend` fixture pinned to `"asyncio"`


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
├── docs/                             # Documentation governance and MkDocs source.
│   ├── README.md                     # Documentation taxonomy and maintenance rules.
│   └── site/                         # Only publishable documentation source.
│       ├── assets/                   # Shared images and GIFs.
│       ├── en/                       # English site: guides, architecture, design, reference, plans.
│       └── zh/                       # Chinese site with matching relative paths.
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

### Documentation Classification (MANDATORY)

- All publishable Markdown belongs under `docs/site/{zh,en}/`; do not add standalone design or plan documents directly under `docs/`.
- Use `architecture/` for system-wide component relationships and flows, `design/` for current subsystem designs and contracts, `plans/` for proposed or historical implementation work, `reference/` for stable interfaces, and `development/` for contributor procedures.
- Store shared documentation media under `docs/site/assets/images/` or `docs/site/assets/gifs/`. Do not make site pages depend on assets in frontend source directories.
- Keep Chinese and English pages at matching relative paths whenever practical, and update `mkdocs.yml` navigation when a published page is added or moved.
- When a plan is implemented, move durable conclusions into the authoritative architecture, design, reference, or development page and archive or remove obsolete plan text.

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

### Unified ASYNC RUNTIME (MANDATORY)

**New production business code MUST use AnyIO.** Outside the explicit compatibility allowlist (§9 of the async runtime design) it is FORBIDDEN to add an `asyncio` import, a bare background task, or an unbounded async queue.

Authoritative design: `docs/site/zh/design/async-runtime.md` and `docs/site/en/design/async-runtime.md`.

- Async primitives: `dojoagents/utils/async_runtime.py`
  - `run_sync_bounded()` — the only sanctioned way to run blocking work (bounded thread limiter, `FILE_IO=16` / `SDK_IO=8` / `CPU=4`)
  - `gather_ordered()` — order-preserving concurrency that never leaks `ExceptionGroup`
  - `operation_timeout()` / `is_cancelled_exception()`
- Cross-thread bridge: `dojoagents/utils/blocking_portal.py::ThreadedBlockingPortal` — the only supported channel from a sync thread into an event loop. One portal per component, explicit idempotent `start()` / `shutdown()`; never one portal per request, never a hand-rolled `new_event_loop()` + `run_forever` thread.
- Process adapter: `dojoagents/tools/processes.py` — all subprocess work goes through `open_process()` / `run_process()` / `terminate_then_kill()`.
- Compatibility allowlist (the only files allowed to `import asyncio`):
  - `dojoagents/tools/af_unix_asyncio_compat.py`
  - `dojoagents/utils/detached_tasks.py`
  - Enforced by `tests/test_asyncio_boundaries.py` (`PERMANENT_ASYNCIO_ALLOWLIST`, empty `TEMPORARY_ASYNCIO_ALLOWLIST`) and `.agents/scripts/audit_asyncio_usage.py` (`PRESERVE_ALLOWLIST`). A new entry must satisfy all six retention rules in §9 of the design doc.
- Reference matrix: regenerate with `uv run --extra dev python .agents/scripts/audit_asyncio_usage.py`. After every migration batch the reference count must only decrease — an unexpected increase means a new `asyncio` dependency was introduced.

Future agents MUST NOT call `asyncio.*` directly, MUST NOT use bare `anyio.to_thread.run_sync()` (use `run_sync_bounded()`), MUST NOT let an `ExceptionGroup` escape a public API, and MUST NOT swallow cancellation with `except Exception`.

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

### K-line Data Ownership (MANDATORY)

- DojoSDK is the single owner of offline K-line files, snapshot revisions, lazy filtering, limits, and price adjustment.
- `dojoagents/dashboard/services/dojo_data_gateway.py` MUST read K-line data through DojoSDK's bounded `get_klines()` API and retain the returned snapshot metadata. It MUST NOT build a full-market DataFrame or symbol/time index.
- `dojoagents/dashboard/services/kline_store.py` MAY keep a bounded cache of assembled API responses, but MUST NOT preload, copy, persist, or rebuild the complete K-line dataset.
- Do NOT add a DojoAgents-owned K-line parquet/JSONL working set, `raw_by_symbol` full-data mirror, or startup full-data preload. These duplicate DojoSDK state and significantly increase startup I/O, memory, and serialization time.
- Cross-process persistence and dataset refresh belong in DojoSDK. If its query surface is insufficient, extend DojoSDK instead of introducing another K-line storage layer in DojoAgents.

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

This pattern from `dojoagents/tools/executor.py` is the model for bounded async execution, unified logging, structured error propagation, and cancellation that is never swallowed:

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
    started_at = time.perf_counter()
    try:
        self.sandbox.check_tool(call.name)
        # Hard deadline: cancels only this scope, converts to TimeoutError.
        with anyio.fail_after(self.sandbox.timeout_seconds):
            raw = await spec.handler(dict(call.arguments))
        latency_ms = int((time.perf_counter() - started_at) * 1000)
        return self._coerce_result(call, raw, session_id=session_id, latency_ms=latency_ms)
    except TimeoutError:
        timeout_seconds = self.sandbox.timeout_seconds
        LOGGER.warning(
            "Tool '%s' timed out after %ss (call_id: %s)", call.name, timeout_seconds, call.id
        )
        return ToolResult(
            call_id=call.id,
            name=call.name,
            ok=False,
            error=f"Tool '{call.name}' timed out after {timeout_seconds:g} seconds",
            latency_ms=int((time.perf_counter() - started_at) * 1000),
        )
    except BaseExceptionGroup as exc:
        # A public API never leaks an ExceptionGroup: re-raise cancellation,
        # flatten everything else into one ToolResult.
        cancelled, remainder = exc.split(anyio.get_cancelled_exc_class())
        if cancelled is not None:
            raise cancelled
        LOGGER.exception("Grouped error executing tool '%s' (call_id: %s)", call.name, call.id)
        return ToolResult(
            call_id=call.id,
            name=call.name,
            ok=False,
            error=str(remainder or exc),
            latency_ms=int((time.perf_counter() - started_at) * 1000),
        )
    except Exception as exc:
        LOGGER.exception(f"Error executing tool '{call.name}' (call_id: {call.id})")
        return ToolResult(call_id=call.id, name=call.name, ok=False, error=str(exc))
    finally:
        active_session_id.reset(token)
```

Note what is deliberately absent: `asyncio.wait_for`, a hand-rolled event loop, and an `except Exception` that would silently absorb cancellation.

## 5. Architectural Guardrails & Anti-Patterns (Must NOT)

- MUST NOT use `git` commands.
- MUST NOT place temporary scripts outside `.agents/scripts/`.
- MUST NOT add an `asyncio` import outside the compatibility allowlist (§3 Unified ASYNC RUNTIME).
- MUST NOT start a bare background task (`asyncio.create_task()`, orphaned coroutines). Every task needs a TaskGroup owner whose lifetime encloses it.
- MUST NOT create an unbounded async queue or an unbounded `anyio.create_memory_object_stream()`. Buffer capacity MUST be an explicit finite number.
- MUST NOT hand-roll an event loop thread (`new_event_loop()` + `run_forever`) or use `run_coroutine_threadsafe()` / `wrap_future()`. Use `ThreadedBlockingPortal`.
- MUST NOT create a `ThreadedBlockingPortal` per request; a component owns its portal for its whole lifetime.
- MUST NOT call `asyncio.*` APIs directly in business code, including `asyncio.wait_for`, `asyncio.gather`, `asyncio.Lock`, `asyncio.sleep`, and `asyncio.CancelledError`.
- MUST NOT use bare `anyio.to_thread.run_sync()` for blocking work; use `run_sync_bounded()` so the work is charged to the correct bounded limiter.
- MUST NOT let an `ExceptionGroup` escape a public API (tool result, HTTP response, gateway callback). Split it and re-raise cancellation.
- MUST NOT swallow cancellation in an `except Exception` block. Detect it with `anyio.get_cancelled_exc_class()` and re-raise, or wrap the bounded cleanup in `anyio.CancelScope(shield=True)`.
- MUST NOT wrap an `__aexit__` that closes a cancel scope in `shield=True` or `move_on_after`; bound the teardown with the closing function's own timeout instead.
- MUST NOT launch subprocesses outside `dojoagents/tools/processes.py`, and MUST NOT leave a child unreaped on timeout or cancellation.
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

Async runtime gates — run these whenever async code changes:

```bash
uv run --extra dev python -m pytest tests/test_asyncio_boundaries.py -q
uv run --extra dev python .agents/scripts/audit_asyncio_usage.py
```

`tests/test_asyncio_boundaries.py` fails if a production file imports `asyncio` without being registered, if a registered file is stale, or if a memory object stream has no finite `max_buffer_size`. The audit script rewrites `.agents/asyncio-migration-matrix.{json,csv,md}`; after a migration batch the `target_stage` counts must only decrease.

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
