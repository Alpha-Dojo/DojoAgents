from __future__ import annotations

from types import SimpleNamespace

import pytest

from dojoagents.harnesses.built_in.financial.tools.domain_runtime import (
    register_dashboard_domain_tools,
)
from dojoagents.harnesses.built_in.financial.tools.portfolio_runtime import (
    register_dashboard_portfolio_tools,
)
from dojoagents.harnesses.built_in.financial.tools import get_domain_tool_specs, get_portfolio_tool_specs
from dojoagents.tools.registry import ToolRegistry


def _compat_specs(register, registry):
    tools = ToolRegistry()
    register(tools, registry)
    return {spec.name: spec for spec in tools.all()}


def test_bound_domain_provider_preserves_public_schemas():
    financial_registry = SimpleNamespace()
    actual = {spec.name: spec for spec in get_domain_tool_specs(SimpleNamespace(registry=financial_registry))}
    expected = _compat_specs(register_dashboard_domain_tools, financial_registry)
    assert {name: spec.schema() for name, spec in actual.items()} == {name: spec.schema() for name, spec in expected.items()}


def test_bound_portfolio_provider_preserves_aliases_and_schemas():
    financial_registry = SimpleNamespace()
    actual = {spec.name: spec for spec in get_portfolio_tool_specs(SimpleNamespace(registry=financial_registry))}
    expected = _compat_specs(register_dashboard_portfolio_tools, financial_registry)
    assert {name: spec.schema() for name, spec in actual.items()} == {name: spec.schema() for name, spec in expected.items()}
    assert {"portfolio_write_add_holding", "portfolio_write_add_holdings"} <= actual.keys()


@pytest.mark.asyncio
async def test_provider_handler_failure_stays_inside_executor_boundary():
    from dojoagents.agent.models import ToolCall
    from dojoagents.tools.executor import ToolExecutor
    from dojoagents.tools.sandbox import SandboxPolicy

    tools = ToolRegistry()
    for spec in get_domain_tool_specs(SimpleNamespace(registry=SimpleNamespace())):
        tools.register(spec)
    result = await ToolExecutor(tools, SandboxPolicy(timeout_seconds=1), presenter_registry=None).execute_one(ToolCall("c1", "search_company_ticker", {"q": "Apple"}))
    assert result.ok is False
    assert "not ready" in result.error
