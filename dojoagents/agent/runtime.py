from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from dojoagents.agent.loop import AgentLoop
from dojoagents.agent.provider_state import ProviderConversationState
from dojoagents.agent.providers import OpenAICompatibleProvider
from dojoagents.agent.gemini_provider import GeminiNativeProvider
from dojoagents.agent.harnesses import PortfolioTaskHarness
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


@dataclass
class Runtime:
    config: AgentsConfig
    config_store: ConfigStore
    agent: AgentLoop
    extensions: DojoExtensionRegistry
    scheduler: JobStore

    @classmethod
    def from_default_config(cls) -> "Runtime":
        return cls.from_config_store(ConfigStore())

    @classmethod
    def from_config_store(cls, store: ConfigStore) -> "Runtime":
        config = store.snapshot()
        extensions = DojoExtensionRegistry()
        if "dojo_research" in config.dojo_extensions.enabled:
            extensions.register(DojoResearchExtension())

        tool_registry = ToolRegistry()
        for spec in extensions.tool_specs():
            tool_registry.register(spec)

        from dojoagents.plugins import get_plugin_registry

        plugin_registry = get_plugin_registry()

        skills_cfg = config.skills
        built_in_dir = Path(__file__).parent.parent / "skills" / "built_in"
        skill_dirs = (
            [
                skills_cfg.dir,
                skills_cfg.generated_skill_dir,
                built_in_dir,
            ]
            + skills_cfg.external_dirs
            + plugin_registry._skill_dirs
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

        from dojoagents.tools.code_execution_tool import get_code_execution_spec

        tool_registry.register(get_code_execution_spec(tool_registry, policy))

        from dojoagents.tools.dojo_sdk_tool import get_dojo_sdk_specs

        for spec in get_dojo_sdk_specs(config.dojosdk):
            tool_registry.register(spec)

        from dojoagents.tools.tools_list_tool import ToolsListTool

        tool_registry.register(ToolsListTool(tool_registry).get_tool_spec())

        from dojoagents.tools.web_searcher import get_web_searcher_specs

        for spec in get_web_searcher_specs(config.tools.web):
            tool_registry.register(spec)

        from dojoagents.tools.agent_viz import get_agent_viz_specs

        for spec in get_agent_viz_specs():
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
        if plugin_registry._mcp_configs:
            LOGGER.debug(f"Registering MCP tools config from plugins: {plugin_registry._mcp_configs}")
            discover_and_register_mcp_tools(tool_registry, plugin_registry._mcp_configs)

        tool_names = [spec.name for spec in tool_registry.all()]
        skill_manager.loaded_tools = set(tool_names)

        provider_cfg = config.llm_provider.providers.get(config.llm_provider.default)
        if provider_cfg is None:
            provider_cfg = next(iter(config.llm_provider.providers.values()))
        provider_state = ProviderConversationState()
        provider_name = config.llm_provider.default
        if provider_name == "gemini":
            provider = GeminiNativeProvider(
                api_key=provider_cfg.api_key,
                api_key_env=provider_cfg.api_key_env,
                base_url=provider_cfg.base_url,
            )
        else:
            provider = OpenAICompatibleProvider(
                api_key=provider_cfg.api_key,
                base_url=provider_cfg.base_url,
            )
            provider.name = provider_name
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

        agent = AgentLoop(
            llm_provider=provider,
            tool_executor=ToolExecutor(
                tool_registry,
                policy,
            ),
            skill_manager=skill_manager,
            memory_manager=memory,
            extension_registry=extensions,
            config=config.agent,
            plan_activation_hook=plan_hook,
            task_harnesses=[PortfolioTaskHarness()],
            provider_config=provider_cfg,
            provider_state=provider_state,
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
            plugin_registry._hooks.setdefault("pre_llm_call", []).append(trigger_hook.on_pre_llm_call)
            plugin_registry._hooks.setdefault("post_tool_call", []).append(trigger_hook.on_post_tool_call)

        return cls(
            config=config,
            config_store=store,
            agent=agent,
            extensions=extensions,
            scheduler=JobStore(Path(config.scheduler.store).expanduser()),
        )

    def for_profile(self, _profile: str) -> "Runtime":
        return self
