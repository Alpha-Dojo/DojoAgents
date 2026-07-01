from __future__ import annotations

import json
from typing import Any

from dojoagents.dashboard.services.domain_api import (
    SectorPathResolutionError,
    _looks_like_index_guess,
    build_market_overview,
    build_sector_analysis,
    build_sector_constituents_v1,
    build_sector_movers,
    build_stock_screen,
    build_sector_taxonomy_search,
    build_taxonomy_tree,
    build_ticker_financials_v1,
    build_tickers_financials_v1,
    build_ticker_news_events_v1,
    build_ticker_price_trends_v1,
    build_ticker_quote_v1,
    build_tickers_quotes_v1,
    resolve_sector_path,
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


def _list_str_arg(args: dict[str, Any], key: str) -> list[str]:
    value = args.get(key)
    if value is None:
        return []
    if isinstance(value, str):
        text = value.strip()
        return [text] if text else []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


def _service_ready(registry: FinancialDomainRegistry) -> None:
    required = ("sector_store", "stock_store", "benchmark_store")
    missing = [name for name in required if getattr(registry, name, None) is None]
    if missing:
        raise RuntimeError(f"dashboard financial registry is not ready: {', '.join(missing)}")


_SECTOR_ID_PROPERTIES = {
    "sector_path_id": {
        "type": "string",
        "description": (
            "Full taxonomy path from search_sector_taxonomy as level1_id/level2_id/level3_id "
            "(always THREE segments). scope=L2 is separate — it widens constituents, not shortens this path."
        ),
    },
    "level1_id": {
        "type": "string",
        "description": "L1 sector_id from search_sector_taxonomy (not array index).",
    },
    "level2_id": {
        "type": "string",
        "description": "L2 sector_id from search_sector_taxonomy (not array index).",
    },
    "level3_id": {
        "type": "string",
        "description": (
            "L3 sector_id from search_sector_taxonomy. May be used alone when globally unique."
        ),
    },
    "sector_name": {
        "type": "string",
        "description": "Fallback only: exact L3 label when ids are unavailable.",
    },
    "level1_name": {"type": "string", "description": "Fallback only: L1 sector label in zh or en."},
    "level2_name": {"type": "string", "description": "Fallback only: L2 sector label in zh or en."},
    "level3_name": {"type": "string", "description": "Fallback only: L3 sector label in zh or en."},
}


def _sector_path_kwargs(args: dict[str, Any]) -> dict[str, Any]:
    return {
        "sector_path_id": _str_arg(args, "sector_path_id"),
        "level1_id": _str_arg(args, "level1_id"),
        "level2_id": _str_arg(args, "level2_id"),
        "level3_id": _str_arg(args, "level3_id"),
        "sector_name": _optional_str_arg(args, "sector_name"),
        "level1_name": _optional_str_arg(args, "level1_name"),
        "level2_name": _optional_str_arg(args, "level2_name"),
        "level3_name": _optional_str_arg(args, "level3_name"),
        "market": _optional_str_arg(args, "market"),
    }


def _resolve_sector_path_or_raise(registry: FinancialDomainRegistry, args: dict[str, Any]):
    kwargs = _sector_path_kwargs(args)
    id_keys = ("sector_path_id", "level1_id", "level2_id", "level3_id")
    if not any(kwargs.get(key) for key in id_keys) and not (
        kwargs.get("sector_name") or kwargs.get("level3_name")
    ):
        raise RuntimeError(
            "sector path is required. Workflow: (1) search_sector_taxonomy with the concept keyword, "
            "(2) copy sector_path_id OR level1_id/level2_id/level3_id from best_match, "
            "(3) filter_sector_constituents / get_sector_analysis with those ids."
        )

    has_name = bool(kwargs.get("sector_name") or kwargs.get("level3_name"))
    if kwargs.get("sector_path_id"):
        try:
            return resolve_sector_path(registry, **kwargs)
        except SectorPathResolutionError as exc:
            raise RuntimeError(str(exc)) from exc

    l1 = kwargs.get("level1_id") or ""
    l2 = kwargs.get("level2_id") or ""
    l3 = kwargs.get("level3_id") or ""
    if not has_name and l1 and l2 and l3:
        store = registry.sector_store
        if store.find_resolved_path(l1, l2, l3) is None and _looks_like_index_guess(l1, l2, l3):
            raise RuntimeError(
                f"Rejected guessed sector path {l1}/{l2}/{l3}. "
                "Do NOT use array indices or trial-and-error. "
                "Call search_sector_taxonomy, then copy sector_path_id or level1_id/level2_id/level3_id "
                "from best_match. For market-wide screens use screen_market_stocks instead."
            )

    try:
        return resolve_sector_path(registry, **kwargs)
    except SectorPathResolutionError as exc:
        raise RuntimeError(str(exc)) from exc


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

    async def taxonomy_search(args: dict[str, Any]) -> dict[str, Any]:
        _service_ready(registry)
        query = _str_arg(args, "q") or _str_arg(args, "query")
        if not query:
            raise RuntimeError("q is required")
        result = build_sector_taxonomy_search(registry, query=query, limit=_int_arg(args, "limit", 10))
        return _json_content(result)

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
        path = _resolve_sector_path_or_raise(registry, args)
        result = await build_sector_analysis(
            registry,
            path,
            scope=_str_arg(args, "scope", "L3"),
        )
        return _json_content(result)

    async def sector_constituents(args: dict[str, Any]) -> dict[str, Any]:
        _service_ready(registry)
        path = _resolve_sector_path_or_raise(registry, args)
        result = await build_sector_constituents_v1(
            registry,
            level1_id=path.level1_id,
            level2_id=path.level2_id,
            level3_id=path.level3_id,
            scope=_str_arg(args, "scope", "L3"),
            market=_optional_str_arg(args, "market"),
            days=_int_arg(args, "days", 1),
        )
        return _json_content(result)

    async def ticker_quote(args: dict[str, Any]) -> dict[str, Any]:
        _service_ready(registry)
        tickers = _list_str_arg(args, "tickers")
        single = _str_arg(args, "ticker")
        if not tickers and single:
            tickers = [single]
        if not tickers:
            raise RuntimeError("ticker or tickers is required")
        market = _optional_str_arg(args, "market")
        if len(tickers) == 1:
            result = await build_ticker_quote_v1(
                registry,
                ticker=tickers[0],
                market=market,
            )
            if result is None:
                raise RuntimeError(f"quote not found for {tickers[0]}")
            return _json_content(result)
        result = await build_tickers_quotes_v1(
            registry,
            tickers=tickers,
            market=market,
        )
        return _json_content(result)

    async def ticker_financials(args: dict[str, Any]) -> dict[str, Any]:
        _service_ready(registry)
        tickers = _list_str_arg(args, "tickers")
        single = _str_arg(args, "ticker")
        if not tickers and single:
            tickers = [single]
        if not tickers:
            raise RuntimeError("ticker or tickers is required")
        market = _optional_str_arg(args, "market")
        start_date = _optional_str_arg(args, "start_date")
        end_date = _optional_str_arg(args, "end_date")
        limit = _optional_int_arg(args, "limit", 20)
        report_type = _optional_str_arg(args, "report_type")
        if len(tickers) == 1:
            result = await build_ticker_financials_v1(
                registry,
                ticker=tickers[0],
                market=market,
                start_date=start_date,
                end_date=end_date,
                limit=limit,
                report_type=report_type,
            )
            if result is None:
                raise RuntimeError(f"financials not found for {tickers[0]}")
            return _json_content(result)
        result = await build_tickers_financials_v1(
            registry,
            tickers=tickers,
            market=market,
            start_date=start_date,
            end_date=end_date,
            limit=limit,
            report_type=report_type,
        )
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
            description=(
                "Resolve ONE company name or ticker symbol to market code and bilingual name. "
                "Use ONLY when the user names a specific company. "
                "FORBIDDEN for themes/concepts (具身智能, 机器人), sector baskets, or looping famous tickers — "
                "use search_sector_taxonomy + filter_sector_constituents or screen_market_stocks instead."
            ),
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
            name="search_sector_taxonomy",
            description=(
                "Search L3 industry sectors by concept keyword (具身智能, 机器人, 半导体, robotics). "
                "CALL THIS FIRST for theme/concept stock picking. "
                "Returns sector_path_id + level1_id/level2_id/level3_id with match_score — "
                "copy ids verbatim into filter_sector_constituents / get_sector_analysis."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "q": {"type": "string", "description": "Sector keyword in zh or en"},
                    "query": {"type": "string", "description": "Alias for q"},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 25},
                },
                "required": ["q"],
            },
            handler=taxonomy_search,
        ),
        ToolSpec(
            name="get_taxonomy_tree",
            description=(
                "Return the L1-L2-L3 sector taxonomy. CALL THIS FIRST before filter_sector_constituents "
                "or get_sector_analysis. Response includes example_l3_paths and "
                "filter_sector_constituents_example — copy those ids verbatim; never use 1/2/3 indices."
            ),
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
            description=(
                "Top gaining/losing L3 sectors. Each item includes level1_id, level2_id, level3_id — "
                "copy them directly into filter_sector_constituents or get_sector_analysis."
            ),
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
            description=(
                "Full-market stock screen by market cap, PE, return, daily change. "
                "Use when there is NO matching taxonomy sector, or after sector tools fail. "
                "For concept/industry baskets prefer search_sector_taxonomy + filter_sector_constituents first."
            ),
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
            description=(
                "Sector NAV, weighted PE, and risk stats for ONE taxonomy path. "
                "Prerequisite: search_sector_taxonomy — copy sector_path_id or level1_id/level2_id/level3_id "
                "from best_match verbatim."
            ),
            parameters={
                "type": "object",
                "properties": {
                    **_SECTOR_ID_PROPERTIES,
                    "scope": {"type": "string", "enum": ["L1", "L2", "L3"]},
                },
            },
            handler=sector_analysis,
        ),
        ToolSpec(
            name="filter_sector_constituents",
            description=(
                "List quoted stocks for a taxonomy path. Prerequisite: search_sector_taxonomy — copy "
                "sector_path_id (three segments) or level1_id/level2_id/level3_id from best_match. "
                "Required: market (us|cn|hk). scope=L1|L2|L3 controls breadth (L2 = all L3 children "
                "under the same L2 branch) but ids must still be the full path from search. "
                "FORBIDDEN: two-segment paths like 1/2 or guessing ids."
            ),
            parameters={
                "type": "object",
                "properties": {
                    **_SECTOR_ID_PROPERTIES,
                    "market": {"type": "string", "enum": ["cn", "sh", "hk", "us"]},
                    "scope": {"type": "string", "enum": ["L1", "L2", "L3"]},
                    "days": {"type": "integer", "minimum": 1, "maximum": 90},
                },
            },
            handler=sector_constituents,
        ),
        ToolSpec(
            name="get_ticker_realtime_quote",
            description=(
                "Get dashboard quote payloads for one or many tickers. "
                "Prefer passing all candidate tickers in tickers (up to 50) in a single call "
                "instead of querying each ticker separately."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "ticker": {"type": "string", "description": "Single ticker symbol"},
                    "tickers": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Batch ticker symbols for candidate lists",
                    },
                    "market": {"type": "string", "enum": ["cn", "sh", "hk", "us"]},
                },
            },
            handler=ticker_quote,
        ),
        ToolSpec(
            name="get_ticker_financials",
            description=(
                "Get financial indicators and income distributions for one or many tickers. "
                "Prefer passing all candidate tickers in tickers (up to 50) in a single call "
                "instead of querying each ticker separately."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "ticker": {"type": "string", "description": "Single ticker symbol"},
                    "tickers": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Batch ticker symbols for candidate lists",
                    },
                    "market": {"type": "string", "enum": ["cn", "sh", "hk", "us"]},
                    "start_date": {"type": "string"},
                    "end_date": {"type": "string"},
                    "limit": {"type": "integer", "minimum": 1},
                    "report_type": {"type": "string"},
                },
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
