from __future__ import annotations

from dojoagents.dojo_extensions.base import DojoExtension
from dojoagents.quant.context import QuantContext
from dojoagents.tools.registry import ToolSpec


class DojoExtensionRegistry:
    def __init__(self) -> None:
        self._extensions: dict[str, DojoExtension] = {}

    def register(self, extension: DojoExtension) -> None:
        self._extensions[extension.name] = extension

    def tool_specs(self) -> list[ToolSpec]:
        specs: list[ToolSpec] = []
        for extension in self._extensions.values():
            specs.extend(extension.tool_specs())
        return specs

    def prompt_context(self, quant_context: QuantContext | None) -> str:
        if quant_context is None:
            return ""
        blocks = [
            extension.prompt_context(quant_context)
            for extension in self._extensions.values()
        ]
        return "\n\n".join(block for block in blocks if block)

    def status(self) -> list[dict[str, str | bool]]:
        result = []
        for extension in self._extensions.values():
            health = extension.health()
            result.append(
                {
                    "name": extension.name,
                    "version": extension.version,
                    "ok": health.ok,
                    "message": health.message,
                }
            )
        return result
