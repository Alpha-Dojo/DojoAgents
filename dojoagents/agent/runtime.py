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
                SandboxPolicy(
                    allowed_roots=config.tools.sandbox.allowed_roots,
                    allow_network=config.tools.sandbox.allow_network,
                    allowed_commands=config.tools.sandbox.allowed_commands,
                    timeout_seconds=config.tools.sandbox.timeout_seconds,
                ),
            ),
            skill_manager=SkillManager([]),
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
