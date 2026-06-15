# DojoAgents Prototype Design

This document is a code-oriented prototype for the architecture in
`docs/architecture.md`. It is not an implementation. It shows the intended API
shape, module boundaries, and demo flows that the first implementation should
follow.

## 1. Runtime Demo

Target developer experience:

```bash
dojoagents chat --profile default --market crypto --symbols BTC-USD,ETH-USD
dojoagents dashboard --host 127.0.0.1 --port 8765
dojoagents gateway --config ~/.dojo/agents.yaml
dojoagents scheduler --run
dojoagents jobs add daily-btc-brief --schedule "0 8 * * 1-5"
```

Minimal Python usage:

```python
from dojoagents.agent.runtime import Runtime
from dojoagents.agent.models import ChatRequest
from dojoagents.quant.context import QuantContext

runtime = Runtime.from_default_config()

response = await runtime.agent.run(
    ChatRequest(
        user_id="local",
        session_id="demo-session",
        message="Summarize the current BTC and ETH market structure.",
        quant=QuantContext(
            market="crypto",
            symbols=["BTC-USD", "ETH-USD"],
            timeframe="1d",
        ),
    )
)

print(response.content)
```

## 2. Core Data Models

```python
from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass(frozen=True)
class QuantContext:
    market: Literal["stock", "crypto"]
    symbols: list[str]
    timeframe: str
    currency: str = "USD"
    data_freshness: str = "latest_available"


@dataclass(frozen=True)
class ChatRequest:
    message: str
    user_id: str
    session_id: str
    channel: str = "cli"
    quant: QuantContext | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class AgentResponse:
    content: str
    session_id: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    artifacts: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
```

## 3. AgentLoop Prototype

```python
class AgentLoop:
    def __init__(
        self,
        *,
        llm_provider: LLMProvider,
        tool_executor: ToolExecutor,
        skill_manager: SkillManager,
        memory_manager: MemoryManager,
        extension_registry: DojoExtensionRegistry,
        config: AgentConfig,
    ) -> None:
        self.llm_provider = llm_provider
        self.tool_executor = tool_executor
        self.skill_manager = skill_manager
        self.memory_manager = memory_manager
        self.extension_registry = extension_registry
        self.config = config

    async def run(self, request: ChatRequest) -> AgentResponse:
        messages = await self._build_messages(request)
        tool_specs = self._collect_tool_specs(request)

        for iteration in range(self.config.max_iterations):
            llm_result = await self.llm_provider.chat(
                messages,
                tool_specs,
                model=self.config.model,
                metadata={"session_id": request.session_id},
            )

            if not llm_result.tool_calls:
                await self.memory_manager.sync_turn(
                    request.message,
                    llm_result.content,
                    session_id=request.session_id,
                )
                return AgentResponse(
                    content=llm_result.content,
                    session_id=request.session_id,
                    metadata={"iterations": iteration + 1},
                )

            tool_results = await self.tool_executor.execute_many(
                llm_result.tool_calls,
                session_id=request.session_id,
            )
            messages.extend(tool_results.to_messages())

        return AgentResponse(
            content="Agent stopped after reaching the iteration limit.",
            session_id=request.session_id,
            metadata={"stopped": "iteration_limit"},
        )
```

Design notes:

- The loop has no direct dependency on Slack, Telegram, dashboard, scheduler, or
  concrete Dojo financial services.
- Quant context enters as request context and becomes prompt context plus tool
  filtering.
- Memory prefetch and skill prompt blocks should be injected before the LLM
  call, not exposed to Gateway.

## 4. LLM Provider Prototype

```python
class LLMProvider(Protocol):
    name: str

    async def chat(
        self,
        messages: list[dict],
        tools: list[dict],
        *,
        model: str,
        stream: bool = False,
        metadata: dict | None = None,
    ) -> LLMResult:
        ...


class LLMProviderRegistry:
    def __init__(self) -> None:
        self._providers: dict[str, LLMProvider] = {}

    def register(self, provider: LLMProvider) -> None:
        self._providers[provider.name] = provider

    def get(self, name: str) -> LLMProvider:
        return self._providers[name]
```

First implementation should support only OpenAI-compatible chat completion.
Other providers can be added once tool-call semantics and streaming are stable.

## 5. Tool and Sandbox Prototype

```python
@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    parameters: dict[str, Any]
    handler: Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]
    sandbox_policy: str = "default"


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}

    def register(self, spec: ToolSpec) -> None:
        self._tools[spec.name] = spec

    def schema_list(self) -> list[dict[str, Any]]:
        return [
            {
                "name": spec.name,
                "description": spec.description,
                "parameters": spec.parameters,
            }
            for spec in self._tools.values()
        ]
```

Sandbox policy prototype:

```yaml
tools:
  sandbox:
    allowed_roots:
      - "${PWD}"
      - "/tmp"
    allow_network: false
    allowed_commands:
      - "python"
      - "pytest"
    timeout_seconds: 120
```

The first sandbox should be policy enforcement around local execution, not a
container runtime. A later implementation can add Docker or OS-level isolation.

## 6. Skills Prototype

Skill directory:

```text
~/.dojo/skills/
  dojo-quant-analyst/
    SKILL.md
    references/
    scripts/
    templates/
    assets/
  generated/
    btc-market-brief-style/
      SKILL.md
```

