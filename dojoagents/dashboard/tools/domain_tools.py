from __future__ import annotations

import json
from typing import Any

from dojoagents.dashboard.services.domain_api import (
    build_market_overview,
    build_sector_analysis,
    build_sector_constituents_v1,
    build_sector_movers,
    build_stock_screen,
    build_taxonomy_tree,
    build_ticker_financials_v1,
    build_ticker_news_events_v1,
    build_ticker_price_trends_v1,
    build_ticker_quote_v1,
    resolve_sector_analysis_path,
    search_company_ticker,
)
from dojoagents.dashboard.services.financial_registry import FinancialDomainRegistry
from dojoagents.tools.registry import ToolRegistry, ToolSpec


def _jsonable(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    return value


def _json_content(payload: Any) -> dict[str, Any]:
    data = _jsonable(payload)
    return {
        "content": json.dumps(data, ensure_ascii=False, indent=2),
        "data": data,
        "metadata": {"ok": True},
    }


def _str_arg(args: dict[str, Any], key: str, default: str = "") -> str:
    value = args.get(key)
    if value is None:
        return default
    return str(value).strip()


def _optional_str_arg(args: dict[str, Any], key: str) -> str | None:
    value = _str_arg(args, key)
    return value or None


def _int_arg(args: dict[str, Any], key: str, default: int) -> int:
    value = args.get(key)
    if value is None or value == "":
        return default
    return int(value)


def _optional_int_arg(args: dict[str, Any], key: str, default: int | None = None) -> int | None:
    value = args.get(key)
    if value is None or value == "":
        return default
    return int(value)


def _optional_float_arg(args: dict[str, Any], key: str) -> float | None:
    value = args.get(key)
    if value is None or value == "":
        return None
    return float(value)


def _service_ready(registry: FinancialDomainRegistry) -> None:
    required = ("sector_store", "stock_store", "benchmark_store")
    missing = [name for name in required if getattr(registry, name, None) is None]
    if missing:
        raise RuntimeError(f"dashboard financial registry is not ready: {', '.join(missing)}")


def register_dashboard_domain_tools(
    tool_registry: ToolRegistry,
    registry: FinancialDomainRegistry,
) -> None:
    async def search_company(args: dict[str, Any]) -> dict[str, Any]:
        _service_ready(registry)
        query = _str_arg(args, "q") or _str_arg(args, "query")
        if not query:
            raise RuntimeError("q is required")
        result = await search_company_ticker(
            registry,
            q=query,
            market=_optional_str_arg(args, "market"),
            limit=_int_arg(args, "limit", 20),
        )
        return _json_content(result)

    async def taxonomy_tree(_: dict[str, Any]) -> dict[str, Any]:
        _service_ready(registry)
        return _json_content(build_taxonomy_tree(registry))

    async def market_overview(args: dict[str, Any]) -> dict[str, Any]:
        _service_ready(registry)
        result = await build_market_overview(
            registry,
            days=_int_arg(args, "days", 1),
            market=_optional_str_arg(args, "market"),
        )
        return _json_content(result)

    async def sector_movers(args: dict[str, Any]) -> dict[str, Any]:
        _service_ready(registry)
        result = await build_sector_movers(
            registry,
            days=_int_arg(args, "days", 1),
            limit=_int_arg(args, "limit", 5),
            market=_optional_str_arg(args, "market"),
            min_cap_by_market={
                key: value
                for key, value in {
                    "us": _optional_float_arg(args, "min_cap_us"),
                    "sh": _optional_float_arg(args, "min_cap_cn"),
                    "hk": _optional_float_arg(args, "min_cap_hk"),
                }.items()
                if value is not None and value > 0
            }
            or None,
        )
        return _json_content(result)

    async def stock_screen(args: dict[str, Any]) -> dict[str, Any]:
        _service_ready(registry)
        result = await build_stock_screen(
            registry,
            market=_optional_str_arg(args, "market"),
            days=_int_arg(args, "days", 0),
            min_market_cap=_optional_float_arg(args, "min_market_cap"),
            max_market_cap=_optional_float_arg(args, "max_market_cap"),
            min_return_pct=_optional_float_arg(args, "min_return_pct"),
            max_return_pct=_optional_float_arg(args, "max_return_pct"),
            min_pe=_optional_float_arg(args, "min_pe"),
            max_pe=_optional_float_arg(args, "max_pe"),
            min_change_percent=_optional_float_arg(args, "min_change_percent"),
            max_change_percent=_optional_float_arg(args, "max_change_percent"),
            sort_by=_str_arg(args, "sort_by", "market_cap"),
            sort_order=_str_arg(args, "sort_order", "desc"),
            limit=_int_arg(args, "limit", 50),
        )
        return _json_content(result)

    async def sector_analysis(args: dict[str, Any]) -> dict[str, Any]:
        _service_ready(registry)
        path = resolve_sector_analysis_path(
            registry,
            level1_id=_str_arg(args, "level1_id"),
            level2_id=_str_arg(args, "level2_id"),
            level3_id=_str_arg(args, "level3_id"),
        )
        if path is None:
            raise RuntimeError("unknown sector path")
        result = await build_sector_analysis(
            registry,
            path,
            scope=_str_arg(args, "scope", "L3"),
        )
        return _json_content(result)

    async def sector_constituents(args: dict[str, Any]) -> dict[str, Any]:
        _service_ready(registry)
        result = await build_sector_constituents_v1(
            registry,
            level1_id=_str_arg(args, "level1_id"),
            level2_id=_str_arg(args, "level2_id"),
            level3_id=_str_arg(args, "level3_id"),
            scope=_str_arg(args, "scope", "L3"),
            market=_optional_str_arg(args, "market"),
            days=_int_arg(args, "days", 1),
        )
        return _json_content(result)

    async def ticker_quote(args: dict[str, Any]) -> dict[str, Any]:
        _service_ready(registry)
        ticker = _str_arg(args, "ticker")
        result = await build_ticker_quote_v1(
            registry,
            ticker=ticker,
            market=_optional_str_arg(args, "market"),
        )
        if result is None:
            raise RuntimeError(f"quote not found for {ticker}")
        return _json_content(result)

    async def ticker_financials(args: dict[str, Any]) -> dict[str, Any]:
        _service_ready(registry)
        ticker = _str_arg(args, "ticker")
        result = await build_ticker_financials_v1(
            registry,
            ticker=ticker,
            market=_optional_str_arg(args, "market"),
            start_date=_optional_str_arg(args, "start_date"),
            end_date=_optional_str_arg(args, "end_date"),
            limit=_optional_int_arg(args, "limit", 20),
            report_type=_optional_str_arg(args, "report_type"),
        )
        if result is None:
            raise RuntimeError(f"financials not found for {ticker}")
        return _json_content(result)

    async def ticker_news_events(args: dict[str, Any]) -> dict[str, Any]:
        _service_ready(registry)
        ticker = _str_arg(args, "ticker")
        result = await build_ticker_news_events_v1(
            registry,
            ticker=ticker,
            market=_optional_str_arg(args, "market"),
            start_date=_optional_str_arg(args, "start_date"),
            end_date=_optional_str_arg(args, "end_date"),
            page_size=_optional_int_arg(args, "page_size", 20),
        )
        if result is None:
            raise RuntimeError(f"news/events not found for {ticker}")
        return _json_content(result)

    async def ticker_price_trends(args: dict[str, Any]) -> dict[str, Any]:
        _service_ready(registry)
        ticker = _str_arg(args, "ticker")
        result = await build_ticker_price_trends_v1(
            registry,
            ticker=ticker,
            market=_optional_str_arg(args, "market"),
            start_date=_optional_str_arg(args, "start_date"),
            end_date=_optional_str_arg(args, "end_date"),
            limit=_optional_int_arg(args, "limit", 252),
            kline_t=_str_arg(args, "kline_t", "1D"),
        )
        if result is None:
            raise RuntimeError(f"price trends not found for {ticker}")
        return _json_content(result)

    tool_specs = [
        ToolSpec(
            name="search_company_ticker",
            description="Resolve a company name or ticker to dashboard market codes and bilingual names.",
            parameters={
                "type": "object",
                "properties": {
                    "q": {"type": "string", "description": "Company name or ticker symbol"},
                    "query": {"type": "string", "description": "Alias for q"},
                    "market": {"type": "string", "enum": ["cn", "sh", "hk", "us"]},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 50},
                },
                "required": ["q"],
            },
            handler=search_company,
        ),
        ToolSpec(
            name="get_taxonomy_tree",
            description="Return the full L1-L2-L3 financial sector taxonomy for dashboard drill-down.",
            parameters={"type": "object", "properties": {}},
            handler=taxonomy_tree,
        ),
        ToolSpec(
            name="get_market_overview",
            description="Get benchmark performance, total market cap, weighted PE, and listed counts by market. Omit market to compare US, CN, and HK together in one response.",
            parameters={
                "type": "object",
                "properties": {
                    "days": {"type": "integer", "minimum": 1, "maximum": 90},
                    "market": {"type": "string", "enum": ["cn", "sh", "hk", "us"]},
                },
            },
            handler=market_overview,
        ),
        ToolSpec(
            name="get_sector_movers",
            description="Get top gaining and losing L3 sectors by market-cap-weighted return.",
            parameters={
                "type": "object",
                "properties": {
                    "days": {"type": "integer", "minimum": 0, "maximum": 90},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 20},
                    "market": {"type": "string", "enum": ["cn", "sh", "hk", "us"]},
                    "min_cap_us": {"type": "number", "minimum": 0},
                    "min_cap_cn": {"type": "number", "minimum": 0},
                    "min_cap_hk": {"type": "number", "minimum": 0},
                },
            },
            handler=sector_movers,
        ),
        ToolSpec(
            name="screen_market_stocks",
            description="Screen quoted stocks by market cap, return, valuation, and daily change.",
            parameters={
                "type": "object",
                "properties": {
                    "market": {"type": "string", "enum": ["cn", "sh", "hk", "us"]},
                    "days": {"type": "integer", "minimum": 0, "maximum": 90},
                    "min_market_cap": {"type": "number", "minimum": 0},
                    "max_market_cap": {"type": "number", "minimum": 0},
                    "min_return_pct": {"type": "number"},
                    "max_return_pct": {"type": "number"},
                    "min_pe": {"type": "number", "minimum": 0},
                    "max_pe": {"type": "number", "minimum": 0},
                    "min_change_percent": {"type": "number"},
                    "max_change_percent": {"type": "number"},
                    "sort_by": {"type": "string", "enum": ["market_cap", "return_pct", "change_percent", "pe"]},
                    "sort_order": {"type": "string", "enum": ["asc", "desc"]},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 100},
                },
            },
            handler=stock_screen,
        ),
        ToolSpec(
            name="get_sector_analysis",
            description="Analyze one sector path with market cap, weighted PE, NAV curves, and risk stats.",
            parameters={
                "type": "object",
                "properties": {
                    "level1_id": {"type": "string"},
                    "level2_id": {"type": "string"},
                    "level3_id": {"type": "string"},
                    "scope": {"type": "string", "enum": ["L1", "L2", "L3"]},
                },
                "required": ["level1_id", "level2_id", "level3_id"],
            },
            handler=sector_analysis,
        ),
        ToolSpec(
            name="filter_sector_constituents",
            description="List constituents in a sector with quote, valuation, and performance metrics.",
            parameters={
                "type": "object",
                "properties": {
                    "level1_id": {"type": "string"},
                    "level2_id": {"type": "string"},
                    "level3_id": {"type": "string"},
                    "market": {"type": "string", "enum": ["cn", "sh", "hk", "us"]},
                    "scope": {"type": "string", "enum": ["L1", "L2", "L3"]},
                    "days": {"type": "integer", "minimum": 1, "maximum": 90},
                },
                "required": ["level1_id", "level2_id", "level3_id"],
            },
            handler=sector_constituents,
        ),
        ToolSpec(
            name="get_ticker_realtime_quote",
            description="Get a dashboard quote card payload for one ticker.",
            parameters={
                "type": "object",
                "properties": {
                    "ticker": {"type": "string"},
                    "market": {"type": "string", "enum": ["cn", "sh", "hk", "us"]},
                },
                "required": ["ticker"],
            },
            handler=ticker_quote,
        ),
        ToolSpec(
            name="get_ticker_financials",
            description="Get financial indicators and income distributions for one ticker.",
            parameters={
                "type": "object",
                "properties": {
                    "ticker": {"type": "string"},
                    "market": {"type": "string", "enum": ["cn", "sh", "hk", "us"]},
                    "start_date": {"type": "string"},
                    "end_date": {"type": "string"},
                    "limit": {"type": "integer", "minimum": 1},
                    "report_type": {"type": "string"},
                },
                "required": ["ticker"],
            },
            handler=ticker_financials,
        ),
        ToolSpec(
            name="get_ticker_news_and_events",
            description="Get recent news and corporate events for one ticker.",
            parameters={
                "type": "object",
                "properties": {
                    "ticker": {"type": "string"},
                    "market": {"type": "string", "enum": ["cn", "sh", "hk", "us"]},
                    "start_date": {"type": "string"},
                    "end_date": {"type": "string"},
                    "page_size": {"type": "integer", "minimum": 1},
                },
                "required": ["ticker"],
            },
            handler=ticker_news_events,
        ),
        ToolSpec(
            name="get_ticker_price_trends",
            description="Get ticker kline price trends and PE-band context for charting.",
            parameters={
                "type": "object",
                "properties": {
                    "ticker": {"type": "string"},
                    "market": {"type": "string", "enum": ["cn", "sh", "hk", "us"]},
                    "start_date": {"type": "string"},
                    "end_date": {"type": "string"},
                    "limit": {"type": "integer", "minimum": 1},
                    "kline_t": {"type": "string"},
                },
                "required": ["ticker"],
            },
            handler=ticker_price_trends,
        ),
    ]

    for spec in tool_specs:
        tool_registry.register(spec)
