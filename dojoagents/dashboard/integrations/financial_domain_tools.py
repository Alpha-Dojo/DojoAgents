"""Financial domain ToolSpecs backed by the Harness service container."""

from __future__ import annotations

import json
from typing import Any

from dojoagents.dashboard.services.attribution_factor_service import (
    build_sector_attribution_factors,
)
from dojoagents.dashboard.services.domain_api import (
    SECTOR_PATH_INVALID_FORMAT,
    SECTOR_PATH_REJECTED_INDEX_GUESS,
    SECTOR_PATH_UNKNOWN,
    SectorPathResolutionError,
    _format_sector_path_suggestions,
    _looks_like_index_guess,
    build_market_overview,
    build_sector_constituents_v1,
    build_sector_movers,
    build_stock_screen,
    build_sector_taxonomy_search,
    build_taxonomy_l3_catalog_for_agent,
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
from dojoagents.dashboard.services.sector_movers_ranking import (
    DEFAULT_SECTOR_MOVERS_MIN_TOTAL_MARKET_CAP,
)
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


def _resolve_sector_movers_min_cap_by_market(args: dict[str, Any]) -> dict[str, float] | None:
    """Omit → UI default 200亿; explicit 0 → no floor; >0 → that floor."""
    resolved: dict[str, float] = {}
    for arg_key, market in (("min_cap_us", "us"), ("min_cap_cn", "sh"), ("min_cap_hk", "hk")):
        if arg_key not in args or args[arg_key] is None or args[arg_key] == "":
            resolved[market] = DEFAULT_SECTOR_MOVERS_MIN_TOTAL_MARKET_CAP
            continue
        value = float(args[arg_key])
        if value > 0:
            resolved[market] = value
    return resolved or None


def _resolve_price_window_args(
    args: dict[str, Any],
) -> tuple[str | None, str | None, int | None]:
    start_date = _optional_str_arg(args, "start_date") or _optional_str_arg(args, "start_time")
    end_date = _optional_str_arg(args, "end_date") or _optional_str_arg(args, "end_time")
    return start_date, end_date, _optional_int_arg(args, "limit")


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
        "description": ("L3 sector_id from search_sector_taxonomy. May be used alone when globally unique."),
    },
    "sector_name": {
        "type": "string",
        "description": "Fallback only: exact L3 label (zh or en) when ids are unavailable.",
    },
}


def _sector_path_kwargs(args: dict[str, Any]) -> dict[str, Any]:
    return {
        "sector_path_id": _str_arg(args, "sector_path_id"),
        "level1_id": _str_arg(args, "level1_id"),
        "level2_id": _str_arg(args, "level2_id"),
        "level3_id": _str_arg(args, "level3_id"),
        "sector_name": _optional_str_arg(args, "sector_name"),
        "market": _optional_str_arg(args, "market"),
    }


_SECTOR_PATH_AGENT_HINTS: dict[str, str] = {
    SECTOR_PATH_INVALID_FORMAT: (
        "Copy a full three-segment sector_path_id (or level1_id/level2_id/level3_id) from "
        "search_sector_taxonomy / get_taxonomy_tree. scope=L2 only widens constituents — "
        "it does not shorten the path to two segments."
    ),
    SECTOR_PATH_REJECTED_INDEX_GUESS: (
        "Do NOT invent sector ids. Call search_sector_taxonomy, then copy sector_path_id "
        "or level1_id/level2_id/level3_id verbatim from best_match (when present) or items. "
        "For market-wide screens use screen_market_stocks instead."
    ),
    SECTOR_PATH_UNKNOWN: (
        "Call search_sector_taxonomy with the concept keyword, pick best_match when confident "
        "otherwise choose from items by name, then pass sector_path_id or level ids verbatim."
    ),
}


def _agent_message_for_sector_path_error(exc: SectorPathResolutionError) -> str:
    """Map typed domain path errors to agent-facing tool guidance."""
    message = str(exc)
    hint = _SECTOR_PATH_AGENT_HINTS.get(getattr(exc, "code", ""), "")
    if hint and hint not in message:
        message = f"{message} {hint}".strip()
    if exc.suggestions and "Did you mean:" not in message:
        message += " Did you mean: " + _format_sector_path_suggestions(exc.suggestions) + "?"
    return message


