from __future__ import annotations

from dataclasses import asdict, dataclass, replace
import inspect
from pathlib import Path
from typing import Any

from dojoagents.agent.loop import AgentLoop
from dojoagents.agent.session_manager import DojoAgentSessionManager
from dojoagents.agent.provider_state import ProviderConversationState
from dojoagents.agent.providers import OpenAICompatibleProvider, UnconfiguredLLMProvider
from dojoagents.config.loader import resolve_provider_config
from dojoagents.agent.gemini_provider import GeminiNativeProvider
from dojoagents.config.loader import ConfigStore
from dojoagents.config.models import AgentsConfig
from dojoagents.cron.jobs import JobStore
from dojoagents.dojo_extensions.registry import DojoExtensionRegistry
from dojoagents.dojo_extensions.research import DojoResearchExtension
from dojoagents.memory.manager import MemoryManager
from dojoagents.memory.skill_summary import SkillSummaryMemoryProvider
from dojoagents.skills.manager import SkillManager
from dojoagents.tools.executor import ToolExecutor
from dojoagents.tools.registry import ToolRegistry
from dojoagents.tools.sandbox import SandboxPolicy
from dojoagents.tools.skill_manage import SkillManagerTool
from dojoagents.logging import LOGGER


class _ProfileConfigStore:
    """Read-only ConfigStore view produced by the central config validator."""

    def __init__(self, parent: ConfigStore, raw: dict[str, Any], snapshot: AgentsConfig) -> None:
        self.path = parent.path
        self._raw = raw
        self._snapshot = snapshot

    def snapshot(self) -> AgentsConfig:
        return self._snapshot

    def raw(self) -> dict[str, Any]:
        return dict(self._raw)

    def redacted(self) -> dict[str, Any]:
        return asdict(self._snapshot)


class RuntimeFactory:
    """Cache Runtime instances by resolved Harness capability profile."""

    def __init__(self, config_store: ConfigStore, *, host: str = "library") -> None:
        self.config_store = config_store
        self.host = host
        self._runtimes: dict[str, Runtime] = {}

    @staticmethod
    def _graph_key(config: AgentsConfig) -> str:
        import hashlib
        import json

        graph = {
            "harness": asdict(config.harness),
            "tools": asdict(config.tools),
            "skills": asdict(config.skills),
            "memory": asdict(config.memory),
            "mcp_servers": config.mcp_servers,
            "extensions": asdict(config.dojo_extensions),
            "tasks": asdict(config.tasks),
        }
        return hashlib.sha256(json.dumps(graph, sort_keys=True, default=str).encode("utf-8")).hexdigest()

    def for_profile(self, profile: str = "default") -> "Runtime":
        from dojoagents.config.loader import _deep_merge, _to_config

        raw = self.config_store._load_raw()
        profiles = self.config_store.raw().get("profiles", {})
        override = profiles.get(profile, {}) if isinstance(profiles, dict) else {}
        if profile != "default" and not isinstance(override, dict):
            raise ValueError(f"profile {profile!r} must be a mapping")
        resolved_raw = _deep_merge(raw, override if isinstance(override, dict) else {})
        resolved_raw.pop("profiles", None)
        snapshot = _to_config(
            resolved_raw,
            base_dir=self.config_store.path.parent.resolve(),
            source_raw=resolved_raw,
        )
        key = self._graph_key(snapshot)
        runtime = self._runtimes.get(key)
        if runtime is None:
            runtime = Runtime.compose(
                _ProfileConfigStore(self.config_store, resolved_raw, snapshot),
                host=self.host,
            )
            self._runtimes[key] = runtime
        return runtime

    async def shutdown(self) -> None:
        for runtime in reversed(tuple(self._runtimes.values())):
            await runtime.shutdown()
        self._runtimes.clear()


