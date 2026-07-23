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


def test_dashboard_core_does_not_import_financial_harness_or_quant():
    for path in Path("dojoagents/dashboard").rglob("*.py"):
        if "integrations" in path.parts:
            continue
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


def test_dashboard_owns_complete_financial_app_backend():
    required = {
        "routers": {
            "market.py",
            "sector.py",
            "ticker.py",
            "portfolio.py",
            "dojo_core.py",
        },
        "schemas": {
            "market.py",
            "sector.py",
            "portfolio.py",
            "stock.py",
        },
        "services": {
            "financial_registry.py",
            "dojo_data_gateway.py",
            "portfolio_service.py",
            "sector_store.py",
            "stock_store.py",
        },
    }
    for directory, expected in required.items():
        actual = {path.name for path in (Path("dojoagents/dashboard") / directory).glob("*.py")}
        assert expected <= actual


def test_financial_harness_contains_only_agent_runtime_capabilities():
    root = Path("dojoagents/harnesses/built_in/financial")
    forbidden_directories = ("contracts", "services", "surfaces", "data")
    assert not [name for name in forbidden_directories if (root / name).exists()]
    app_pipeline_patterns = (
        "cli_precompute_*.py",
        "precompute_sector_*.py",
        "precompute_theme_state_daily.py",
        "precompute_ticker_alpha_factors.py",
    )
    assert not [path for pattern in app_pipeline_patterns for path in (root / "pipelines").glob(pattern)]


def test_dashboard_integration_is_the_only_dashboard_financial_harness_boundary():
    root = Path("dojoagents/dashboard")
    offenders = []
    for path in root.rglob("*.py"):
        imports_financial_harness = any(module.startswith("dojoagents.harnesses.built_in.financial") for module in _imports(path))
        if imports_financial_harness and "integrations" not in path.parts:
            offenders.append(path)
    assert not offenders


def test_removed_core_financial_compatibility_paths_do_not_reappear():
    removed = (
        "dojoagents/quant",
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