Skill metadata:

```yaml
---
name: dojo-quant-analyst
description: Use for stock and crypto market analysis workflows.
tools:
  - dojo.research.artifacts
---
```

Generated skill memory should record repeatable procedure, not private raw
conversation logs.

## 7. Memory Prototype

```python
class MemoryProvider(Protocol):
    name: str

    def is_available(self) -> bool: ...
    async def initialize(self, session_id: str, **context: Any) -> None: ...
    def system_prompt_block(self) -> str: ...
    async def prefetch(self, query: str, *, session_id: str) -> str: ...
    async def queue_prefetch(self, query: str, *, session_id: str) -> None: ...
    async def sync_turn(
        self,
        user_content: str,
        assistant_content: str,
        *,
        session_id: str,
    ) -> None: ...
    async def on_session_end(self, messages: list[dict[str, Any]]) -> None: ...
    async def shutdown(self) -> None: ...
```

Default provider:

```python
class SkillSummaryMemoryProvider:
    name = "skill_summary"

    async def on_session_end(self, messages: list[dict[str, Any]]) -> None:
        summary = await self._summarize_repeatable_workflow(messages)
        if summary.is_skill_worthy:
            await self._write_generated_skill(summary)
```

## 8. Scheduler Prototype

```python
class SchedulerService:
    def __init__(
        self,
        *,
        runtime_factory: RuntimeFactory,
        job_store: JobStore,
        gateway: GatewayDelivery | None = None,
    ) -> None:
        self.runtime_factory = runtime_factory
        self.job_store = job_store
        self.gateway = gateway

    async def run_job(self, job_id: str) -> JobRun:
        job = self.job_store.get(job_id)
        runtime = self.runtime_factory.for_profile(job.agent.profile)
        response = await runtime.agent.run(job.to_chat_request())
        run = self.job_store.save_output(job, response)
        if job.delivery and self.gateway:
            await self.gateway.send(job.delivery, response.content)
        return run
```

The scheduler should use a config snapshot for each run. Dynamic config reload
should affect future runs, not mutate a run already in progress.

## 9. Gateway Prototype

```python
@dataclass(frozen=True)
class PlatformEntry:
    name: str
    label: str
    adapter_factory: Callable[[GatewayConfig], GatewayAdapter]
    required_env: list[str]
    install_hint: str = ""


class GatewayRegistry:
    def register(self, entry: PlatformEntry) -> None: ...
    def create_adapter(self, name: str, config: GatewayConfig) -> GatewayAdapter: ...
```

Gateway adapters normalize messages into `ChatRequest` and send
`AgentResponse.content` back to the platform. They should never call financial
data providers directly.

## 10. DojoExtensions Prototype

```python
class DojoExtension(Protocol):
    name: str
    version: str

    def health(self) -> ExtensionHealth: ...
    def tool_specs(self) -> list[ToolSpec]: ...
    def dashboard_cards(self) -> list[DashboardCardSpec]: ...
    def prompt_context(self, quant_context: QuantContext) -> str: ...
```

Example extension facade:

```python

```

This is a facade only. Indicator computation, factor models, order execution,
and backtesting are intentionally outside this prototype.

## 11. Dashboard Prototype

FastAPI routes:

```python
def create_app(runtime: Runtime) -> FastAPI:
    app = FastAPI(title="DojoAgents Dashboard")

    @app.get("/api/health")
    async def health() -> dict:
        return {"ok": True}

    @app.get("/api/jobs")
    async def jobs() -> list[dict]:
        return runtime.scheduler.list_jobs()

    @app.get("/api/extensions")
    async def extensions() -> list[dict]:
        return runtime.extensions.status()

    @app.post("/api/chat")
    async def chat(request: ChatRequest) -> AgentResponse:
        return await runtime.agent.run(request)

    return app
```

Frontend views can start as static HTML/JS:

- status
- scheduled jobs
- extension cards
- config editor
- chat panel

## 12. Config Prototype

```python
class ConfigStore:
    def __init__(self, path: Path = Path("~/.dojo/agents.yaml")) -> None:
        self.path = path.expanduser()
        self._snapshot: AgentsConfig | None = None
        self._fingerprint: tuple[int, int] | None = None

    def snapshot(self) -> AgentsConfig:
        fingerprint = self._stat_fingerprint()
        if fingerprint != self._fingerprint:
            self._snapshot = self._load_and_validate()
            self._fingerprint = fingerprint
        return deepcopy(self._snapshot)
```

`ConfigStore` should provide a redacted serializer for Dashboard and logs.

## 13. First Implementation Checklist

- [ ] Create source files matching the package layout in `docs/architecture.md`.
- [ ] Add focused tests for config loading and redaction.
- [ ] Add `LLMProvider` protocol and a fake provider for tests.
- [ ] Add `ToolRegistry` and timeout-aware `ToolExecutor`.
- [ ] Add `MemoryProvider` and no-op plus skill-summary providers.
- [ ] Add `DojoExtensionRegistry` and one fake research extension.
- [ ] Add `AgentLoop` direct-answer and tool-call tests.
- [ ] Add APScheduler-backed scheduler with fake job execution tests.
- [ ] Add FastAPI dashboard endpoints with JSON contract tests.
- [ ] Add CLI entry points after core services are testable.
