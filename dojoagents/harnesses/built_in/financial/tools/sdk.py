"""DojoSDK tool provider sharing the Harness-owned client."""

from __future__ import annotations

from typing import Any

from .sdk_runtime import OFFLINE_TOOL_BINDINGS
from .backend_delegation import get_backend_tool_specs
from dojoagents.tools.registry import ToolSpec

SDK_TOOL_NAMES = tuple(sorted(binding.name for binding in OFFLINE_TOOL_BINDINGS.values()))


def get_sdk_tool_specs(backend: Any) -> list[ToolSpec]:
    return get_backend_tool_specs(backend, SDK_TOOL_NAMES)


__all__ = ["SDK_TOOL_NAMES", "get_sdk_tool_specs"]