def _resolve_sector_path_or_raise(registry: FinancialDomainRegistry, args: dict[str, Any]):
    kwargs = _sector_path_kwargs(args)
    id_keys = ("sector_path_id", "level1_id", "level2_id", "level3_id")
    if not any(kwargs.get(key) for key in id_keys) and not kwargs.get("sector_name"):
        raise RuntimeError(
            "sector path is required. Workflow: (1) search_sector_taxonomy with the concept keyword, "
            "(2) copy sector_path_id OR level1_id/level2_id/level3_id from best_match when present, "
            "else from items by name, "
            "(3) filter_sector_constituents with those ids."
        )

    has_name = bool(kwargs.get("sector_name"))
    if kwargs.get("sector_path_id"):
        try:
            return resolve_sector_path(registry, **kwargs)
        except SectorPathResolutionError as exc:
            raise RuntimeError(_agent_message_for_sector_path_error(exc)) from exc

    l1 = kwargs.get("level1_id") or ""
    l2 = kwargs.get("level2_id") or ""
    l3 = kwargs.get("level3_id") or ""
    if not has_name and l1 and l2 and l3:
        store = registry.sector_store
        if store.find_resolved_path(l1, l2, l3) is None and _looks_like_index_guess(l1, l2, l3):
            raise RuntimeError(
                f"Rejected guessed sector path {l1}/{l2}/{l3}. "
                + _SECTOR_PATH_AGENT_HINTS[SECTOR_PATH_REJECTED_INDEX_GUESS]
            )

    try:
        return resolve_sector_path(registry, **kwargs)
    except SectorPathResolutionError as exc:
        raise RuntimeError(_agent_message_for_sector_path_error(exc)) from exc


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

    async def taxonomy_tree(args: dict[str, Any]) -> dict[str, Any]:
        _service_ready(registry)
        locale = _str_arg(args, "locale", "zh")
        if locale not in {"zh", "en"}:
            raise RuntimeError("locale must be zh or en")
        return _json_content(build_taxonomy_l3_catalog_for_agent(registry, locale=locale))

    async def taxonomy_search(args: dict[str, Any]) -> dict[str, Any]:
        _service_ready(registry)
        query = _str_arg(args, "q") or _str_arg(args, "query")
        sector_path_id = _str_arg(args, "sector_path_id")
        if not sector_path_id and not query:
            raise RuntimeError("q or sector_path_id is required")
        try:
            result = build_sector_taxonomy_search(
                registry,
                query=query,
                limit=_int_arg(args, "limit", 10),
                sector_path_id=sector_path_id,
            )
        except SectorPathResolutionError as exc:
            raise RuntimeError(_agent_message_for_sector_path_error(exc)) from exc
        except ValueError as exc:
            raise RuntimeError(str(exc)) from exc
        return _json_content(result)

    async def market_overview(args: dict[str, Any]) -> dict[str, Any]:
        _service_ready(registry)
        result = await build_market_overview(
            registry,
            days=_int_arg(args, "days", 1),
            market=_optional_str_arg(args, "market"),
            start_date=_optional_str_arg(args, "start_date") or _optional_str_arg(args, "start_time"),
            end_date=_optional_str_arg(args, "end_date") or _optional_str_arg(args, "end_time"),
        )
        return _json_content(result)

    async def sector_movers(args: dict[str, Any]) -> dict[str, Any]:
        _service_ready(registry)
        result = await build_sector_movers(
            registry,
            days=_int_arg(args, "days", 1),
            limit=_int_arg(args, "limit", 5),
            market=_optional_str_arg(args, "market"),
            min_cap_by_market=_resolve_sector_movers_min_cap_by_market(args),
            start_date=_optional_str_arg(args, "start_date") or _optional_str_arg(args, "start_time"),
            end_date=_optional_str_arg(args, "end_date") or _optional_str_arg(args, "end_time"),
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
            start_date=_optional_str_arg(args, "start_date") or _optional_str_arg(args, "start_time"),
            end_date=_optional_str_arg(args, "end_date") or _optional_str_arg(args, "end_time"),
        )
        return _json_content(result)

    async def sector_attribution_factors(args: dict[str, Any]) -> dict[str, Any]:
        _service_ready(registry)
        client = registry.client
        if client is None:
            raise RuntimeError("Dojo client is not initialized")
        market = _str_arg(args, "market")
        if not market:
            raise RuntimeError("market is required")
        start_date = _optional_str_arg(args, "start_date") or _optional_str_arg(args, "start_time")
        end_date = _optional_str_arg(args, "end_date") or _optional_str_arg(args, "end_time")
        if not start_date or not end_date:
            raise RuntimeError("start_date and end_date are required")
        sector = _str_arg(args, "sector_id") or _str_arg(args, "sector_path_id")
        if not sector:
            level1_id = _str_arg(args, "level1_id")
            level2_id = _str_arg(args, "level2_id")
            level3_id = _str_arg(args, "level3_id")
            if level1_id and level2_id and level3_id:
                sector = f"{level1_id}/{level2_id}/{level3_id}"
            else:
                raise RuntimeError("sector_id or level1_id/level2_id/level3_id is required")
        locale = _str_arg(args, "locale", "zh")
        if locale not in {"zh", "en"}:
            raise RuntimeError("locale must be zh or en")
        result = await build_sector_attribution_factors(
            client,
            market=market,
            sector_id=sector,
            start_date=start_date,
            end_date=end_date,
            locale=locale,  # type: ignore[arg-type]
            limit=_optional_int_arg(args, "limit"),
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
        start_date, end_date, limit = _resolve_price_window_args(args)
        result = await build_ticker_price_trends_v1(
            registry,
            ticker=ticker,
            market=_optional_str_arg(args, "market"),
            start_date=start_date,
            end_date=end_date,
            limit=limit,
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
                "Resolve L3 industry sectors. "
                "Pass sector_path_id for exact path lookup (returns names/breadcrumb; ignores q). "
                "Or pass q/query keyword (具身智能, 半导体, robotics) for ranked text search. "
                "Returns items (ranked) + best_match only when high-confidence; "
                "if best_match is null or ambiguous=true, pick from items by name. "
                "Copy sector_path_id / level ids verbatim — never invent ids."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "q": {"type": "string", "description": "Sector keyword in zh or en"},
                    "query": {"type": "string", "description": "Alias for q"},
                    "sector_path_id": {
                        "type": "string",
                        "description": "Exact path level1_id/level2_id/level3_id — skips text search",
                    },
                    "limit": {"type": "integer", "minimum": 1, "maximum": 25},
                },
            },
            handler=taxonomy_search,
        ),
        ToolSpec(
            name="get_taxonomy_tree",
            description=(
                "Return a flat L3 sector catalog for agent use: each item has sector_path_id "
                "(opaque L1/L2/L3 like 153/160/161), monolingual name, and full description. "
                "Pass locale=zh|en (default zh). Copy sector_path_id verbatim into downstream "
                "sector tools; never treat list indices as sector ids. Prefer "
                "search_sector_taxonomy for keyword lookup."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "locale": {
                        "type": "string",
                        "enum": ["zh", "en"],
                        "description": "Language for name and description (default zh).",
                    },
                },
            },
            handler=taxonomy_tree,
        ),
        ToolSpec(
            name="get_market_overview",
            description=(
                "Cross-market snapshot: listed counts, total market cap, weighted PE (current snapshot), "
                "and benchmark index cards with window-scoped change% plus clipped klines. "
                "Omit `market` to fetch US, CN, and HK together in one call. "
                "Window — pick ONE mode: "
                "(A) `days` = latest N trading days (default 1, max 90); "
                "(B) `start_date` + `end_date` (YYYY-MM-DD, both required, max 126 calendar days) — "
                "when both dates are set, `days` is ignored. "
                "Response includes `window_mode` (`days`|`date_range`), `window_start`/`window_end` "
                "(actual first/last trade dates in range), and `as_of`. "
                "Benchmark `change_percent` is total return over the window; klines are clipped to it. "
                "`markets.*` cap/PE/count fields are current snapshot — NOT window return."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "days": {
                        "type": "integer",
                        "minimum": 0,
                        "maximum": 90,
                        "description": ("Latest N trading days for benchmark window (default 1). " "Ignored when start_date and end_date are both set."),
                    },
                    "start_date": {
                        "type": "string",
                        "description": ("Window start YYYY-MM-DD; must pair with end_date. " "Overrides days when both dates are provided."),
                    },
                    "end_date": {
                        "type": "string",
                        "description": ("Window end YYYY-MM-DD; must pair with start_date. " "Span (inclusive) must be ≤126 calendar days."),
                    },
                    "market": {
                        "type": "string",
                        "enum": ["cn", "hk", "us"],
                        "description": "Optional single-market filter. Omit for US + CN + HK in one response.",
                    },
                },
            },
            handler=market_overview,
        ),
        ToolSpec(
            name="get_sector_movers",
            description=(
                "Ranked top gaining/losing L3 sectors by weighted sector return over a window. "
                "Each item includes level1_id, level2_id, level3_id — copy verbatim into "
                "filter_sector_constituents. "
                "Ranking excludes sectors with member_count<5 (eligible constituents above ~10亿 "
                "ticker floor; basket too small). "
                "Window — pick ONE mode: "
                "(A) `days` = latest N trading days (default 1, max 90); "
                "(B) `start_date` + `end_date` (YYYY-MM-DD, both required, max 126 calendar days) — "
                "dates override days. "
                "Sector `change_percent` is total return from first to last trade date in the window "
                "(from precomputed daily sector returns). "
                "Response: `window_mode`, `window_start`, `window_end`, and "
                "`markets.{market}.gainers[]` / `losers[]` with change_percent, member_count, taxonomy ids. "
                "Default per-market min total sector cap is 200亿 (2e10), matching the Market UI; "
                "override with min_cap_us / min_cap_cn (maps to sh) / min_cap_hk, or pass 0 to disable."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "days": {
                        "type": "integer",
                        "minimum": 0,
                        "maximum": 90,
                        "description": ("Latest N trading days (default 1). Ignored when start_date+end_date are set."),
                    },
                    "start_date": {
                        "type": "string",
                        "description": "Window start YYYY-MM-DD; requires end_date; overrides days.",
                    },
                    "end_date": {
                        "type": "string",
                        "description": "Window end YYYY-MM-DD; requires start_date; max 126 calendar-day span.",
                    },
                    "limit": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 20,
                        "description": "Max gainers and max losers per market (default 5).",
                    },
                    "market": {
                        "type": "string",
                        "enum": ["cn", "sh", "hk", "us"],
                        "description": "Optional single-market filter. Omit for sh + hk + us.",
                    },
                    "min_cap_us": {
                        "type": "number",
                        "minimum": 0,
                        "description": ("Min total sector market cap (USD) for US ranking. " "Default 2e10 (200亿) when omitted; 0 disables the floor."),
                    },
                    "min_cap_cn": {
                        "type": "number",
                        "minimum": 0,
                        "description": ("Min total sector market cap (CNY) for CN/sh ranking. " "Default 2e10 (200亿) when omitted; 0 disables the floor."),
                    },
                    "min_cap_hk": {
                        "type": "number",
                        "minimum": 0,
                        "description": ("Min total sector market cap (HKD) for HK ranking. " "Default 2e10 (200亿) when omitted; 0 disables the floor."),
                    },
                },
            },
            handler=sector_movers,
        ),
        ToolSpec(
            name="screen_market_stocks",
            description=(
                "Full-market stock screen by market cap, PE, return, daily change. "
                "Hard-excludes delisted/zero-volume tickers. Default min market cap ~10B when omitted. "
                "Mover sorts (change_percent/return_pct) use change×log(market_cap). "
                "Pass min_market_cap=0 only when user explicitly wants small/micro caps. "
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
            name="filter_sector_constituents",
            description=(
                "List quoted stocks for a taxonomy path. Prerequisite: search_sector_taxonomy — copy "
                "sector_path_id (three segments) or level1_id/level2_id/level3_id from best_match. "
                "Required: market (us|cn|hk). scope=L1|L2|L3 controls breadth (L2 = all L3 children "
                "under the same L2 branch) but ids must still be the full path from search. "
                "Returns: omit dates for latest quote change_percent + optional days window_change_percent; "
                "or pass start_date+end_date (YYYY-MM-DD) for historical window returns "
                "(single day: set both equal; dates override days). "
                "FORBIDDEN: two-segment paths like 1/2 or guessing ids."
            ),
            parameters={
                "type": "object",
                "properties": {
                    **_SECTOR_ID_PROPERTIES,
                    "market": {"type": "string", "enum": ["cn", "sh", "hk", "us"]},
                    "scope": {"type": "string", "enum": ["L1", "L2", "L3"]},
                    "days": {"type": "integer", "minimum": 1, "maximum": 90},
                    "start_date": {
                        "type": "string",
                        "description": "Optional window start YYYY-MM-DD; requires end_date; overrides days.",
                    },
                    "end_date": {
                        "type": "string",
                        "description": "Optional window end YYYY-MM-DD; requires start_date; max 126 calendar-day span.",
                    },
                },
            },
            handler=sector_constituents,
        ),
        ToolSpec(
            name="get_sector_attribution_factors",
            description=(
                "List sector attribution factors for ONE exact taxonomy path and event_time date window. "
                "Pass market + sector_id (or sector_path_id / level1_id+level2_id+level3_id from "
                "search_sector_taxonomy) + start_date + end_date (YYYY-MM-DD). "
                "locale=zh|en projects claim/mechanism to a single string. "
                "Rows without event_time are dropped; sector_id is exact-match (not path prefix)."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "market": {"type": "string", "enum": ["cn", "sh", "hk", "us"]},
                    "sector_id": {
                        "type": "string",
                        "description": "Exact L1/L2/L3 path (alias of sector_path_id).",
                    },
                    **_SECTOR_ID_PROPERTIES,
                    "start_date": {
                        "type": "string",
                        "description": "Inclusive lower bound YYYY-MM-DD (event_time calendar day).",
                    },
                    "end_date": {
                        "type": "string",
                        "description": "Inclusive upper bound YYYY-MM-DD (event_time calendar day).",
                    },
                    "locale": {
                        "type": "string",
                        "enum": ["zh", "en"],
                        "description": "Project bilingual claim/mechanism to this locale (default zh).",
                    },
                    "limit": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 1000,
                        "description": "Optional post-filter safety cap (do not use as history bound).",
                    },
                },
                "required": ["market", "start_date", "end_date"],
            },
            handler=sector_attribution_factors,
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
            description=(
                "Get ticker kline price trends and PE-band context for charting. "
                "For a specific trading day (e.g. open price on 2026-06-18), set BOTH "
                "start_date and end_date to that date (YYYY-MM-DD). "
                "For full history since dashboard inception, omit dates (server filters from 2025-01-01). "
                "Call ONCE per ticker per turn when possible — artifact pointers include latest_kline/as_of. "
                "Do NOT re-fetch with a guessed date to confirm the latest bar."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "ticker": {"type": "string"},
                    "market": {"type": "string", "enum": ["cn", "sh", "hk", "us"]},
                    "start_date": {
                        "type": "string",
                        "description": "Window start (YYYY-MM-DD). For one day, equal to end_date.",
                    },
                    "start_time": {
                        "type": "string",
                        "description": "Alias for start_date (SDK-style name).",
                    },
                    "end_date": {
                        "type": "string",
                        "description": "Window end (YYYY-MM-DD). For one day, equal to start_date.",
                    },
                    "end_time": {"type": "string", "description": "Alias for end_date."},
                    "kline_t": {"type": "string"},
                },
                "required": ["ticker"],
            },
            handler=ticker_price_trends,
        ),
    ]

    for spec in tool_specs:
        tool_registry.register(spec)
