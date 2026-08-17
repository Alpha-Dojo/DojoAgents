from __future__ import annotations

from pathlib import Path

import dojoagents

from dojoagents.config.models import AgentsConfig, HarnessConfig
from dojoagents.harnesses.builder import HarnessBuilder
from dojoagents.harnesses.built_in.financial.config import FinancialHarnessConfig
from dojoagents.harnesses.built_in.financial.harness import FinancialHarness
from dojoagents.harnesses.built_in.financial.tools import FINANCIAL_TOOL_NAMES
from dojoagents.harnesses.context import HarnessBuildContext
from tests.fixtures.minimal_harness import MinimalHarness


def _context(tmp_path):
    config = AgentsConfig(harness=HarnessConfig(config={"data_root": str(tmp_path / "data"), "portfolio_data_root": str(tmp_path / "portfolios"), "refresh_enabled": False}))
    return HarnessBuildContext(config, config.harness.config, tmp_path, tmp_path, "api", None)


def test_financial_harness_declares_exact_unique_inventory(tmp_path):
    context = _context(tmp_path)
    harness = FinancialHarness(FinancialHarnessConfig.from_context(context))
    builder = HarnessBuilder(harness.descriptor)
    harness.configure(builder, context)
    capabilities = builder.build()
    names = [name for provider in capabilities.tools for name in provider.tool_names]
    assert len(names) == len(set(names))
    assert set(names) == set(FINANCIAL_TOOL_NAMES)


def test_minimal_harness_has_no_financial_tools(tmp_path):
    harness = MinimalHarness()
    builder = HarnessBuilder(harness.descriptor)
    harness.configure(builder, _context(tmp_path))
    names = {name for provider in builder.build().tools for name in provider.tool_names}
    assert names == {"echo"}
    assert names.isdisjoint(FINANCIAL_TOOL_NAMES)


def test_financial_subclass_can_replace_all_builtin_operations(tmp_path):
    class CoreOnlyFinancialHarness(FinancialHarness):
        def configure_operational_capabilities(self, builder, context):
            del builder, context

    context = _context(tmp_path)
    harness = CoreOnlyFinancialHarness(
        FinancialHarnessConfig.from_context(context),
        builtin_operations=False,
    )
    assert harness.tool_backend is None

    builder = HarnessBuilder(harness.descriptor)
    harness.configure(builder, context)
    capabilities = builder.build()

    assert not capabilities.tools
    assert not capabilities.services
    assert not capabilities.tasks
    assert not capabilities.pipelines
    assert not capabilities.presenters
    assert [spec.component_id for spec in capabilities.flow_policies] == [
        "financial.turn-scope",
        "financial.completion",
    ]
    built_in = next(spec.provider for spec in capabilities.skills if spec.component_id == "financial.skills.built-in")
    assert built_in == Path(dojoagents.__file__).resolve().parent / "skills" / "built_in"
