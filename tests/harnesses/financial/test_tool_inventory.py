from __future__ import annotations

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
