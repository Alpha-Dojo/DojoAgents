from __future__ import annotations

from unittest.mock import MagicMock

from dojoagents.agent.runtime import Runtime
from dojoagents.config.models import AgentsConfig
from dojoagents.dashboard.integrations.financial_domain_tools import (
    register_dashboard_domain_tools,
)
from dojoagents.dashboard.integrations.financial_portfolio_tools import (
    register_dashboard_portfolio_tools,
)
from tests.test_runtime_multi_agent_plan import _make_store

BASE_RUNTIME_TOOLS = {
    "agent_viz_build",
    "agent_viz_kinds",
    "execute_code",
    "read_session_input",
    "read_session_output",
    "terminal",
    "tools_list",
    "web_extract",
    "web_search",
    "write_session_file",
}

DOMAIN_TOOLS = {
    "search_company_ticker",
    "search_sector_taxonomy",
    "get_taxonomy_tree",
    "get_market_overview",
    "get_sector_movers",
    "screen_market_stocks",
    "get_sector_analysis",
    "filter_sector_constituents",
    "get_ticker_realtime_quote",
    "get_ticker_financials",
    "get_ticker_news_and_events",
    "get_ticker_price_trends",
}

PORTFOLIO_TOOLS = {
    "portfolio_read_list",
    "portfolio_read_search",
    "portfolio_read_detail",
    "portfolio_eval_submit",
    "portfolio_write_create",
    "portfolio_write_rename",
    "portfolio_write_delete",
    "portfolio_write_add_candidate",
    "portfolio_write_add_candidates",
    "portfolio_write_add_holding",
    "portfolio_write_add_holdings",
    "portfolio_write_create_order",
    "portfolio_write_create_orders",
    "portfolio_write_sync_positions",
    "portfolio_write_remove_holding",
    "portfolio_write_remove_candidates",
    "portfolio_write_auto_allocate",
}


def test_current_runtime_and_dashboard_financial_inventory_is_frozen():
    runtime = Runtime.from_config_store(_make_store(AgentsConfig()))
    registry = runtime.agent.tool_executor.registry

    assert BASE_RUNTIME_TOOLS <= {spec.name for spec in registry.all()}
    assert [type(item).__name__ for item in runtime.agent.task_harnesses] == [
        "PortfolioTaskHarness",
        "ToolOrchestratedHarness",
        "ArtifactSynthesisHarness",
    ]

    financial_registry = MagicMock()
    register_dashboard_domain_tools(registry, financial_registry)
    register_dashboard_portfolio_tools(registry, financial_registry)

    names = {spec.name for spec in registry.all()}
    assert DOMAIN_TOOLS <= names
    assert PORTFOLIO_TOOLS <= names
