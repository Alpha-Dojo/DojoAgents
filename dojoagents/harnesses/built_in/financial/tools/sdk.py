"""DojoSDK tool provider sharing the Harness-owned client."""

from __future__ import annotations

from typing import Any

from dojoagents.tools.dojo_sdk_tool import DojoSDKToolManager, OFFLINE_TOOL_BINDINGS
from dojoagents.tools.registry import ToolSpec

SDK_TOOL_NAMES = tuple(sorted(binding.name for binding in OFFLINE_TOOL_BINDINGS.values()))


def get_sdk_tool_specs(container: Any) -> list[ToolSpec]:
    if container.client is None:
        raise RuntimeError("financial SDK client is not ready")
    manager = DojoSDKToolManager(container.config.sdk)
    manager._client = container.client
    return manager.get_tool_specs()


__all__ = ["SDK_TOOL_NAMES", "get_sdk_tool_specs"]