@dataclass
class Runtime:
    config: AgentsConfig
    config_store: ConfigStore
    agent: AgentLoop
    sessions: DojoAgentSessionManager
    extensions: DojoExtensionRegistry
    scheduler: JobStore
    task_manager: Any | None = None
    task_activator: Any | None = None
    command_router: Any | None = None
    pipeline_runner: Any | None = None
    harness: Any | None = None
    capabilities: Any | None = None
    resolved_harness_factory: str | None = None
    session_store: Any | None = None
    blob_store: Any | None = None
    session_service: Any | None = None
    harness_runtime_context: Any | None = None
    lifecycle_manager: Any | None = None
    state: str = "legacy"
    _legacy_surfaces: dict[str, Any] | None = None

    @classmethod
    def compose(cls, store: ConfigStore, *, host: str = "library") -> "Runtime":
        """Assemble a Harness capability graph without starting resources."""

        from dojoagents.harnesses.composer import RuntimeComposer

        return RuntimeComposer.compose(store, host=host)

    @classmethod
    async def create(cls, store: ConfigStore, *, host: str = "library") -> "Runtime":
        """Compose and fully start a Harness-backed Runtime."""

        runtime = cls.compose(store, host=host)
        await runtime.startup()
        return runtime

    async def startup(self) -> None:
        """Start canonical stores, Harness services and the Harness atomically."""

        if self.state == "ready":
            return
        if self.state != "composed":
            if self.state == "legacy":
                return
            raise RuntimeError(f"runtime cannot start from state {self.state!r}")

        from dojoagents.harnesses.context import (
            HarnessObjectFacade,
            HarnessRuntimeContext,
            HarnessSessionStateFacade,
        )
        from dojoagents.harnesses.errors import HarnessLifecycleError
        from dojoagents.harnesses.lifecycle import LifecycleManager
        from dojoagents.sessions.factory import create_blob_store, create_session_store, shutdown_stores
        from dojoagents.sessions.service import SessionService

        self.state = "starting"
        try:
            self.session_store = await create_session_store(self.config.sessions.store)
            self.blob_store = await create_blob_store(self.config.sessions.blob_store)
            self.session_service = SessionService(
                store=self.session_store,
                blob_store=self.blob_store,
                config=self.config.sessions,
            )
            self.sessions = self.session_service
            self.lifecycle_manager = LifecycleManager(self.capabilities.services)
            services = await self.lifecycle_manager.startup()
            for service in services.values():
                if callable(getattr(service, "project_results", None)):
                    self.session_service.set_result_projector(service)
                    break
            self.harness_runtime_context = HarnessRuntimeContext(
                capabilities=self.capabilities,
                services=services,
                logger=LOGGER,
                session_state_facade=HarnessSessionStateFacade(
                    self.session_service,
                    self.capabilities.descriptor,
                    self.capabilities.state_codec,
                ),
                object_facade=HarnessObjectFacade(self.session_service),
            )
            await self.harness.startup(self.harness_runtime_context)
            await self._build_harness_agent()
            self.state = "ready"
        except Exception as exc:
            if self.harness_runtime_context is not None:
                try:
                    await self.harness.shutdown(self.harness_runtime_context)
                except Exception:
                    LOGGER.exception("Harness rollback shutdown failed")
            if self.lifecycle_manager is not None:
                try:
                    await self.lifecycle_manager.shutdown()
                except Exception:
                    LOGGER.exception("Harness service rollback failed")
            await shutdown_stores(*(store for store in (self.blob_store, self.session_store) if store is not None))
            self.session_store = None
            self.blob_store = None
            self.session_service = None
            self.sessions = None
            self.state = "failed"
            if isinstance(exc, HarnessLifecycleError):
                raise
            raise HarnessLifecycleError(f"Runtime startup failed: {type(exc).__name__}: {exc}") from exc

    async def shutdown(self) -> None:
        """Release all Harness-owned resources in reverse order, idempotently."""

        if self.state in {"stopped", "legacy"}:
            return
        from dojoagents.harnesses.errors import HarnessLifecycleError
        from dojoagents.sessions.factory import shutdown_stores

        errors: list[str] = []
        if self.state == "ready" and self.harness_runtime_context is not None:
            try:
                await self.harness.shutdown(self.harness_runtime_context)
            except Exception as exc:
                LOGGER.exception("Harness shutdown failed")
                errors.append(f"harness: {exc}")
        if self.lifecycle_manager is not None:
            try:
                await self.lifecycle_manager.shutdown()
            except Exception as exc:
                LOGGER.exception("Harness services shutdown failed")
                errors.append(f"services: {exc}")
        await shutdown_stores(*(store for store in (self.blob_store, self.session_store) if store is not None))
        self.session_store = None
        self.blob_store = None
        self.session_service = None
        self.state = "stopped"
        if errors:
            raise HarnessLifecycleError("Runtime shutdown failed: " + "; ".join(errors))

    def surface(self, surface_id: str) -> Any:
        """Resolve an adapter declared by this Runtime's bound Harness."""

        if self.capabilities is None:
            if self._legacy_surfaces is None:
                self._legacy_surfaces = {}
            if surface_id not in self._legacy_surfaces:
                factory = getattr(self.harness, "legacy_surface", None)
                if not callable(factory):
                    raise KeyError(f"surface '{surface_id}' is unavailable on a legacy Runtime")
                self._legacy_surfaces[surface_id] = factory(surface_id, self)
            return self._legacy_surfaces[surface_id]
        for spec in self.capabilities.surfaces:
            if spec.component_id == surface_id:
                return spec.adapter
        raise KeyError(f"surface '{surface_id}' is not registered")

    async def _build_harness_agent(self) -> AgentLoop:
        """Resolve the generic AgentLoop from the frozen capability graph."""

        from dojoagents.agent.providers import OpenAICompatibleProvider, UnconfiguredLLMProvider
        from dojoagents.harnesses.decisions import ToolControlDecision
        from dojoagents.harnesses.runtime import HarnessRuntime
        from dojoagents.memory.manager import MemoryManager
        from dojoagents.sessions.memory_sync import SessionMemorySyncWorker
        from dojoagents.skills.manager import SkillManager
        from dojoagents.tools.executor import ToolExecutor
        from dojoagents.tools.artifacts import ToolResultArtifactStore
        from dojoagents.tools.mcp_tool import discover_and_register_mcp_tools
        from dojoagents.tools.registry import ToolRegistry, ToolSpec

        registry = ToolRegistry()
        for provider_spec in self.capabilities.tools:
            provided = provider_spec.provider
            if callable(provided):
                provided = provided(self.harness_runtime_context)
                if inspect.isawaitable(provided):
                    provided = await provided
            if isinstance(provided, ToolSpec):
                provided = (provided,)
            for tool in tuple(provided or ()):
                if not isinstance(tool, ToolSpec):
                    raise TypeError(f"tool provider '{provider_spec.component_id}' from {provider_spec.source} returned a non-ToolSpec")
                if registry.get(tool.name) is not None:
                    raise RuntimeError(f"resolved tool name conflict: {tool.name}")
                registry.register(tool)

        mcp_configs = {spec.component_id: dict(spec.config or {}) for spec in self.capabilities.mcp_sources}
        if mcp_configs:
            import asyncio

            await asyncio.to_thread(discover_and_register_mcp_tools, registry, mcp_configs)

        sandbox = SandboxPolicy(
            allowed_roots=self.config.tools.sandbox.allowed_roots,
            allow_network=self.config.tools.sandbox.allow_network,
            allowed_commands=self.config.tools.sandbox.allowed_commands,
            timeout_seconds=self.config.tools.sandbox.timeout_seconds,
        )

        async def revalidate(call: Any) -> None:
            spec = registry.get(call.name)
            if spec is None:
                raise ValueError(f"tool '{call.name}' is not registered")
            if not isinstance(call.arguments, dict):
                raise ValueError(f"tool '{call.name}' arguments must be an object")
            required = spec.parameters.get("required", ()) if isinstance(spec.parameters, dict) else ()
            missing = [name for name in required if name not in call.arguments]
            if missing:
                raise ValueError(f"tool '{call.name}' missing required arguments: {', '.join(missing)}")
            sandbox.check_tool(call.name)

        async def core_authorize(call: Any, context: Any) -> ToolControlDecision:
            return ToolControlDecision("allow", "core_safety_allowed")

        harness_runtime = HarnessRuntime(
            self.capabilities,
            core_safety_prompt=("Follow Core safety constraints. Never bypass tool schemas, SandboxPolicy, " "session identity boundaries, or explicit user authorization."),
            core_tool_authorizer=core_authorize,
            revalidate_tool_call=revalidate,
            max_recovery_turns=min(3, max(0, self.config.agent.max_iterations - 1)),
        )
        memory = MemoryManager()
        for memory_spec in self.capabilities.memories:
            provider = memory_spec.provider
            if callable(provider):
                provider = provider(self.harness_runtime_context)
                if inspect.isawaitable(provider):
                    provider = await provider
            if provider is not None:
                memory.add_provider(provider)

        skill_dirs = [spec.provider for spec in self.capabilities.skills if isinstance(spec.provider, (str, Path))]
        skills = SkillManager(
            skill_dirs=skill_dirs,
            disabled_skills=self.config.skills.disabled,
            platform_disabled=self.config.skills.platform_disabled,
            loaded_tools=[tool.name for tool in registry.all()],
            enable_cache=self.config.agent.enable_skill_cache,
            lazy_skills=self.config.agent.lazy_skills,
        )

        self.task_manager = None
        self.task_activator = None
        self.command_router = None
        self.pipeline_runner = None
        if self.config.tasks.enabled and self.capabilities.tasks:
            from dojoagents.tasks.activator import TaskActivator
            from dojoagents.tasks.command_router import CommandRouter
            from dojoagents.tasks.manager import TaskPromptManager
            from dojoagents.tasks.pipeline import PipelineRunner
            from dojoagents.tasks.schema_validator import TaskOutputValidator

            task_dirs = [Path(spec.provider).expanduser() for spec in self.capabilities.tasks if isinstance(spec.provider, (str, Path))]
            pipeline_dirs = [Path(spec.provider).expanduser() for spec in self.capabilities.pipelines if isinstance(spec.provider, (str, Path))]
            self.task_manager = TaskPromptManager(
                task_dirs=task_dirs,
                pipeline_dirs=pipeline_dirs,
            )
            self.task_activator = TaskActivator(
                manager=self.task_manager,
                sessions_root=self.config.sessions.root,
                task_output_root=self.config.tasks.output_root,
                auto_detect=self.config.tasks.auto_detect,
            )
            self.command_router = CommandRouter(
                manager=self.task_manager,
                activator=self.task_activator,
                skill_manager=skills,
            )
            self.pipeline_runner = PipelineRunner(
                manager=self.task_manager,
                activator=self.task_activator,
                validator=TaskOutputValidator(self.task_manager),
                task_output_root=self.config.tasks.output_root,
            )

        provider_name, provider_cfg = resolve_provider_config(self.config.llm_provider)
        if provider_cfg is None:
            llm_provider: Any = UnconfiguredLLMProvider()
            model = self.config.agent.model or "unconfigured"
        elif provider_name == "gemini":
            llm_provider = GeminiNativeProvider(
                api_key=provider_cfg.api_key,
                api_key_env=provider_cfg.api_key_env,
                base_url=provider_cfg.base_url,
            )
            model = self.config.agent.model or provider_cfg.model
        else:
            llm_provider = OpenAICompatibleProvider(
                api_key=provider_cfg.api_key,
                base_url=provider_cfg.base_url,
                author=provider_cfg.author,
            )
            llm_provider.name = provider_name or "openai"
            model = self.config.agent.model or provider_cfg.model

        agent_config = replace(self.config.agent, model=model or "unconfigured")
        memory_worker = SessionMemorySyncWorker(self.session_service, memory) if self.config.sessions.sync_memory else None
        artifact_store = ToolResultArtifactStore(self.config.sessions.root)
        artifact_adapter = self.capabilities.artifact_adapter.adapter if self.capabilities.artifact_adapter is not None else None
        self.agent = AgentLoop(
            llm_provider=llm_provider,
            tool_executor=ToolExecutor(
                registry,
                sandbox,
                artifact_store=artifact_store,
                artifact_adapter=artifact_adapter,
                presenter_registry=None,
            ),
            skill_manager=skills,
            memory_manager=memory,
            extension_registry=self.extensions,
            config=agent_config,
            provider_config=provider_cfg,
            session_service=self.session_service,
            task_manager=self.task_manager,
            harness_descriptor=self.capabilities.descriptor,
            harness_runtime=harness_runtime,
            memory_sync_worker=memory_worker,
        )
        return self.agent

    @classmethod
    def from_default_config(cls) -> "Runtime":
        return cls.from_config_store(ConfigStore())

    @classmethod
    def from_config_store(cls, store: ConfigStore) -> "Runtime":
        config = store.snapshot()
        from dojoagents.harnesses.context import HarnessBuildContext
        from dojoagents.harnesses.loader import HarnessLoader

        config_path = Path(getattr(store, "path", Path.cwd() / "agents.yaml")).expanduser()
        build_context = HarnessBuildContext(
            config=config,
            harness_config=config.harness.config,
            config_dir=config_path.parent.resolve(),
            workdir=Path.cwd().resolve(),
            host="legacy",
            logger=LOGGER,
        )
        loaded_harness = HarnessLoader().load(config.harness, context=build_context).harness
        legacy_contribution_factory = getattr(
            loaded_harness,
            "legacy_runtime_contributions",
            None,
        )
        if not callable(legacy_contribution_factory):
            raise RuntimeError(
                f"Harness '{loaded_harness.descriptor.id}' does not support the deprecated " "synchronous Runtime.from_config_store(); use await Runtime.create(...)"
            )
        legacy_contributions = legacy_contribution_factory(config)
        extensions = DojoExtensionRegistry()
        if "dojo_research" in config.dojo_extensions.enabled:
            extensions.register(DojoResearchExtension())

        tool_registry = ToolRegistry()
        for spec in extensions.tool_specs():
            tool_registry.register(spec)

        from dojoagents.plugins import get_plugin_registry

        plugin_registry = get_plugin_registry()
        plugin_snapshot = plugin_registry.contribution_snapshot()

        skills_cfg = config.skills
        built_in_dir = Path(__file__).parent.parent / "skills" / "built_in"
        skill_dirs = (
            [
                skills_cfg.dir,
                skills_cfg.generated_skill_dir,
                built_in_dir,
            ]
            + skills_cfg.external_dirs
            + list(plugin_snapshot.skill_dirs)
        )

        if skills_cfg.read_claude_skills:
            skill_dirs.append("~/.claude/skills")

        skill_manager = SkillManager(
            skill_dirs=skill_dirs,
            disabled_skills=skills_cfg.disabled,
            platform_disabled=skills_cfg.platform_disabled,
            enable_cache=config.agent.enable_skill_cache,
            lazy_skills=config.agent.lazy_skills,
        )

        skill_tool = SkillManagerTool(main_skills_dir=Path(skills_cfg.dir), skill_manager=skill_manager)
        tool_registry.register(skill_tool.get_tool_spec())

        from dojoagents.tools.skill_manage import SkillsListTool, SkillViewTool

        tool_registry.register(SkillsListTool(skill_manager).get_tool_spec())
        tool_registry.register(SkillViewTool(skill_manager).get_tool_spec())

        from dojoagents.tools.plugin_manage import PluginListTool, PluginDeleteTool

        tool_registry.register(PluginListTool(plugin_registry).get_tool_spec())
        tool_registry.register(PluginDeleteTool(plugin_registry).get_tool_spec())

        from dojoagents.tools.terminal_tool import get_terminal_spec

        policy = SandboxPolicy(
            allowed_roots=config.tools.sandbox.allowed_roots,
            allow_network=config.tools.sandbox.allow_network,
            allowed_commands=config.tools.sandbox.allowed_commands,
            timeout_seconds=config.tools.sandbox.timeout_seconds,
        )
        tool_registry.register(get_terminal_spec(policy))

        task_manager = None
        task_activator = None
        command_router = None
        pipeline_runner = None
        if config.tasks.enabled:
            from dojoagents.tasks.manager import TaskPromptManager
            from dojoagents.tasks.activator import TaskActivator
            from dojoagents.tasks.command_router import CommandRouter
            from dojoagents.tasks.pipeline import PipelineRunner
            from dojoagents.tasks.schema_validator import TaskOutputValidator

            task_dirs = [
                *legacy_contributions.task_directories,
                *[Path(path).expanduser() for path in config.tasks.dirs],
            ]
            task_manager = TaskPromptManager(
                task_dirs=task_dirs,
                pipeline_dirs=list(legacy_contributions.pipeline_directories),
            )
            task_activator = TaskActivator(
                manager=task_manager,
                sessions_root=config.sessions.root,
                task_output_root=config.tasks.output_root,
                auto_detect=config.tasks.auto_detect,
            )
            command_router = CommandRouter(
                manager=task_manager,
                activator=task_activator,
                skill_manager=skill_manager,
            )
            pipeline_runner = PipelineRunner(
                manager=task_manager,
                activator=task_activator,
                validator=TaskOutputValidator(task_manager),
                task_output_root=config.tasks.output_root,
            )

        from dojoagents.tools.code_execution_tool import get_code_execution_spec
        from dojoagents.tools.artifacts import ToolResultArtifactStore

        artifact_store = ToolResultArtifactStore(config.sessions.root)
        artifact_adapter = legacy_contributions.artifact_adapter
        tool_registry.register(
            get_code_execution_spec(
                tool_registry,
                policy,
                artifact_store=artifact_store,
                artifact_adapter=artifact_adapter,
                sessions_root=config.sessions.root,
            )
        )

        from dojoagents.tools.session_file_tool import get_write_session_file_spec

        tool_registry.register(
            get_write_session_file_spec(
                config.sessions.root,
                task_output_root=config.tasks.output_root if config.tasks.enabled else None,
                task_manager=task_manager,
            )
        )

        from dojoagents.tools.session_file_tool import get_read_session_output_spec

        tool_registry.register(
            get_read_session_output_spec(
                config.sessions.root,
                task_output_root=config.tasks.output_root if config.tasks.enabled else None,
            )
        )

        from dojoagents.tools.session_input_tool import get_read_session_input_spec

        tool_registry.register(get_read_session_input_spec(config.sessions.root))

        for spec in legacy_contributions.additional_tool_specs:
            tool_registry.register(spec)

        from dojoagents.tools.tools_list_tool import ToolsListTool

        tool_registry.register(ToolsListTool(tool_registry).get_tool_spec())

        from dojoagents.tools.web_searcher import get_web_searcher_specs

        for spec in get_web_searcher_specs(config.tools.web):
            tool_registry.register(spec)

        # Multi-Agent setup
        pool = None
        if config.multi_agent.enabled:
            from dojoagents.multi_agent.pool import AgentPool
            from dojoagents.multi_agent.models import AgentSpec, AgentRole
            from dojoagents.multi_agent.tools import get_delegation_tool_spec
            from dojoagents.multi_agent.orchestrator import Orchestrator

            # Two-phase init: create pool with None runtime, set later
            pool = AgentPool.__new__(AgentPool)
            pool._runtime = None
            pool._agents = {}
            pool._specs = {}

            for agent_def in config.multi_agent.default_agents:
                spec = AgentSpec(
                    role=AgentRole(agent_def["role"]),
                    name=agent_def["name"],
                    model=agent_def.get("model"),
                )
                pool.register_agent(spec)

            # Register delegation tool
            tool_registry.register(get_delegation_tool_spec(pool))

        # Plan setup
        plan_hook = None
        if config.planning.enabled:
            from dojoagents.planning.store import PlanStateStore
            from dojoagents.planning.engine import PlanExecutionEngine
            from dojoagents.planning.tools import get_plan_tools
            from dojoagents.planning.triggers import PlanActivationHook

            store = PlanStateStore(config.planning.plan_store_path)
            plan_engine = PlanExecutionEngine(pool, store)
            for spec in get_plan_tools(plan_engine):
                tool_registry.register(spec)
            plan_hook = PlanActivationHook()

        from dojoagents.tools.mcp_tool import discover_and_register_mcp_tools

        discover_and_register_mcp_tools(tool_registry, config.mcp_servers)
        if plugin_snapshot.mcp_configs:
            LOGGER.debug(f"Registering MCP tools config from plugins: {plugin_snapshot.mcp_configs}")
            discover_and_register_mcp_tools(tool_registry, dict(plugin_snapshot.mcp_configs))

        tool_names = [spec.name for spec in tool_registry.all()]
        skill_manager.loaded_tools = set(tool_names)

        provider_state = ProviderConversationState()
        provider_name, provider_cfg = resolve_provider_config(config.llm_provider)
        if provider_cfg is None:
            provider = UnconfiguredLLMProvider()
            LOGGER.info("Runtime started without LLM provider configuration")
        elif provider_name == "gemini":
            provider = GeminiNativeProvider(
                api_key=provider_cfg.api_key,
                api_key_env=provider_cfg.api_key_env,
                base_url=provider_cfg.base_url,
            )
            LOGGER.info(
                "Runtime selected LLM provider: provider=%s implementation=%s model=%s base_url=%s api_key_present=%s",
                provider_name,
                type(provider).__name__,
                provider_cfg.model,
                getattr(provider_cfg, "base_url", None),
                bool(getattr(provider_cfg, "api_key", None) or getattr(provider_cfg, "api_key_env", None)),
            )
        else:
            provider = OpenAICompatibleProvider(
                api_key=provider_cfg.api_key,
                base_url=provider_cfg.base_url,
                author=provider_cfg.author,
            )
            provider.name = provider_name or "openai"
            LOGGER.info(
                "Runtime selected LLM provider: provider=%s implementation=%s model=%s base_url=%s api_key_present=%s",
                provider_name,
                type(provider).__name__,
                provider_cfg.model,
                getattr(provider_cfg, "base_url", None),
                bool(getattr(provider_cfg, "api_key", None) or getattr(provider_cfg, "api_key_env", None)),
            )

        memory = MemoryManager()
        if config.memory.provider == "skill_summary":
            memory.add_provider(SkillSummaryMemoryProvider(config.memory.generated_skill_dir))

        sessions = DojoAgentSessionManager(
            root=config.sessions.root,
            memory_manager=memory,
            agent_id=config.sessions.agent_id,
            provider=config.sessions.provider,
            sync_memory=config.sessions.sync_memory,
            export_default_dir=config.sessions.export_default_dir,
            enabled=config.sessions.enabled,
        )

        presenter_factory = legacy_contributions.presenter_factory
        sessions.presenter_factory = presenter_factory
        agent = AgentLoop(
            llm_provider=provider,
            tool_executor=ToolExecutor(
                tool_registry,
                policy,
                artifact_store=artifact_store,
                artifact_adapter=artifact_adapter,
                presenter_registry=presenter_factory() if presenter_factory is not None else None,
            ),
            skill_manager=skill_manager,
            memory_manager=memory,
            extension_registry=extensions,
            config=config.agent,
            plan_activation_hook=plan_hook,
            task_harnesses=legacy_contributions.build_task_harnesses(
                task_manager,
                config,
            ),
            provider_config=provider_cfg,
            provider_state=provider_state,
            session_manager=sessions,
            task_manager=task_manager,
            legacy_behavior=legacy_contributions.behavior,
        )

        # Wire pool runtime reference after agent creation
        if pool is not None:
            pool._runtime = type("RuntimeRef", (), {"agent": agent, "config": config})()
            from dojoagents.multi_agent.automation import MultiAgentAutoDispatcher

            # Instantiate to register with event_bus
            _dispatcher = MultiAgentAutoDispatcher(pool)  # noqa

        if config.planning.enabled:
            from dojoagents.planning.automation import AutoPlanManager

            # Instantiate to register with event_bus
            _plan_manager = AutoPlanManager(llm_provider=provider, model=config.agent.model, plan_engine=plan_engine)  # noqa

        # Register multi-agent trigger hooks in plugin system
        if config.multi_agent.enabled:
            from dojoagents.multi_agent.triggers import MultiAgentTriggerHook
            from dojoagents.multi_agent.orchestrator import Orchestrator  # noqa

            orchestrator = Orchestrator()
            trigger_hook = MultiAgentTriggerHook(orchestrator)
            plugin_registry.register_runtime_hook("pre_llm_call", trigger_hook.on_pre_llm_call)
            plugin_registry.register_runtime_hook("post_tool_call", trigger_hook.on_post_tool_call)

        return cls(
            config=config,
            config_store=store,
            agent=agent,
            sessions=sessions,
            extensions=extensions,
            scheduler=JobStore(Path(config.scheduler.store).expanduser()),
            task_manager=task_manager,
            task_activator=task_activator,
            command_router=command_router,
            pipeline_runner=pipeline_runner,
            harness=loaded_harness,
        )

    def for_profile(self, _profile: str) -> "Runtime":
        return self
