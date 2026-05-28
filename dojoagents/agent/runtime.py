from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from dojoagents.agent.loop import AgentLoop
from dojoagents.agent.providers import OpenAICompatibleProvider
from dojoagents.config.loader import ConfigStore
from dojoagents.config.models import AgentsConfig
from dojoagents.cron.jobs import JobStore
from dojoagents.dojo_extensions.quant_data import DojoMarketDataExtension
from dojoagents.dojo_extensions.registry import DojoExtensionRegistry
from dojoagents.dojo_extensions.research import DojoResearchExtension
from dojoagents.memory.manager import MemoryManager
from dojoagents.memory.skill_summary import SkillSummaryMemoryProvider
from dojoagents.skills.manager import SkillManager
from dojoagents.tools.executor import ToolExecutor
from dojoagents.tools.registry import ToolRegistry
from dojoagents.tools.sandbox import SandboxPolicy
from dojoagents.tools.skill_manage import SkillManagerTool


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
        if "dojo_market_data" in config.dojo_extensions.enabled:
            extensions.register(DojoMarketDataExtension())
        if "dojo_research" in config.dojo_extensions.enabled:
            extensions.register(DojoResearchExtension())

        tool_registry = ToolRegistry()
        for spec in extensions.tool_specs():
            tool_registry.register(spec)

        from dojoagents.plugins import get_plugin_registry
        plugin_registry = get_plugin_registry()

        skills_cfg = config.skills
        built_in_dir = Path(__file__).parent.parent / "skills" / "built_in"
        skill_dirs = [
            skills_cfg.dir,
            skills_cfg.generated_skill_dir,
            built_in_dir,
        ] + skills_cfg.external_dirs + plugin_registry._skill_dirs

        skill_manager = SkillManager(
            skill_dirs=skill_dirs,
            disabled_skills=skills_cfg.disabled,
            platform_disabled=skills_cfg.platform_disabled,
            enable_cache=config.agent.enable_skill_cache,
            lazy_skills=config.agent.lazy_skills,
        )

        skill_tool = SkillManagerTool(
            main_skills_dir=Path(skills_cfg.dir),
            skill_manager=skill_manager
        )
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

        from dojoagents.tools.mcp_tool import discover_and_register_mcp_tools
        discover_and_register_mcp_tools(tool_registry, config.mcp_servers)
        if plugin_registry._mcp_configs:
            from dojoagents.logging import LOGGER
            LOGGER.debug(f"Registering MCP tools config from plugins: {plugin_registry._mcp_configs}")
            discover_and_register_mcp_tools(tool_registry, plugin_registry._mcp_configs)

        tool_names = [spec.name for spec in tool_registry.all()]
        skill_manager.loaded_tools = set(tool_names)

        provider_cfg = config.llm_provider.providers.get(config.llm_provider.default)
        if provider_cfg is None:
            provider_cfg = next(iter(config.llm_provider.providers.values()))
        provider = OpenAICompatibleProvider(
            api_key=provider_cfg.api_key,
            base_url=provider_cfg.base_url,
        )
        provider.name = config.llm_provider.default

        memory = MemoryManager()
        if config.memory.provider == "skill_summary":
            memory.add_provider(
                SkillSummaryMemoryProvider(config.memory.generated_skill_dir)
            )

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
        )

        return cls(
            config=config,
            config_store=store,
            agent=agent,
            extensions=extensions,
            scheduler=JobStore(Path(config.scheduler.store).expanduser()),
        )

    def for_profile(self, _profile: str) -> "Runtime":
        return self
