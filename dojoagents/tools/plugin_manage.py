from __future__ import annotations

import json
import shutil
import logging
from pathlib import Path
from typing import Any

from dojoagents.tools.registry import ToolSpec
from dojoagents.plugins.registry import DojoPluginRegistry

LOGGER = logging.getLogger("dojoagents.tools.plugin_manage")


class PluginListTool:
    def __init__(self, plugin_registry: DojoPluginRegistry) -> None:
        self.plugin_registry = plugin_registry

    def get_tool_spec(self) -> ToolSpec:
        return ToolSpec(
            name="list_plugins",
            description="List all currently installed plugins, including their metadata, source, and type.",
            parameters={
                "type": "object",
                "properties": {},
            },
            handler=self.handle_call,
        )

    async def handle_call(self, args: dict[str, Any]) -> dict[str, Any]:
        LOGGER.debug("Handling list_plugins tool call")
        try:
            plugins_data = []
            for manifest in self.plugin_registry._manifests.values():
                plugins_data.append(
                    {
                        "name": manifest.name,
                        "version": manifest.version,
                        "description": manifest.description,
                        "source": manifest.source,
                        "is_claude": manifest.is_claude,
                        "provides_tools": manifest.provides_tools,
                        "provides_hooks": manifest.provides_hooks,
                        "path": manifest.path,
                    }
                )
            return {"content": json.dumps(plugins_data, indent=2, ensure_ascii=False), "metadata": {"ok": True}}
        except Exception as e:
            LOGGER.error(f"Failed to list plugins: {e}", exc_info=True)
            return {"content": f"Failed to list plugins: {e}", "metadata": {"ok": False}}


class PluginDeleteTool:
    def __init__(self, plugin_registry: DojoPluginRegistry) -> None:
        self.plugin_registry = plugin_registry

    def get_tool_spec(self) -> ToolSpec:
        return ToolSpec(
            name="delete_plugin",
            description="Delete a plugin by its name. Only user-installed plugins can be deleted.",
            parameters={"type": "object", "properties": {"name": {"type": "string", "description": "The exact name of the plugin to delete."}}, "required": ["name"]},
            handler=self.handle_call,
        )

    async def handle_call(self, args: dict[str, Any]) -> dict[str, Any]:
        name = args.get("name", "").strip()
        if not name:
            return {"content": "Plugin name is required.", "metadata": {"ok": False}}

        LOGGER.debug(f"Handling delete_plugin tool call for plugin: {name}")
        try:
            manifest = self.plugin_registry._manifests.get(name)
            if not manifest:
                return {"content": f"Plugin '{name}' not found.", "metadata": {"ok": False}}

            if manifest.source == "built_in":
                return {"content": f"Cannot delete built-in plugin '{name}'.", "metadata": {"ok": False}}

            if not manifest.path:
                return {"content": f"Plugin '{name}' does not have a valid directory path.", "metadata": {"ok": False}}

            # Resolve paths for security validation
            user_plugins_root = Path("~/.dojo/plugins").expanduser().resolve()
            plugin_path = Path(manifest.path).resolve()

            # Ensure the plugin path is strictly inside the user plugins root directory
            try:
                plugin_path.relative_to(user_plugins_root)
            except ValueError:
                LOGGER.warning(f"Security Alert: Blocked attempt to delete out-of-bounds plugin directory: {plugin_path}")
                return {"content": f"Security Error: Plugin path '{plugin_path}' is outside the authorized user plugins directory.", "metadata": {"ok": False}}

            if not plugin_path.exists():
                return {"content": f"Plugin directory '{plugin_path}' does not exist.", "metadata": {"ok": False}}

            # Perform the deletion
            LOGGER.info(f"Physically deleting plugin directory '{plugin_path}' and reloading plugin registry.")
            shutil.rmtree(plugin_path)

            # Hot-reload the plugin registry to remove the plugin from memory
            self.plugin_registry.discover_and_load(force=True)

            return {"content": f"Plugin '{name}' deleted successfully and registry reloaded.", "metadata": {"ok": True}}
        except Exception as e:
            LOGGER.error(f"Failed to delete plugin '{name}': {e}", exc_info=True)
            return {"content": f"Failed to delete plugin '{name}': {e}", "metadata": {"ok": False}}
