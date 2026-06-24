"""Tests for ToolRegistry.clone() and ToolRegistry.remove() methods."""

import pytest
from unittest.mock import AsyncMock

from dojoagents.tools.registry import ToolRegistry, ToolSpec


def _make_spec(name: str) -> ToolSpec:
    return ToolSpec(
        name=name,
        description=f"Tool {name}",
        parameters={"type": "object"},
        handler=AsyncMock(),
    )


class TestToolRegistryClone:
    def test_clone_creates_independent_copy(self):
        reg = ToolRegistry()
        reg.register(_make_spec("a"))
        clone = reg.clone()
        clone.register(_make_spec("b"))
        assert reg.get("b") is None
        assert clone.get("b") is not None

    def test_clone_preserves_tool_specs(self):
        reg = ToolRegistry()
        spec_a = _make_spec("a")
        spec_b = _make_spec("b")
        reg.register(spec_a)
        reg.register(spec_b)
        clone = reg.clone()
        assert clone.get("a") is spec_a
        assert clone.get("b") is spec_b

    def test_clone_has_same_all_list(self):
        reg = ToolRegistry()
        reg.register(_make_spec("x"))
        reg.register(_make_spec("y"))
        clone = reg.clone()
        assert len(clone.all()) == 2


class TestToolRegistryRemove:
    def test_remove_deletes_tool(self):
        reg = ToolRegistry()
        reg.register(_make_spec("a"))
        reg.remove("a")
        assert reg.get("a") is None
        assert len(reg.all()) == 0

    def test_remove_nonexistent_is_noop(self):
        reg = ToolRegistry()
        reg.register(_make_spec("a"))
        reg.remove("nonexistent")  # should not raise
        assert len(reg.all()) == 1

    def test_clone_then_remove_isolation(self):
        reg = ToolRegistry()
        reg.register(_make_spec("a"))
        clone = reg.clone()
        clone.remove("a")
        assert reg.get("a") is not None
        assert clone.get("a") is None
