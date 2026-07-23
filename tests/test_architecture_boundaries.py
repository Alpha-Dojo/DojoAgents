from __future__ import annotations

import ast
from pathlib import Path


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            modules.add(node.module or "")
        elif isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
    return modules


def test_generic_harness_framework_does_not_import_financial_or_dashboard_domains():
    paths = [path for path in Path("dojoagents/harnesses").rglob("*.py") if "built_in" not in path.parts]
    for path in paths:
        forbidden = {module for module in _imports(path) if module.startswith(("dojoagents.dashboard", "dojoagents.quant")) or module.startswith("dojoagents.agent.harnesses")}
        assert not forbidden, f"{path}: {sorted(forbidden)}"


def test_sessions_and_core_execution_do_not_import_dashboard_domain():
    paths = list(Path("dojoagents/sessions").rglob("*.py")) + [
        Path("dojoagents/agent/models.py"),
        Path("dojoagents/agent/loop.py"),
        Path("dojoagents/agent/runtime.py"),
        Path("dojoagents/tools/executor.py"),
    ]
    for path in paths:
        forbidden = {module for module in _imports(path) if module.startswith(("dojoagents.dashboard", "dojoagents.quant")) or module.startswith("dojoagents.agent.harnesses")}
        assert not forbidden, f"{path}: {sorted(forbidden)}"


def test_dashboard_host_has_no_static_financial_registry_import():
    imports = _imports(Path("dojoagents/dashboard/server.py"))
    assert "dojoagents.dashboard.services.financial_registry" not in imports


def test_only_formal_harness_namespace_exports_capability_contract():
    import dojoagents.harnesses as harnesses

    assert harnesses.HarnessBuilder is not None
    assert harnesses.HarnessRuntime is not None
    assert "HarnessCapabilities" in harnesses.__all__
