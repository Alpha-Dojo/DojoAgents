from __future__ import annotations

import json
import uuid
from collections.abc import Callable
from typing import Any

from dojoagents.tools.registry import ToolSpec

VizKind = str
MapperFn = Callable[[dict[str, Any], bool], list[dict[str, Any]]]

_MARKETS = ("us", "cn", "hk")
_SUPPORTED_KINDS = {
    "auto",
    "kpi_row",
    "sparkline",
    "line",
    "price_kline",
    "bar",
    "hbar_rank",
    "donut",
    "table",
    "timeline",
    "quote_card",
}


def _normalize_market(value: Any) -> str | None:
    raw = str(value or "").strip().lower()
    if raw in _MARKETS:
        return raw
    if raw in {"sh", "sz"}:
        return "cn"
    return None


def _group_rows_by_market(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped = {market: [] for market in _MARKETS}
    for row in rows:
        market = _normalize_market(row.get("market"))
        if market:
            grouped[market].append(row)
    return grouped


def _market_label(market: str) -> str:
    return {
        "us": "US",
        "cn": "CN",
        "hk": "HK",
    }.get(market, market.upper())


def _block(
    kind: VizKind,
    payload: dict[str, Any],
    *,
    title: str = "",
    subtitle: str | None = None,
    source_tool: str = "agent_viz_build",
    truncated: bool = False,
    market: str | None = None,
) -> dict[str, Any]:
    if market:
        payload = {**payload, "market": market}
    return {
        "id": uuid.uuid4().hex[:12],
        "kind": kind,
        "title": title,
        "subtitle": subtitle,
        "source_tool": source_tool or "agent_viz_build",
        "truncated": truncated,
        "payload": payload,
    }


def _bilingual_name(value: Any) -> tuple[str, str]:
    if isinstance(value, dict):
        return str(value.get("zh") or ""), str(value.get("en") or "")
    if isinstance(value, str):
        return value, value
    return "", ""


def _num(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _fmt_pct(value: Any) -> str | None:
    num = _num(value)
    if num is None:
        return None
    sign = "+" if num > 0 else ""
    return f"{sign}{num:.2f}%"


def _holding_total_return_pct(row: dict[str, Any]) -> float | None:
    explicit = _num(row.get("total_return_pct"))
    if explicit is not None:
        return explicit
    cost = _num(row.get("cost"))
    price = _num(row.get("price"))
    if cost is None or price is None or cost <= 0 or price <= 0:
        return None
    return round((price - cost) / cost * 100, 2)


def _lookback_subtitle(days: Any) -> str:
    if days == 0:
        return "total"
    return f"{days}D window"


def _constituent_table_columns() -> list[dict[str, Any]]:
    return [
        {"key": "ticker", "label": "Ticker"},
        {"key": "name_zh", "label": "Name"},
        {"key": "change_percent", "label": "Today P&L", "format": "percent"},
        {"key": "total_return_pct", "label": "Total P&L", "format": "percent"},
        {"key": "pe", "label": "PE", "format": "number"},
        {"key": "market_cap", "label": "Mkt Cap", "format": "market_cap"},
    ]


def _rows_from_stock_items(items: list[Any], *, limit: int = 50) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for raw in items[:limit]:
        if not isinstance(raw, dict):
            continue
        name_zh, name_en = _bilingual_name(raw.get("name"))
        rows.append(
            {
                "ticker": raw.get("ticker") or raw.get("symbol"),
                "market": _normalize_market(raw.get("market")) or raw.get("market"),
                "name_zh": raw.get("name_zh") or name_zh or name_en,
                "name_en": raw.get("name_en") or name_en,
                "change_percent": _num(raw.get("change_percent") or raw.get("change_pct")),
                "total_return_pct": _num(raw.get("window_change_percent") or raw.get("total_return_pct")),
                "pe": _num(raw.get("pe")),
                "market_cap": _num(raw.get("market_cap")),
            }
        )
    return rows


def _map_search_company_ticker(data: dict[str, Any], truncated: bool) -> list[dict[str, Any]]:
    items = data.get("items") or data.get("rows") or []
    rows = _rows_from_stock_items(list(items), limit=15) if isinstance(items, list) else []
    if not rows:
        return []
    groups = []
    for market, market_rows in _group_rows_by_market(rows).items():
        if market_rows:
            groups.append({"market": market, "rows": market_rows})
    return [
        _block(
            "table",
            {
                "layout": "by_market" if groups else "flat",
                "columns": [
                    {"key": "ticker", "label": "Ticker"},
                    {"key": "name_zh", "label": "Name"},
                    {"key": "market_cap", "label": "Market Cap", "format": "market_cap"},
                ],
                **({"groups": groups} if groups else {"rows": rows}),
            },
            title="Ticker search",
            subtitle=data.get("query"),
            source_tool="search_company_ticker",
            truncated=truncated or len(items) > len(rows),
        )
    ]


def _map_taxonomy_tree(data: dict[str, Any], truncated: bool) -> list[dict[str, Any]]:
    sectors = data.get("sectors") or data.get("items") or []
    if not isinstance(sectors, list) or not sectors:
        return []
    rows = [row for row in sectors[:20] if isinstance(row, dict)]
    if not rows:
        return []
    return [
        _block(
            "table",
            {
                "columns": [
                    {"key": "name_zh", "label": "Sector"},
                    {"key": "level1_id", "label": "L1"},
                    {"key": "level2_id", "label": "L2"},
                    {"key": "level3_id", "label": "L3"},
                ],
                "rows": rows,
            },
            title="Sector taxonomy",
            subtitle=f"{data.get('sector_count', len(sectors))} sectors",
            source_tool="get_taxonomy_tree",
            truncated=truncated or bool(data.get("truncated")),
        )
    ]


def _map_market_overview(data: dict[str, Any], truncated: bool) -> list[dict[str, Any]]:
    markets = data.get("markets") or {}
    benchmarks = data.get("benchmarks") or {}
    if not isinstance(markets, dict) or not markets:
        return []
    market_groups = []
    ordered_markets: list[str] = []
    weighted_pe_values: list[float | None] = []
    for raw_market, stats in markets.items():
        if not isinstance(stats, dict):
            continue
        market = _normalize_market(raw_market) or str(raw_market).lower()
        ordered_markets.append(market)
        items = [
            {
                "key": "market_cap",
                "label": "Total market cap",
                "value": _num(stats.get("total_market_cap")),
                "value_format": "market_cap",
            },
            {
                "key": "weighted_pe",
                "label": "Weighted PE",
                "value": _num(stats.get("weighted_pe")),
                "value_format": "number",
            },
            {
                "key": "listed_count",
                "label": "Listed",
                "value": stats.get("listed_count", 0),
                "value_format": "number",
            },
        ]
        bench_rows = benchmarks.get(raw_market) or benchmarks.get(market) or []
        if isinstance(bench_rows, list) and bench_rows:
            primary = bench_rows[0]
            if isinstance(primary, dict):
                name_zh, name_en = _bilingual_name(primary.get("name"))
                change = _num(primary.get("change_percent"))
                items.append(
                    {
                        "key": "benchmark",
                        "label": name_zh or name_en or str(primary.get("symbol") or "Benchmark"),
                        "value": change,
                        "value_format": "percent",
                        "tone": "positive" if change and change > 0 else "negative" if change and change < 0 else "neutral",
                    }
                )
        market_groups.append({"market": market, "items": items})
        weighted_pe_values.append(_num(stats.get("weighted_pe")))
    if not market_groups:
        return []
    ordered_pairs = sorted(
        zip(ordered_markets, weighted_pe_values, strict=False),
        key=lambda item: _MARKETS.index(item[0]) if item[0] in _MARKETS else len(_MARKETS),
    )
    blocks = [
        _block(
            "kpi_row",
            {"layout": "by_market", "markets": market_groups},
            title="Market overview",
            subtitle=_lookback_subtitle(data.get("days", 1)),
            source_tool="get_market_overview",
            truncated=truncated,
        )
    ]
    comparable_pairs = [(market, value) for market, value in ordered_pairs if value is not None]
    if len(comparable_pairs) >= 2:
        blocks.append(
            _block(
                "bar",
                {
                    "categories": [_market_label(market) for market, _ in comparable_pairs],
                    "series": [
                        {
                            "label": "Weighted PE",
                            "values": [value for _, value in comparable_pairs],
                        }
                    ],
                },
                title="Valuation comparison",
                subtitle="Weighted PE",
                source_tool="get_market_overview",
                truncated=truncated,
            )
        )
    return blocks


def _map_sector_movers(data: dict[str, Any], truncated: bool) -> list[dict[str, Any]]:
    markets = data.get("markets") or {}
    if not isinstance(markets, dict):
        return []
    blocks: list[dict[str, Any]] = []
    for raw_market, payload in markets.items():
        if not isinstance(payload, dict):
            continue
        gainers = []
        for row in payload.get("gainers") or []:
            if not isinstance(row, dict):
                continue
            name_zh, name_en = _bilingual_name(row.get("name"))
            gainers.append({"label": name_zh or name_en or row.get("concept_code") or row.get("label"), "value": _num(row.get("change_percent") or row.get("value")) or 0.0})
        losers = []
        for row in payload.get("losers") or []:
            if not isinstance(row, dict):
                continue
            name_zh, name_en = _bilingual_name(row.get("name"))
            losers.append({"label": name_zh or name_en or row.get("concept_code") or row.get("label"), "value": _num(row.get("change_percent") or row.get("value")) or 0.0})
        if not gainers and not losers:
            continue
        market = _normalize_market(raw_market) or str(raw_market).lower()
        blocks.append(
            _block(
                "hbar_rank",
                {"market": market, "gainers": gainers[:8], "losers": losers[:8]},
                title="Sector movers",
                subtitle=_lookback_subtitle(data.get("days", 1)),
                source_tool="get_sector_movers",
                truncated=truncated,
                market=market,
            )
        )
    return blocks


def _map_sector_analysis(data: dict[str, Any], truncated: bool) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    stats = data.get("stats_by_market") or {}
    if isinstance(stats, dict):
        market_kpis = []
        for market in _MARKETS:
            row = stats.get(market)
            if not isinstance(row, dict):
                continue
            cumulative = _num(row.get("cumulative_return_pct"))
            sharpe = _num(row.get("sharpe_ratio"))
            drawdown = _num(row.get("max_drawdown_pct"))
            market_kpis.append(
                {
                    "market": market,
                    "items": [
                        {
                            "key": "return",
                            "label": "累计收益",
                            "value": _fmt_pct(cumulative) or "—",
                            "tone": "positive" if cumulative and cumulative > 0 else "negative" if cumulative and cumulative < 0 else "neutral",
                        },
                        {"key": "sharpe", "label": "夏普", "value": f"{sharpe:.2f}" if sharpe is not None else "—"},
                        {"key": "mdd", "label": "最大回撤", "value": _fmt_pct(drawdown) or "—", "tone": "risk"},
                    ],
                }
            )
        if market_kpis:
            blocks.append(_block("kpi_row", {"layout": "by_market", "markets": market_kpis}, title="Sector performance", source_tool="get_sector_analysis", truncated=truncated))

    perf = data.get("performance_by_market") or {}
    series = _series_by_market(perf)
    if series:
        blocks.append(_block("line", {"series": series}, title="Sector NAV", source_tool="get_sector_analysis", truncated=truncated))
    return blocks


def _map_stock_screen(data: dict[str, Any], truncated: bool) -> list[dict[str, Any]]:
    items = data.get("items") or []
    if not isinstance(items, list):
        return []
    rows = _rows_from_stock_items(items)
    if not rows:
        return []
    columns = _constituent_table_columns()
    market = _normalize_market(data.get("market"))
    subtitle = _lookback_subtitle(data.get("days", 0))
    if data.get("match_count") is not None:
        subtitle = f"{subtitle} · {data.get('match_count')} matches"
    if market:
        payload = {"layout": "flat", "columns": columns, "rows": rows}
    else:
        grouped = [{"market": code, "rows": market_rows} for code, market_rows in _group_rows_by_market(rows).items() if market_rows]
        payload = {"layout": "by_market", "columns": columns, "groups": grouped}
    return [
        _block("table", payload, title="Market screen", subtitle=subtitle, market=market, source_tool="screen_market_stocks", truncated=truncated or bool(data.get("truncated")))
    ]


def _map_constituents(data: dict[str, Any], truncated: bool) -> list[dict[str, Any]]:
    items = data.get("items") or []
    if not isinstance(items, list):
        return []
    rows = _rows_from_stock_items(items, limit=20)
    if not rows:
        return []
    return [
        _block(
            "table",
            {"layout": "flat", "columns": _constituent_table_columns(), "rows": rows},
            title="Sector constituents",
            market=_normalize_market(data.get("market")),
            source_tool="filter_sector_constituents",
            truncated=truncated or bool(data.get("truncated")),
        )
    ]


def _first_quote(data: dict[str, Any]) -> dict[str, Any] | None:
    rows = data.get("quotes") or data.get("items") or data.get("data")
    if isinstance(rows, list) and rows and isinstance(rows[0], dict):
        return rows[0]
    return data


def _map_ticker_quote(data: dict[str, Any], truncated: bool) -> list[dict[str, Any]]:
    quote = _first_quote(data)
    if not isinstance(quote, dict):
        return []
    ticker = quote.get("ticker") or quote.get("symbol")
    if not ticker:
        return []
    name_zh, name_en = _bilingual_name(quote.get("name"))
    market = _normalize_market(quote.get("market"))
    return [
        _block(
            "quote_card",
            {
                "market": market,
                "ticker": ticker,
                "name_zh": quote.get("name_zh") or name_zh,
                "name_en": quote.get("name_en") or name_en,
                "last_price": _num(quote.get("last_price") or quote.get("price")),
                "change_percent": _num(quote.get("change_percent") or quote.get("change_pct")),
                "pe": _num(quote.get("pe")),
                "pb": _num(quote.get("pb")),
                "market_cap": _num(quote.get("market_cap")),
                "high": _num(quote.get("high")),
                "low": _num(quote.get("low")),
            },
            title=str(ticker),
            market=market,
            source_tool="get_ticker_realtime_quote",
            truncated=truncated,
        )
    ]


def _map_ticker_financials(data: dict[str, Any], truncated: bool) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    indicators = data.get("indicators_tail") or data.get("indicators") or []
    if isinstance(indicators, list):
        categories: list[str] = []
        revenue: list[float | None] = []
        profit: list[float | None] = []
        for row in indicators[-8:]:
            if not isinstance(row, dict):
                continue
            categories.append(str(row.get("calendar_period_label") or row.get("report_date") or ""))
            revenue.append(_num(row.get("total_revenue") or row.get("revenue")))
            profit.append(_num(row.get("net_profit") or row.get("net_income")))
        if categories and any(v is not None for v in revenue + profit):
            blocks.append(
                _block(
                    "bar",
                    {"categories": categories, "series": [{"name": "revenue", "label": "Revenue", "values": revenue}, {"name": "profit", "label": "Net profit", "values": profit}]},
                    title=f"Financials · {data.get('ticker')}",
                    source_tool="get_ticker_financials",
                    truncated=truncated,
                )
            )
    for dist in data.get("income_distributions") or []:
        if not isinstance(dist, dict):
            continue
        slices = _slices_from_items(dist.get("items") or [])
        if slices:
            blocks.append(
                _block(
                    "donut",
                    {"slices": slices, "dimension": dist.get("dimension")},
                    title=f"Income · {dist.get('dimension')}",
                    subtitle=data.get("ticker"),
                    source_tool="get_ticker_financials",
                    truncated=truncated,
                )
            )
    return blocks


def _bar_from_sequence(row: Any) -> dict[str, Any] | None:
    if isinstance(row, dict):
        close = _num(row.get("close"))
        open_ = _num(row.get("open"))
        high = _num(row.get("high"))
        low = _num(row.get("low"))
        if close is None or open_ is None or high is None or low is None:
            return None
        return {
            "date": str(row.get("datetime") or row.get("date") or row.get("bar_time") or "")[:10],
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": _num(row.get("volume")) or 0,
        }
    if isinstance(row, (list, tuple)) and len(row) >= 5:
        open_ = _num(row[1])
        high = _num(row[2])
        low = _num(row[3])
        close = _num(row[4])
        if open_ is None or high is None or low is None or close is None:
            return None
        return {"date": str(row[0])[:10], "open": open_, "high": high, "low": low, "close": close, "volume": _num(row[5]) if len(row) > 5 else 0}
    return None


def _extract_klines(data: dict[str, Any]) -> list[Any]:
    rows = data.get("klines_chart") or data.get("klines_tail") or data.get("klines") or data.get("bars")
    if isinstance(rows, list):
        return rows
    nested = data.get("data")
    if isinstance(nested, dict):
        return _extract_klines(nested)
    if isinstance(nested, list):
        return nested
    return []


def _map_price_trends(data: dict[str, Any], truncated: bool) -> list[dict[str, Any]]:
    bars = [bar for row in _extract_klines(data) if (bar := _bar_from_sequence(row)) is not None]
    if len(bars) < 2:
        return []
    change = data.get("chart_change_pct")
    if change is None:
        change = data.get("window_change_pct")
    market = _normalize_market(data.get("market"))
    return [
        _block(
            "price_kline",
            {
                "ticker": data.get("ticker") or data.get("symbol"),
                "market": market,
                "bars": bars,
                "period_start": data.get("period_start"),
                "period_end": data.get("period_end"),
                "chart_change_pct": _num(change),
                "window_change_pct": _num(data.get("window_change_pct")),
            },
            title=f"Price · {data.get('ticker') or data.get('symbol') or ''}".strip(),
            subtitle=_fmt_pct(change),
            market=market,
            source_tool="get_ticker_price_trends",
            truncated=truncated,
        )
    ]


def _map_news_events(data: dict[str, Any], truncated: bool) -> list[dict[str, Any]]:
    items = []
    for row in data.get("news") or data.get("items") or []:
        if isinstance(row, dict):
            items.append(
                {
                    "kind": "news",
                    "date": row.get("published_at") or row.get("date"),
                    "title": row.get("title"),
                    "summary": row.get("summary") or row.get("description"),
                    "source": row.get("source"),
                }
            )
    for row in data.get("events") or []:
        if isinstance(row, dict):
            items.append(
                {
                    "kind": "event",
                    "date": row.get("event_date") or row.get("date"),
                    "title": row.get("title"),
                    "summary": row.get("description") or row.get("summary"),
                    "source": row.get("event_type") or row.get("source"),
                }
            )
    if not items:
        return []
    return [
        _block(
            "timeline",
            {"items": items[:12]},
            title=f"News & events · {data.get('ticker') or data.get('symbol') or ''}".strip(),
            source_tool="get_ticker_news_and_events",
            truncated=truncated or bool(data.get("truncated")),
        )
    ]


def _map_portfolio_list(data: dict[str, Any], truncated: bool) -> list[dict[str, Any]]:
    items = data.get("items")
    if items is None and isinstance(data.get("results"), list):
        items = data.get("results")
    if items is None and isinstance(data, dict) and any(key in data for key in ("id", "name")):
        items = [data]
    if not isinstance(items, list) or not items:
        return []
    rows = [
        {
            "id": row.get("id"),
            "name": row.get("name"),
            "kind": row.get("kind"),
            "net_value_usd": _num(row.get("net_value_usd")),
            "today_change": _num(row.get("today_change")),
        }
        for row in items[:15]
        if isinstance(row, dict)
    ]
    if not rows:
        return []
    return [
        _block(
            "table",
            {
                "columns": [
                    {"key": "name", "label": "Portfolio"},
                    {"key": "id", "label": "ID"},
                    {"key": "kind", "label": "Kind"},
                    {"key": "net_value_usd", "label": "Net value", "format": "currency_usd"},
                    {"key": "today_change", "label": "Today", "format": "percent"},
                ],
                "rows": rows,
            },
            title="Portfolios",
            subtitle=data.get("query"),
            source_tool="list_or_search_portfolios",
            truncated=truncated,
        )
    ]


def _series_by_market(data: Any) -> list[dict[str, Any]]:
    if not isinstance(data, dict):
        return []
    series = []
    for market in _MARKETS:
        points = data.get(market)
        if not isinstance(points, list):
            continue
        mapped = [{"date": pt.get("date"), "value": _num(pt.get("value"))} for pt in points if isinstance(pt, dict) and _num(pt.get("value")) is not None]
        if len(mapped) >= 2:
            series.append({"id": market, "market": market, "label": market.upper(), "points": mapped})
    return series


def _slices_from_items(items: Any, *, label_key: str = "label", value_key: str = "value") -> list[dict[str, Any]]:
    if not isinstance(items, list):
        return []
    slices = []
    for index, item in enumerate(items[:12]):
        if not isinstance(item, dict):
            continue
        label = str(item.get(label_key) or item.get("ticker") or item.get("name") or item.get("item_name") or f"item_{index}")
        value = _num(item.get(value_key) or item.get("weight") or item.get("main_business_income"))
        if value is not None and value > 0:
            slices.append(
                {"key": str(item.get("key") or item.get("ticker") or label), "label": label, "value": value, **({"market": item["market"]} if item.get("market") else {})}
            )
    return slices


def _map_portfolio_analysis(data: dict[str, Any], truncated: bool) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    portfolio_name = data.get("name") or "Portfolio"
    stats = data.get("stats_by_market") or {}
    net_by_market = data.get("net_value_by_market") or {}
    market_kpis = []
    for market in _MARKETS:
        stat = stats.get(market) if isinstance(stats, dict) and isinstance(stats.get(market), dict) else {}
        net_val = _num(net_by_market.get(market)) if isinstance(net_by_market, dict) else None
        if net_val is None and not stat:
            continue
        cumulative = _num(stat.get("cumulative_return_pct"))
        sharpe = _num(stat.get("sharpe_ratio"))
        drawdown = _num(stat.get("max_drawdown_pct"))
        market_kpis.append(
            {
                "market": market,
                "items": [
                    {"key": "netValue", "label": "净值", "value": net_val, "value_format": "compact_amount"},
                    {
                        "key": "return",
                        "label": "累计收益",
                        "value": _fmt_pct(cumulative) or "—",
                        "tone": "positive" if cumulative and cumulative > 0 else "negative" if cumulative and cumulative < 0 else "neutral",
                    },
                    {"key": "sharpe", "label": "夏普", "value": f"{sharpe:.2f}" if sharpe is not None else "—"},
                    {"key": "mdd", "label": "最大回撤", "value": _fmt_pct(drawdown) or "—", "tone": "risk"},
                ],
            }
        )
    if market_kpis:
        blocks.append(_block("kpi_row", {"layout": "by_market", "markets": market_kpis}, title=portfolio_name, source_tool="get_portfolio_analysis", truncated=truncated))

    holdings = data.get("holdings") or []
    if isinstance(holdings, list):
        for market, rows in _group_rows_by_market([row for row in holdings if isinstance(row, dict)]).items():
            if not rows:
                continue
            slices = []
            table_rows = []
            for row in rows[:12]:
                weight = _num(row.get("weight")) or 0.0
                ticker = str(row.get("ticker") or "")
                if weight > 0:
                    slices.append({"key": ticker, "label": ticker, "value": weight, "market": market})
                table_rows.append(
                    {
                        "ticker": ticker,
                        "name": row.get("name_zh") or row.get("name"),
                        "weight": weight,
                        "change_percent": _num(row.get("change_percent")),
                        "total_return_pct": _holding_total_return_pct(row),
                        "market_value": _num(row.get("market_value")),
                    }
                )
            if slices:
                blocks.append(_block("donut", {"market": market, "slices": slices}, title="持仓权重", market=market, source_tool="get_portfolio_analysis", truncated=truncated))
            if table_rows:
                blocks.append(
                    _block(
                        "table",
                        {
                            "layout": "flat",
                            "market": market,
                            "columns": [
                                {"key": "ticker", "label": "Ticker"},
                                {"key": "name", "label": "Name"},
                                {"key": "weight", "label": "Weight", "format": "percent"},
                                {"key": "change_percent", "label": "Today P&L", "format": "percent"},
                                {"key": "total_return_pct", "label": "Total P&L", "format": "percent"},
                            ],
                            "rows": table_rows,
                        },
                        title="持仓明细",
                        market=market,
                        source_tool="get_portfolio_analysis",
                        truncated=truncated,
                    )
                )

    series = _series_by_market(data.get("nav_by_market") or {})
    if series:
        blocks.append(
            _block("line", {"series": series, "benchmark_series": []}, title="净值曲线", subtitle=portfolio_name, source_tool="get_portfolio_analysis", truncated=truncated)
        )
    return blocks


def _generic_table(data: dict[str, Any], truncated: bool) -> list[dict[str, Any]]:
    rows = data.get("rows") or data.get("items") or []
    if not isinstance(rows, list) or not rows:
        return []
    max_rows = int(data.get("max_rows") or 50)
    columns = data.get("columns")
    rows_are_arrays = any(isinstance(row, list) for row in rows)
    max_array_width = max((len(row) for row in rows if isinstance(row, list)), default=0)
    column_keys: list[str] = []
    if isinstance(columns, list) and columns:
        for index, column in enumerate(columns):
            if isinstance(column, dict):
                key = column.get("key")
                column_keys.append(str(key) if key is not None else f"col_{index}")
            elif rows_are_arrays:
                column_keys.append(f"col_{index}")
            else:
                column_keys.append(str(column))
    if max_array_width and len(column_keys) < max_array_width:
        column_keys.extend(f"col_{index}" for index in range(len(column_keys), max_array_width))
    row_dicts: list[dict[str, Any]] = []
    for row in rows:
        if isinstance(row, dict):
            row_dicts.append(row)
        elif isinstance(row, list):
            keys = column_keys or [f"col_{index}" for index in range(len(row))]
            row_dicts.append({key: row[index] if index < len(row) else None for index, key in enumerate(keys)})
    if not row_dicts:
        return []
    if not isinstance(columns, list) or not columns:
        keys = list(row_dicts[0].keys())[:8]
        columns = [{"key": key, "label": key.replace("_", " ").title()} for key in keys]
    else:
        normalized_columns = []
        for index, column in enumerate(columns):
            if isinstance(column, dict):
                fallback_key = column_keys[index] if index < len(column_keys) else f"col_{index}"
                key = str(column.get("key") or fallback_key)
                normalized_columns.append({**column, "key": key, "label": str(column.get("label") or key)})
            else:
                key = column_keys[index] if index < len(column_keys) else str(column)
                normalized_columns.append({"key": key, "label": str(column)})
        for index in range(len(normalized_columns), len(column_keys)):
            key = column_keys[index]
            normalized_columns.append({"key": key, "label": key})
        columns = normalized_columns
    return [_block("table", {"columns": columns, "rows": row_dicts[:max_rows]}, title=str(data.get("title") or "Table"), subtitle=data.get("subtitle"), truncated=truncated)]


def _generic_sparkline(data: dict[str, Any], truncated: bool) -> list[dict[str, Any]]:
    points = data.get("points")
    if not isinstance(points, list):
        values = data.get("values")
        if isinstance(values, list):
            points = [{"value": value} for value in values]
    if not isinstance(points, list) or len(points) < 2:
        return []
    return [
        _block(
            "sparkline",
            {
                "points": points,
                "change_percent": _num(data.get("change_percent")),
                "market": _normalize_market(data.get("market")),
            },
            title=str(data.get("title") or "Sparkline"),
            subtitle=data.get("subtitle"),
            truncated=truncated,
            market=_normalize_market(data.get("market")),
        )
    ]


def _generic_line(data: dict[str, Any], truncated: bool) -> list[dict[str, Any]]:
    series = data.get("series")
    if isinstance(series, list) and series:
        return [
            _block(
                "line",
                {"series": series, "benchmark_series": data.get("benchmark_series") or []},
                title=str(data.get("title") or "Line chart"),
                subtitle=data.get("subtitle"),
                truncated=truncated,
            )
        ]
    points = data.get("points")
    if isinstance(points, list) and len(points) >= 2:
        return [
            _block(
                "line",
                {"series": [{"id": "series", "label": data.get("label") or "Series", "points": points}]},
                title=str(data.get("title") or "Line chart"),
                subtitle=data.get("subtitle"),
                truncated=truncated,
            )
        ]
    return []


def _generic_donut(data: dict[str, Any], truncated: bool) -> list[dict[str, Any]]:
    slices = data.get("slices") if isinstance(data.get("slices"), list) else _slices_from_items(data.get("items") or data.get("rows") or [])
    if not slices:
        return []
    return [_block("donut", {"slices": slices}, title=str(data.get("title") or "Donut"), subtitle=data.get("subtitle"), truncated=truncated)]


def _generic_kpi_row(data: dict[str, Any], truncated: bool) -> list[dict[str, Any]]:
    if isinstance(data.get("markets"), list):
        return [_block("kpi_row", {"layout": "by_market", "markets": data["markets"]}, title=str(data.get("title") or "KPIs"), subtitle=data.get("subtitle"), truncated=truncated)]
    if isinstance(data.get("items"), list) and data["items"]:
        return [_block("kpi_row", {"items": data["items"]}, title=str(data.get("title") or "KPIs"), subtitle=data.get("subtitle"), truncated=truncated)]
    metrics = data.get("metrics")
    if isinstance(metrics, list) and metrics:
        items = []
        for metric in metrics:
            if not isinstance(metric, dict):
                continue
            trend = str(metric.get("trend") or "").strip().lower()
            tone = "positive" if trend == "up" else "negative" if trend == "down" else "neutral" if trend else None
            items.append(
                {
                    "key": metric.get("key"),
                    "label": str(metric.get("label") or metric.get("name") or metric.get("key") or ""),
                    "value": metric.get("value"),
                    "meta": metric.get("meta"),
                    "delta": metric.get("delta"),
                    "tone": tone,
                }
            )
        if items:
            return [_block("kpi_row", {"items": items}, title=str(data.get("title") or "KPIs"), subtitle=data.get("subtitle"), truncated=truncated)]
    return []


def _generic_bar(data: dict[str, Any], truncated: bool) -> list[dict[str, Any]]:
    if isinstance(data.get("categories"), list) and isinstance(data.get("series"), list):
        return [
            _block(
                "bar", {"categories": data["categories"], "series": data["series"]}, title=str(data.get("title") or "Bar chart"), subtitle=data.get("subtitle"), truncated=truncated
            )
        ]
    labels = data.get("labels")
    if isinstance(labels, list) and labels:
        categories = [str(label) for label in labels]
        series = []
        preferred = [
            ("pe_current", "当前PE"),
            ("pe_median", "历史中位数PE"),
            ("current", "Current"),
            ("median", "Median"),
        ]
        for key, label in preferred:
            values = data.get(key)
            if isinstance(values, list):
                series.append({"name": key, "label": label, "values": [_num(value) for value in values]})
        if not series:
            for key, values in data.items():
                if key in {"labels", "title", "subtitle", "market"}:
                    continue
                if isinstance(values, list):
                    series.append({"name": key, "label": key.replace("_", " ").title(), "values": [_num(value) for value in values]})
        if series:
            return [
                _block(
                    "bar",
                    {"categories": categories, "series": series},
                    title=str(data.get("title") or "Bar chart"),
                    subtitle=data.get("subtitle"),
                    truncated=truncated,
                    market=_normalize_market(data.get("market")),
                )
            ]
    return []


def _generic_hbar_rank(data: dict[str, Any], truncated: bool) -> list[dict[str, Any]]:
    if isinstance(data.get("gainers"), list) or isinstance(data.get("losers"), list):
        return [
            _block(
                "hbar_rank",
                {"gainers": data.get("gainers") or [], "losers": data.get("losers") or []},
                title=str(data.get("title") or "Rank"),
                subtitle=data.get("subtitle"),
                truncated=truncated,
            )
        ]
    items = data.get("items")
    if isinstance(items, list) and items:
        gainers = []
        losers = []
        for item in items:
            if not isinstance(item, dict):
                continue
            value = _num(item.get("value"))
            if value is None:
                continue
            row = {"label": str(item.get("label") or item.get("name") or item.get("key") or ""), "value": value}
            if value >= 0:
                gainers.append(row)
            else:
                losers.append(row)
        if gainers or losers:
            return [
                _block(
                    "hbar_rank",
                    {"gainers": gainers, "losers": losers},
                    title=str(data.get("title") or "Rank"),
                    subtitle=data.get("subtitle"),
                    truncated=truncated,
                )
            ]
    if isinstance(data.get("categories"), list) and isinstance(data.get("series"), list):
        return _generic_bar(data, truncated)
    return []


_MAPPERS: dict[str, MapperFn] = {
    "ticker_search": _map_search_company_ticker,
    "taxonomy_tree": _map_taxonomy_tree,
    "market_overview": _map_market_overview,
    "sector_movers": _map_sector_movers,
    "sector_analysis": _map_sector_analysis,
    "stock_screen": _map_stock_screen,
    "sector_constituents": _map_constituents,
    "ticker_quote": _map_ticker_quote,
    "ticker_financials": _map_ticker_financials,
    "ticker_kline": _map_price_trends,
    "news_timeline": _map_news_events,
    "portfolio_list": _map_portfolio_list,
    "portfolio_analysis": _map_portfolio_analysis,
}

_ALIASES = {
    "search_company_ticker": "ticker_search",
    "get_taxonomy_tree": "taxonomy_tree",
    "get_market_overview": "market_overview",
    "get_sector_movers": "sector_movers",
    "get_sector_analysis": "sector_analysis",
    "screen_market_stocks": "stock_screen",
    "filter_sector_constituents": "sector_constituents",
    "get_ticker_realtime_quote": "ticker_quote",
    "get_ticker_financials": "ticker_financials",
    "get_ticker_price_trends": "ticker_kline",
    "get_ticker_news_and_events": "news_timeline",
    "list_or_search_portfolios": "portfolio_list",
    "get_portfolio_analysis": "portfolio_analysis",
    "manage_portfolio": "portfolio_analysis",
    "add_portfolio_holding": "portfolio_analysis",
    "add_portfolio_holdings": "portfolio_analysis",
    "auto_allocate_portfolio": "portfolio_analysis",
    "dojo.sdk.stock.current_quote": "ticker_quote",
    "dojo.sdk.stock.kline": "ticker_kline",
    "dojo.sdk.forex.kline": "ticker_kline",
    "dojo.sdk.benchmark.kline": "ticker_kline",
    "dojo.sdk.stock.news": "news_timeline",
    "portfolio_read_list": "portfolio_list",
    "portfolio_read_search": "portfolio_list",
    "portfolio_read_detail": "portfolio_analysis",
    "portfolio_write_add_holding": "portfolio_analysis",
    "portfolio_write_auto_allocate": "portfolio_analysis",
}

_KIND_BUILDERS: dict[str, MapperFn] = {
    "table": _generic_table,
    "sparkline": _generic_sparkline,
    "line": _generic_line,
    "price_kline": _map_price_trends,
    "bar": _generic_bar,
    "donut": _generic_donut,
    "kpi_row": _generic_kpi_row,
    "timeline": _map_news_events,
    "quote_card": _map_ticker_quote,
    "hbar_rank": _generic_hbar_rank,
}


def _canonical_hint(value: Any) -> str:
    raw = str(value or "").strip()
    return _ALIASES.get(raw, raw)


def _auto_blocks(data: dict[str, Any], truncated: bool) -> list[dict[str, Any]]:
    candidates: list[str] = []
    if any(key in data for key in ("klines", "klines_chart", "klines_tail", "bars")):
        candidates.append("ticker_kline")
    if any(key in data for key in ("holdings", "stats_by_market", "nav_by_market", "net_value_by_market")):
        candidates.append("portfolio_analysis")
    markets = data.get("markets")
    if isinstance(markets, dict) and any(isinstance(value, dict) and ("gainers" in value or "losers" in value) for value in markets.values()):
        candidates.append("sector_movers")
    if "news" in data or "events" in data:
        candidates.append("news_timeline")
    if data.get("ticker") or data.get("symbol"):
        if any(key in data for key in ("last_price", "price", "change_percent", "change_pct")):
            candidates.append("ticker_quote")
    if "items" in data:
        candidates.append("stock_screen")
    for candidate in candidates:
        blocks = _MAPPERS[candidate](data, truncated)
        if blocks:
            return blocks
    return []


def build_viz_blocks(
    data: dict[str, Any],
    *,
    kind: str = "auto",
    mapping_hint: str = "",
    source_tool: str = "",
    title: str = "",
    subtitle: str | None = None,
    truncated: bool = False,
) -> list[dict[str, Any]]:
    if kind not in _SUPPORTED_KINDS:
        raise RuntimeError(f"Unsupported visualization kind: {kind}")

    blocks: list[dict[str, Any]] = []
    hint = _canonical_hint(mapping_hint)
    if hint in _MAPPERS:
        blocks = _MAPPERS[hint](data, truncated)
    if not blocks:
        source_hint = _canonical_hint(source_tool)
        if source_hint in _MAPPERS:
            blocks = _MAPPERS[source_hint](data, truncated)
    if not blocks and kind != "auto":
        builder = _KIND_BUILDERS.get(kind)
        blocks = builder(data, truncated) if builder else []
    if not blocks and kind == "auto":
        blocks = _auto_blocks(data, truncated)

    if title or subtitle is not None or source_tool:
        adjusted = []
        for block in blocks:
            adjusted.append(
                {
                    **block,
                    "title": title or block.get("title", ""),
                    "subtitle": subtitle if subtitle is not None else block.get("subtitle"),
                    "source_tool": source_tool or block.get("source_tool") or "agent_viz_build",
                }
            )
        blocks = adjusted
    return blocks


def _kinds_payload() -> dict[str, Any]:
    return {
        "kinds": [
            {"kind": "kpi_row", "use_for": "compact key metrics and by-market KPI groups"},
            {"kind": "sparkline", "use_for": "small single-series trend previews"},
            {"kind": "line", "use_for": "time series, NAV, performance, benchmarks"},
            {"kind": "price_kline", "use_for": "OHLCV candlestick bars"},
            {"kind": "bar", "use_for": "category comparisons and financial statement series"},
            {"kind": "hbar_rank", "use_for": "gainers and losers rankings"},
            {"kind": "donut", "use_for": "weights, allocations, composition"},
            {"kind": "table", "use_for": "rankings, holdings, search results"},
            {"kind": "timeline", "use_for": "news and events"},
            {"kind": "quote_card", "use_for": "single ticker quote snapshot"},
        ]
    }


def get_agent_viz_specs() -> list[ToolSpec]:
    async def agent_viz_build(args: dict[str, Any]) -> dict[str, Any]:
        data = args.get("data")
        if not isinstance(data, dict):
            raise RuntimeError("agent_viz_build requires data to be an object")
        if args.get("max_rows") is not None:
            data = {**data, "max_rows": args.get("max_rows")}
        kind = str(args.get("kind") or "auto")
        blocks = build_viz_blocks(
            data,
            kind=kind,
            mapping_hint=str(args.get("mapping_hint") or ""),
            source_tool=str(args.get("source_tool") or ""),
            title=str(args.get("title") or ""),
            subtitle=args.get("subtitle") if args.get("subtitle") is not None else None,
            truncated=bool(args.get("truncated", False)),
        )
        kinds = [str(block.get("kind")) for block in blocks]
        summary = f"Built {len(blocks)} visualization block(s)"
        if kinds:
            summary += f": {', '.join(kinds)}"
        else:
            summary += ". No supported visualization shape was detected."
        payload = {"block_count": len(blocks), "kinds": kinds}
        return {
            "content": summary,
            "data": payload,
            "viz_blocks": blocks,
            "metadata": {
                "mapping_hint": str(args.get("mapping_hint") or ""),
                "source_tool": str(args.get("source_tool") or ""),
            },
        }

    async def agent_viz_kinds(_: dict[str, Any]) -> dict[str, Any]:
        payload = _kinds_payload()
        return {
            "content": json.dumps(payload, ensure_ascii=False),
            "data": payload,
            "metadata": {"kind_count": len(payload["kinds"])},
        }

    return [
        ToolSpec(
            name="agent_viz_build",
            description=(
                "Build UI visualization blocks from compact structured data. "
                "Call this after data tools when charts, tables, quote cards, timelines, or allocation visuals help the answer. "
                "Use kind='auto' unless the desired block type is clear. Pass source_tool and mapping_hint when converting a previous tool result."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "kind": {"type": "string", "enum": sorted(_SUPPORTED_KINDS), "description": "Preferred block kind; use auto when unsure."},
                    "source_tool": {"type": "string", "description": "Name of the tool that produced the input data, if any."},
                    "title": {"type": "string"},
                    "subtitle": {"type": "string"},
                    "data": {"type": "object", "description": "Compact structured source data to visualize."},
                    "mapping_hint": {
                        "type": "string",
                        "description": "Hint such as portfolio_analysis, ticker_quote, ticker_kline, market_overview, sector_movers, stock_screen, news_timeline.",
                    },
                    "max_rows": {"type": "integer"},
                    "truncated": {"type": "boolean"},
                },
                "required": ["data"],
            },
            handler=agent_viz_build,
        ),
        ToolSpec(
            name="agent_viz_kinds",
            description="List supported agent visualization block kinds and when to use each one.",
            parameters={"type": "object", "properties": {}},
            handler=agent_viz_kinds,
        ),
    ]
