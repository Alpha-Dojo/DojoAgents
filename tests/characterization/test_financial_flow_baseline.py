from __future__ import annotations

from tests.characterization.test_runtime_financial_baseline import (
    DOMAIN_TOOLS,
    PORTFOLIO_TOOLS,
)

FLOW_TOOL_REQUIREMENTS = {
    "market_overview": {"get_market_overview"},
    "sector_chain": {
        "search_sector_taxonomy",
        "get_taxonomy_tree",
        "get_sector_movers",
        "get_sector_analysis",
        "filter_sector_constituents",
    },
    "ticker_analysis": {
        "search_company_ticker",
        "get_ticker_realtime_quote",
        "get_ticker_financials",
        "get_ticker_news_and_events",
        "get_ticker_price_trends",
    },
    "portfolio_read": {"portfolio_read_list", "portfolio_read_search", "portfolio_read_detail"},
    "portfolio_build": {
        "portfolio_write_create",
        "portfolio_write_add_candidates",
        "portfolio_read_detail",
        "portfolio_eval_submit",
    },
    "portfolio_trade": {
        "portfolio_write_create_orders",
        "portfolio_write_sync_positions",
        "portfolio_read_detail",
        "portfolio_eval_submit",
    },
    "portfolio_liquidate": {
        "portfolio_write_remove_holding",
        "portfolio_read_detail",
        "portfolio_eval_submit",
    },
    "portfolio_delete": {"portfolio_write_delete"},
}


def test_every_current_financial_flow_has_registered_tool_coverage():
    available = DOMAIN_TOOLS | PORTFOLIO_TOOLS

    assert set(FLOW_TOOL_REQUIREMENTS) == {
        "market_overview",
        "sector_chain",
        "ticker_analysis",
        "portfolio_read",
        "portfolio_build",
        "portfolio_trade",
        "portfolio_liquidate",
        "portfolio_delete",
    }
    for required in FLOW_TOOL_REQUIREMENTS.values():
        assert required <= available
