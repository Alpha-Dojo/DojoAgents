"""Side-effect-free assembly of one agent and exactly one harness instance."""

from __future__ import annotations

from hashlib import sha256
from pathlib import Path
from types import MappingProxyType
from typing import Mapping

from dojoagents.config.loader import ConfigStore
from dojoagents.dojo_extensions.registry import DojoExtensionRegistry
from dojoagents.logging import LOGGER
from dojoagents.plugins import get_plugin_registry

from .builder import HarnessBuilder
from .capabilities import MCPSourceSpec, SkillSourceSpec, ToolProviderSpec
from .config import resolve_extra_skill_sources
from .context import HarnessBuildContext
from .extra_tools import load_extra_tools
from .loader import HarnessLoader


def _stable_path_id(path: Path) -> str:
    return sha256(str(path).encode("utf-8")).hexdigest()[:12]


class RuntimeComposer:
    """Build the immutable graph without starting stores, services or tasks."""

    @classmethod
    def compose(
        cls,
        store: ConfigStore,
        *,
        host: str = "library",
        service_bindings: Mapping[str, object] | None = None,
    ):
        from dojoagents.agent.runtime import Runtime

        config = store.snapshot()
        config_path = Path(getattr(store, "path", Path.cwd() / "agents.yaml")).expanduser()
        build_context = HarnessBuildContext(
            config=config,
            harness_config=config.harness.config,
            config_dir=config_path.parent.resolve(),
            workdir=Path.cwd().resolve(),
            host=host,
            logger=LOGGER,
        )
        loaded = HarnessLoader().load(config.harness, context=build_context)
        harness = loaded.harness
        builder = HarnessBuilder(harness.descriptor)
        harness.configure(builder, build_context)

        plugin_snapshot = get_plugin_registry().contribution_snapshot()
        for tool in plugin_snapshot.tools:
            builder.add_tool_provider(
                ToolProviderSpec(
                    component_id=f"plugin.tool.{tool.name}",
                    source=plugin_snapshot.tool_sources.get(tool.name, "plugin:registry"),
                    provider=(tool,),
                    tool_names=(tool.name,),
                )
            )
        for server_id, mcp_config in plugin_snapshot.mcp_configs.items():
            builder.add_mcp_source(
                MCPSourceSpec(
                    component_id=server_id,
                    source=plugin_snapshot.mcp_sources.get(server_id, "plugin:registry"),
                    config=dict(mcp_config),
                )
            )
        for server_id, mcp_config in config.mcp_servers.items():
            builder.add_mcp_source(
                MCPSourceSpec(
                    component_id=server_id,
                    source="core:config.mcp_servers",
                    config=dict(mcp_config),
                )
            )

        extra_tools = load_extra_tools(config.harness.extra_tool_dirs) if config.harness.extra_tool_dirs else ()
        if extra_tools:
            builder.add_tool_provider(
                ToolProviderSpec(
                    component_id="configured.extra_tools",
                    source="config:harness.extra_tool_dirs",
                    provider=extra_tools,
                    tool_names=tuple(tool.name for tool in extra_tools),
                )
            )

        skill_resolution = resolve_extra_skill_sources(
            (),
            config.harness.extra_skill_dirs,
            loaded_tools=set(builder.tool_names),
        )
        for warning in skill_resolution.warnings:
            LOGGER.warning(warning)
        for root in skill_resolution.directories:
            builder.add_skill_source(
                SkillSourceSpec(
                    component_id=f"extra.skills.{_stable_path_id(root)}",
                    source=f"extra-skills:{root}",
                    provider=root,
                    skill_names=tuple(path.parent.name for path in sorted(root.glob("*/SKILL.md"))),
                )
            )

        capabilities = builder.build()
        bindings = dict(service_bindings or {})
        declared_service_ids = {spec.component_id for spec in capabilities.services}
        unknown_bindings = set(bindings).difference(declared_service_ids)
        if unknown_bindings:
            from .errors import HarnessLifecycleError

            raise HarnessLifecycleError("external service bindings are not declared by the harness: " + ", ".join(sorted(unknown_bindings)))
        return Runtime(
            config=config,
            config_store=store,
            agent=None,
            sessions=None,
            extensions=DojoExtensionRegistry(),
            scheduler=None,
            harness=harness,
            capabilities=capabilities,
            resolved_harness_factory=loaded.resolved_factory,
            service_bindings=MappingProxyType(bindings),
            state="composed",
        )
