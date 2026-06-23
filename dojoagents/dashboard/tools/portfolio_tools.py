from __future__ import annotations

import json
from typing import Any

from dojoagents.dashboard.schemas.portfolio import (
    AddPortfolioHoldingRequest,
    AutoAllocateRequest,
    CreatePortfolioRequest,
    RemovePortfolioHoldingRequest,
    UpdatePortfolioRequest,
)
from dojoagents.dashboard.services.financial_registry import FinancialDomainRegistry
from dojoagents.tools.registry import ToolRegistry, ToolSpec


def _normalize_market(market: str | None) -> str | None:
    if market is None:
        return None
    normalized = market.strip().lower()
    if normalized == "cn":
        return "sh"
    return normalized or None


def _service_or_raise(registry: FinancialDomainRegistry):
    service = registry.portfolio_service
    if service is None:
        raise RuntimeError("portfolio service is not ready")
    return service


def _json_content(payload: Any) -> dict[str, Any]:
    return {
        "content": json.dumps(payload, ensure_ascii=False, indent=2),
        "metadata": {"ok": True},
    }


def register_dashboard_portfolio_tools(
    tool_registry: ToolRegistry,
    registry: FinancialDomainRegistry,
) -> None:
    async def list_portfolios(_: dict[str, Any]) -> dict[str, Any]:
        rows = await _service_or_raise(registry).list_summaries()
        return _json_content([row.model_dump() for row in rows])

    async def search_portfolios(args: dict[str, Any]) -> dict[str, Any]:
        query = str(args.get("query") or args.get("q") or "").strip()
        result = await _service_or_raise(registry).search(query)
        return _json_content(result.model_dump())

    async def get_portfolio_detail(args: dict[str, Any]) -> dict[str, Any]:
        portfolio_id = str(args.get("portfolio_id") or args.get("id") or "").strip()
        include_performance = bool(args.get("include_performance", True))
        detail = await _service_or_raise(registry).get_detail(
            portfolio_id,
            include_performance=include_performance,
        )
        if detail is None:
            raise RuntimeError("portfolio not found")
        return _json_content(detail.model_dump())

    async def create_portfolio(args: dict[str, Any]) -> dict[str, Any]:
        name = str(args.get("name") or "").strip()
        detail = await _service_or_raise(registry).create(CreatePortfolioRequest(name=name))
        return _json_content(detail.model_dump())

    async def rename_portfolio(args: dict[str, Any]) -> dict[str, Any]:
        portfolio_id = str(args.get("portfolio_id") or "").strip()
        name = str(args.get("name") or "").strip()
        detail = await _service_or_raise(registry).update(
            portfolio_id,
            UpdatePortfolioRequest(name=name),
        )
        if detail is None:
            raise RuntimeError("portfolio not found")
        return _json_content(detail.model_dump())

    async def delete_portfolio(args: dict[str, Any]) -> dict[str, Any]:
        portfolio_id = str(args.get("portfolio_id") or "").strip()
        ok = await _service_or_raise(registry).delete(portfolio_id)
        if not ok:
            raise RuntimeError("portfolio not found")
        return _json_content({"ok": True, "portfolio_id": portfolio_id})

    async def add_holding(args: dict[str, Any]) -> dict[str, Any]:
        portfolio_id = str(args.get("portfolio_id") or "").strip()
        body = AddPortfolioHoldingRequest(
            ticker=str(args.get("ticker") or "").strip(),
            market=_normalize_market(args.get("market")),
            shares=float(args["shares"]) if args.get("shares") is not None else None,
        )
        detail = await _service_or_raise(registry).add_holding(portfolio_id, body)
        if detail is None:
            raise RuntimeError("portfolio or ticker not found")
        return _json_content(detail.model_dump())

    async def remove_holding(args: dict[str, Any]) -> dict[str, Any]:
        portfolio_id = str(args.get("portfolio_id") or "").strip()
        body = RemovePortfolioHoldingRequest(
            ticker=str(args.get("ticker") or "").strip(),
            market=_normalize_market(args.get("market")),
        )
        detail = await _service_or_raise(registry).remove_holding(portfolio_id, body)
        if detail is None:
            raise RuntimeError("portfolio or holding not found")
        return _json_content(detail.model_dump())

    async def auto_allocate(args: dict[str, Any]) -> dict[str, Any]:
        portfolio_id = str(args.get("portfolio_id") or "").strip()
        body = AutoAllocateRequest(market=_normalize_market(args.get("market")))
        detail = await _service_or_raise(registry).auto_allocate(portfolio_id, body)
        if detail is None:
            raise RuntimeError("portfolio not found")
        return _json_content(detail.model_dump())

    tool_specs = [
        ToolSpec(
            name="portfolio_read_list",
            description="List saved portfolios in the financial dashboard.",
            parameters={"type": "object", "properties": {}},
            handler=list_portfolios,
        ),
        ToolSpec(
            name="portfolio_read_search",
            description="Search portfolios by portfolio name or holding ticker/name.",
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                },
                "required": ["query"],
            },
            handler=search_portfolios,
        ),
        ToolSpec(
            name="portfolio_read_detail",
            description="Fetch one portfolio detail with holdings and optional performance.",
            parameters={
                "type": "object",
                "properties": {
                    "portfolio_id": {"type": "string"},
                    "include_performance": {"type": "boolean"},
                },
                "required": ["portfolio_id"],
            },
            handler=get_portfolio_detail,
        ),
        ToolSpec(
            name="portfolio_write_create",
            description="Create a new portfolio.",
            parameters={
                "type": "object",
                "properties": {"name": {"type": "string"}},
                "required": ["name"],
            },
            handler=create_portfolio,
        ),
        ToolSpec(
            name="portfolio_write_rename",
            description="Rename an existing portfolio.",
            parameters={
                "type": "object",
                "properties": {
                    "portfolio_id": {"type": "string"},
                    "name": {"type": "string"},
                },
                "required": ["portfolio_id", "name"],
            },
            handler=rename_portfolio,
        ),
        ToolSpec(
            name="portfolio_write_delete",
            description="Delete an existing portfolio.",
            parameters={
                "type": "object",
                "properties": {
                    "portfolio_id": {"type": "string"},
                },
                "required": ["portfolio_id"],
            },
            handler=delete_portfolio,
        ),
        ToolSpec(
            name="portfolio_write_add_holding",
            description="Add one holding into a portfolio.",
            parameters={
                "type": "object",
                "properties": {
                    "portfolio_id": {"type": "string"},
                    "ticker": {"type": "string"},
                    "market": {"type": "string"},
                    "shares": {"type": "number"},
                },
                "required": ["portfolio_id", "ticker"],
            },
            handler=add_holding,
        ),
        ToolSpec(
            name="portfolio_write_remove_holding",
            description="Remove one holding from a portfolio.",
            parameters={
                "type": "object",
                "properties": {
                    "portfolio_id": {"type": "string"},
                    "ticker": {"type": "string"},
                    "market": {"type": "string"},
                },
                "required": ["portfolio_id", "ticker"],
            },
            handler=remove_holding,
        ),
        ToolSpec(
            name="portfolio_write_auto_allocate",
            description="Auto allocate a portfolio by market-cap weighting.",
            parameters={
                "type": "object",
                "properties": {
                    "portfolio_id": {"type": "string"},
                    "market": {"type": "string"},
                },
                "required": ["portfolio_id"],
            },
            handler=auto_allocate,
        ),
    ]

    for spec in tool_specs:
        tool_registry.register(spec)
