from __future__ import annotations

from pathlib import Path

import pytest

from dojoagents.config.models import AgentsConfig, HarnessConfig
from dojoagents.harnesses.builder import HarnessBuilder
from dojoagents.harnesses.context import HarnessBuildContext
from dojoagents.harnesses.errors import CapabilityConflictError, HarnessLoadError
from dojoagents.harnesses.loader import HarnessLoader
from dojoagents.harnesses.schema import load_manifest


def _context(tmp_path, harness):
    config = AgentsConfig(harness=harness)
    return HarnessBuildContext(config, harness.config, tmp_path, tmp_path, "test", None)


def _capabilities(loaded, context):
    builder = HarnessBuilder(loaded.harness.descriptor)
    loaded.harness.configure(builder, context)
    return builder.build()


def test_declarative_financial_manifest_matches_python_graph(tmp_path):
    manifest = Path("tests/fixtures/harnesses/financial.yaml").resolve()
    declarative_config = HarnessConfig(id="financial", factory=None, manifest=str(manifest), config={"refresh_enabled": False})
    python_config = HarnessConfig(id="financial", factory="dojoagents.harnesses.built_in.financial:create_harness", config={"refresh_enabled": False})
    declarative_context = _context(tmp_path, declarative_config)
    python_context = _context(tmp_path, python_config)
    declarative = _capabilities(HarnessLoader().load(declarative_config, context=declarative_context), declarative_context)
    python = _capabilities(HarnessLoader().load(python_config, context=python_context), python_context)

    for field in ("tools", "prompts", "flow_policies", "tool_authorizers", "tool_transformers", "presenters", "tasks", "pipelines", "services", "surfaces"):
        assert [item.component_id for item in getattr(declarative, field)] == [item.component_id for item in getattr(python, field)]
    assert [name for spec in declarative.tools for name in spec.tool_names] == [name for spec in python.tools for name in spec.tool_names]


def test_manifest_rejects_unknown_fields_path_escape_and_bad_factory(tmp_path):
    base = """apiVersion: dojoagents/v1alpha1\nkind: Harness\nmetadata: {id: x, version: 1.0.0, display_name: X}\n"""
    unknown = tmp_path / "unknown.yaml"
    unknown.write_text(base + "surprise: true\n", encoding="utf-8")
    with pytest.raises(HarnessLoadError, match="unknown fields"):
        load_manifest(unknown)

    escape = tmp_path / "escape.yaml"
    escape.write_text(base + "components:\n  prompts:\n    - {id: p, path: ../secret}\n", encoding="utf-8")
    with pytest.raises(HarnessLoadError, match="escapes"):
        load_manifest(escape)

    invalid = tmp_path / "invalid.yaml"
    invalid.write_text(base + "implementation: {factory: 'os.system rm -rf'}\n", encoding="utf-8")
    with pytest.raises(HarnessLoadError, match="module:attribute"):
        load_manifest(invalid)


def test_manifest_rejects_duplicate_ids_missing_dependencies_and_factory_plus_manifest(tmp_path):
    duplicate = tmp_path / "duplicate.yaml"
    duplicate.write_text(
        """apiVersion: dojoagents/v1alpha1
kind: Harness
metadata: {id: x, version: 1.0.0, display_name: X}
components:
  prompts:
    - {id: same, value: one}
    - {id: same, value: two}
""",
        encoding="utf-8",
    )
    with pytest.raises(HarnessLoadError, match="duplicate"):
        load_manifest(duplicate)

    missing = tmp_path / "missing.yaml"
    missing.write_text(
        """apiVersion: dojoagents/v1alpha1
kind: Harness
metadata: {id: x, version: 1.0.0, display_name: X}
components:
  prompts:
    - {id: p, value: prompt, dependencies: [absent]}
""",
        encoding="utf-8",
    )
    config = HarnessConfig(id="x", factory=None, manifest=str(missing))
    context = _context(tmp_path, config)
    loaded = HarnessLoader().load(config, context=context)
    builder = HarnessBuilder(loaded.harness.descriptor)
    loaded.harness.configure(builder, context)
    with pytest.raises(CapabilityConflictError, match="missing component"):
        builder.build()

    with pytest.raises(HarnessLoadError, match="mutually exclusive"):
        HarnessLoader().load(HarnessConfig(id="x", factory="a:b", manifest=str(missing)), context=context)
