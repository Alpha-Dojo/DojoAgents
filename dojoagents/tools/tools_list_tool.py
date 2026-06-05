# dojoagents/tools/tools_list_tool.py
from __future__ import annotations

import json
from typing import Any
from dojoagents.tools.registry import ToolRegistry, ToolSpec


class ToolsListTool:
    def __init__(self, registry: ToolRegistry) -> None:
        self.registry = registry

    def get_tool_spec(self) -> ToolSpec:
        return ToolSpec(
            name="tools_list",
            description="List all registered tools available in the agent's runtime, including their names, descriptions, and parameter schemas.",
            parameters={
                "type": "object",
                "properties": {},
            },
            handler=self.handle_call
        )

    async def handle_call(self, args: dict[str, Any]) -> dict[str, Any]:
        try:
            tools_data = [spec.schema() for spec in self.registry.all()]
            return {
                "content": json.dumps(tools_data, indent=2, ensure_ascii=False),
                "metadata": {"ok": True}
            }
        except Exception as e:
            return {"content": f"Failed to list tools: {e}", "metadata": {"ok": False}}
