"""Financial domain ToolSpec provider."""

from __future__ import annotations

from typing import Any

from dojoagents.tools.registry import ToolSpec
from .backend_delegation import get_backend_tool_specs

DOMAIN_TOOL_NAMES = (
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
)


def get_domain_tool_specs(backend: Any) -> list[ToolSpec]:
    return get_backend_tool_specs(backend, DOMAIN_TOOL_NAMES)


__all__ = ["DOMAIN_TOOL_NAMES", "get_domain_tool_specs"]
