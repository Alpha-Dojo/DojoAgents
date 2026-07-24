from pathlib import Path

import pytest

from dojoagents.harnesses.errors import CapabilityConflictError
from dojoagents.harnesses.extra_tools import load_extra_tools
from dojoagents.harnesses.config import resolve_extra_skill_sources


def _write_provider(root: Path, marker: str, tool_name: str = "echo") -> None:
    (root / "provider.py").write_text(
        "from dojoagents.tools.registry import ToolSpec\n"
        "async def handler(args): return {'marker': '" + marker + "'}\n"
        "def create_tools():\n"
        "    return [ToolSpec('" + tool_name + "', 'echo', {'type': 'object'}, handler)]\n",
        encoding="utf-8",
    )
    (root / "tools.yaml").write_text("module: provider.py\nfactory: create_tools\n", encoding="utf-8")


@pytest.mark.asyncio
async def test_extra_tool_modules_are_isolated_by_content_and_root(tmp_path):
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()
    _write_provider(first, "first", "first_echo")
    _write_provider(second, "second", "second_echo")

    first_tools = load_extra_tools(first)
    second_tools = load_extra_tools(second)

    assert (await first_tools[0].handler({}))["marker"] == "first"
    assert (await second_tools[0].handler({}))["marker"] == "second"
    assert first_tools[0].handler.__module__ != second_tools[0].handler.__module__


def test_extra_tools_reject_path_escape_wrong_result_and_duplicates(tmp_path):
    root = tmp_path / "tools"
    root.mkdir()
    (root / "tools.yaml").write_text("module: ../outside.py\nfactory: create_tools\n", encoding="utf-8")
    with pytest.raises(ValueError, match="escape"):
        load_extra_tools(root)

    (root / "bad.py").write_text("def create_tools(): return [object()]\n", encoding="utf-8")
    (root / "tools.yaml").write_text("module: bad.py\nfactory: create_tools\n", encoding="utf-8")
    with pytest.raises(TypeError, match="ToolSpec"):
        load_extra_tools(root)

    one = tmp_path / "one"
    two = tmp_path / "two"
    one.mkdir()
    two.mkdir()
    _write_provider(one, "one")
    _write_provider(two, "two")
    with pytest.raises(CapabilityConflictError, match="echo"):
        load_extra_tools((one, two))


def test_skill_resolution_keeps_harness_priority_and_disables_unmet_extra_requirements(tmp_path):
    harness = tmp_path / "harness"
    extra = tmp_path / "extra"
    (harness / "research").mkdir(parents=True)
    (extra / "research").mkdir(parents=True)
    (extra / "optional").mkdir(parents=True)
    (harness / "research" / "SKILL.md").write_text("# harness", encoding="utf-8")
    (extra / "research" / "SKILL.md").write_text("# extra duplicate", encoding="utf-8")
    (extra / "optional" / "SKILL.md").write_text("---\nrequires_tools: [missing_tool]\n---\n# optional", encoding="utf-8")

    resolution = resolve_extra_skill_sources((harness,), (extra,), loaded_tools={"echo"})

    assert resolution.directories == (harness.resolve(), extra.resolve())
    assert resolution.disabled_skills == frozenset({"optional"})
    assert any("research" in warning for warning in resolution.warnings)
