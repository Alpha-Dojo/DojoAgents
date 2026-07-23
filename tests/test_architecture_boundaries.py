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
        forbidden = {
            module
            for module in _imports(path)
            if module.startswith(
                (
                    "dojoagents.dashboard",
                    "dojoagents.quant",
                    "dojoagents.harnesses.built_in",
                )
            )
        }
        assert not forbidden, f"{path}: {sorted(forbidden)}"


def test_agent_core_does_not_import_harness_or_host_domains():
    paths = list(Path("dojoagents/agent").rglob("*.py"))
    for path in paths:
        forbidden = {
            module
            for module in _imports(path)
            if module.startswith(
                (
                    "dojoagents.dashboard",
                    "dojoagents.quant",
                    "dojoagents.harnesses.built_in",
                )
            )
        }
        assert not forbidden, f"{path}: {sorted(forbidden)}"


def test_sessions_and_core_execution_do_not_import_host_or_harness_domains():
    paths = list(Path("dojoagents/sessions").rglob("*.py")) + [
        Path("dojoagents/tools/executor.py"),
        Path("dojoagents/tools/artifacts.py"),
        Path("dojoagents/tools/code_execution_tool.py"),
        Path("dojoagents/tools/session_input_tool.py"),
    ]
    for path in paths:
        forbidden = {
            module
            for module in _imports(path)
            if module.startswith(
                (
                    "dojoagents.dashboard",
                    "dojoagents.quant",
                    "dojoagents.harnesses.built_in",
                )
            )
        }
        assert not forbidden, f"{path}: {sorted(forbidden)}"


def test_generic_task_cron_extension_and_cli_hosts_do_not_import_built_in_harnesses():
    paths = (
        list(Path("dojoagents/tasks").rglob("*.py"))
        + list(Path("dojoagents/cron").rglob("*.py"))
        + list(Path("dojoagents/dojo_extensions").rglob("*.py"))
        + list(Path("dojoagents/cli").rglob("*.py"))
    )
    for path in paths:
        forbidden = {
            module
            for module in _imports(path)
            if module.startswith(
                (
                    "dojoagents.harnesses.built_in",
                    "dojoagents.quant",
                )
            )
        }
        assert not forbidden, f"{path}: {sorted(forbidden)}"


def test_dashboard_host_does_not_import_financial_harness_or_quant():
    for path in Path("dojoagents/dashboard").rglob("*.py"):
        forbidden = {
            module
            for module in _imports(path)
            if module.startswith(
                (
                    "dojoagents.harnesses.built_in.financial",
                    "dojoagents.quant",
                )
            )
        }
        assert not forbidden, f"{path}: {sorted(forbidden)}"


def test_financial_harness_does_not_import_dashboard_implementation():
    for path in Path("dojoagents/harnesses/built_in/financial").rglob("*.py"):
        forbidden = {module for module in _imports(path) if module.startswith("dojoagents.dashboard")}
        assert not forbidden, f"{path}: {sorted(forbidden)}"


def test_dashboard_namespace_contains_only_host_owned_modules():
    expected = {
        "routers": {"__init__.py", "chat_sessions.py"},
        "schemas": {
            "__init__.py",
            "agent.py",
            "chat_sessions.py",
            "common.py",
            "session_inputs.py",
            "session_outputs.py",
        },
        "services": {
            "__init__.py",
            "chat_session_service.py",
            "session_inputs.py",
            "session_outputs.py",
        },
    }
    for directory, allowed in expected.items():
        actual = {path.name for path in (Path("dojoagents/dashboard") / directory).glob("*.py")}
        assert actual == allowed


def test_removed_financial_compatibility_paths_do_not_reappear():
    removed = (
        "dojoagents/quant",
        "dojoagents/dashboard/store_manager.py",
        "dojoagents/dashboard/tools/domain_tools.py",
        "dojoagents/dashboard/tools/portfolio_tools.py",
        "dojoagents/tasks/built_in",
        "dojoagents/tasks/pipelines",
        "dojoagents/cli/tasks.py",
        "dojoagents/cli/tasks_client.py",
        "dojoagents/cli/precompute_sector.py",
        "dojoagents/cli/precompute_sector_theme_state.py",
    )
    assert not [path for path in removed if Path(path).exists()]


def test_only_formal_harness_namespace_exports_capability_contract():
    import dojoagents.harnesses as harnesses

    assert harnesses.HarnessBuilder is not None
    assert harnesses.HarnessRuntime is not None
    assert "HarnessCapabilities" in harnesses.__all__
