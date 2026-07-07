"""Generate execute_code schema hints from Pydantic tool response models."""

from __future__ import annotations

from functools import lru_cache
from typing import Annotated, Any, Union, get_args, get_origin

from pydantic import BaseModel

from dojoagents.dashboard.schemas.domain_api import (
    CompanyTickerSearchResponse,
    MarketOverviewResponse,
    PortfolioListResponseV1,
    SectorAnalysisResponse,
    SectorConstituentsResponse,
    SectorMoverItem,
    SectorMoverItem,
    SectorMoversResponse,
    StockScreenResponse,
    TaxonomyTreeResponse,
    TickerFinancialsResponseV1,
    TickerNewsEventsResponseV1,
    TickerPriceTrendsResponseV1,
    TickerQuoteResponseV1,
)
from dojoagents.dashboard.schemas.dojo_mesh import BilingualText
from dojoagents.dashboard.schemas.portfolio import PortfolioDetail

_PREFERRED_ROWS_KEYS = (
    "items",
    "klines",
    "bars",
    "positions",
    "holdings",
    "candidates",
    "rows",
    "indicators",
    "tree",
    "news",
    "events",
)

_TOOL_TABLE_PANDAS = "df = pd.DataFrame(dojo_tools.tool_table(res))"

TOOL_RESPONSE_MODELS: dict[str, type[BaseModel]] = {
    "search_company_ticker": CompanyTickerSearchResponse,
    "get_taxonomy_tree": TaxonomyTreeResponse,
    "get_market_overview": MarketOverviewResponse,
    "get_sector_movers": SectorMoversResponse,
    "screen_market_stocks": StockScreenResponse,
    "get_sector_analysis": SectorAnalysisResponse,
    "filter_sector_constituents": SectorConstituentsResponse,
    "get_ticker_realtime_quote": TickerQuoteResponseV1,
    "get_ticker_financials": TickerFinancialsResponseV1,
    "get_ticker_price_trends": TickerPriceTrendsResponseV1,
    "get_ticker_news_events": TickerNewsEventsResponseV1,
    "portfolio_read_list": PortfolioListResponseV1,
    "portfolio_read_search": PortfolioListResponseV1,
    "portfolio_read_detail": PortfolioDetail,
}

TOOL_NAME_ALIASES: dict[str, str] = {
    "dojo.sdk.stock.kline": "get_ticker_price_trends",
    "code_execution": "execute_code",
}

# Only for tools whose runtime shape varies (single vs batch) — not for column naming.
MANUAL_TOOL_SCHEMA_OVERRIDES: dict[str, dict[str, Any]] = {
    "get_ticker_price_trends": {
        "pandas_example": (
            "df = pd.DataFrame(dojo_tools.tool_table(res)); "
            "df['date'] = pd.to_datetime(df['datetime'])"
        ),
    },
    "get_ticker_financials": {
        "tables": {
            "rows": {
                "type": "first_list",
                "paths": ["items", "indicators"],
                "row_fields": ["ticker", "market", "report_type", "as_of"],
            },
        },
        "default_table": "rows",
    },
    "get_ticker_realtime_quote": {
        "tables": {
            "rows": {
                "type": "first_list",
                "paths": ["items"],
                "row_fields": ["ticker", "market", "last_price", "change_percent"],
                "record_fallback": True,
            },
        },
        "default_table": "rows",
    },
    "portfolio_read_detail": {
        "tables": {
            "positions": {
                "type": "first_list",
                "paths": ["positions", "holdings"],
                "row_fields": ["ticker", "name", "market", "shares", "weight"],
            },
        },
        "default_table": "positions",
    },
}


def _unwrap_annotation(annotation: Any) -> Any:
    current = annotation
    while True:
        origin = get_origin(current)
        if origin is Annotated:
            current = get_args(current)[0]
            continue
        if origin is Union:
            args = [arg for arg in get_args(current) if arg is not type(None)]
            current = args[0] if args else current
            continue
        break
    return current


def _is_basemodel_type(annotation: Any) -> bool:
    try:
        return isinstance(annotation, type) and issubclass(annotation, BaseModel)
    except TypeError:
        return False


def _is_bilingual_text_type(annotation: Any) -> bool:
    unwrapped = _unwrap_annotation(annotation)
    return unwrapped is BilingualText or (
        _is_basemodel_type(unwrapped) and issubclass(unwrapped, BilingualText)
    )


def _is_list_of_rows(annotation: Any) -> bool:
    origin = get_origin(annotation)
    if origin is not list:
        return False
    args = get_args(annotation)
    if not args:
        return True
    inner = _unwrap_annotation(args[0])
    if _is_basemodel_type(inner):
        return True
    inner_origin = get_origin(inner)
    return inner_origin is dict or inner in (dict, Any)


def _inner_list_model(annotation: Any) -> type[BaseModel] | None:
    if get_origin(annotation) is not list:
        return None
    args = get_args(annotation)
    if not args:
        return None
    inner = _unwrap_annotation(args[0])
    return inner if _is_basemodel_type(inner) else None


def _dict_value_type(dict_ann: Any) -> Any:
    args = get_args(dict_ann)
    return _unwrap_annotation(args[1]) if len(args) >= 2 else Any


def _bilingual_field_names(model: type[BaseModel]) -> list[str]:
    return [name for name, field in model.model_fields.items() if _is_bilingual_text_type(field.annotation)]


def _row_fields_for_model(
    model: type[BaseModel] | None,
    *,
    extra: list[str] | None = None,
    skip: frozenset[str] = frozenset(),
) -> list[str]:
    fields: list[str] = list(extra or [])
    if model is None:
        return fields
    for name, field in model.model_fields.items():
        if name in skip:
            continue
        if _is_bilingual_text_type(field.annotation):
            fields.extend([f"{name}_zh", f"{name}_en"])
            continue
        origin = get_origin(_unwrap_annotation(field.annotation))
        if origin is list:
            continue
        fields.append(name)
    return fields


def _list_table(name: str, path: str, row_model: type[BaseModel] | None) -> dict[str, Any]:
    return {
        "type": "list",
        "path": path,
        "row_fields": _row_fields_for_model(row_model),
    }


def _dict_records_table(name: str, path: str, row_model: type[BaseModel] | None, *, group_key: str) -> dict[str, Any]:
    return {
        "type": "dict_records",
        "path": path,
        "group_key": group_key,
        "expand_bilingual": _bilingual_field_names(row_model) if row_model else [],
        "row_fields": _row_fields_for_model(row_model, extra=[group_key]),
    }


def _dict_list_records_table(name: str, path: str, item_model: type[BaseModel] | None, *, group_key: str) -> dict[str, Any]:
    return {
        "type": "dict_list_records",
        "path": path,
        "group_key": group_key,
        "expand_bilingual": _bilingual_field_names(item_model) if item_model else [],
        "row_fields": _row_fields_for_model(item_model, extra=[group_key]),
    }


def _dict_side_lists_table(
    path: str,
    item_model: type[BaseModel],
    *,
    group_key: str = "market",
    side_column: str = "side",
    sides: tuple[str, ...] = ("gainers", "losers"),
) -> dict[str, Any]:
    expand = _bilingual_field_names(item_model)
    return {
        "type": "dict_side_lists",
        "path": path,
        "group_key": group_key,
        "side_column": side_column,
        "sides": list(sides),
        "rank_by": [group_key, side_column],
        "expand_bilingual": expand,
        "row_fields": _row_fields_for_model(
            item_model,
            extra=[group_key, side_column, "rank"],
            skip=frozenset({"top_members", "sample_tickers"}),
        ),
    }


def _model_has_gainers_losers(model: type[BaseModel]) -> bool:
    names = set(model.model_fields)
    return "gainers" in names and "losers" in names


def _finalize_hint(hint: dict[str, Any]) -> dict[str, Any]:
    tables = hint.get("tables") or {}
    default_table = hint.get("default_table")
    if default_table and default_table in tables:
        hint.setdefault("row_fields", tables[default_table].get("row_fields", []))
    if tables and default_table:
        hint.setdefault("pandas_example", _TOOL_TABLE_PANDAS)
    return hint


def infer_schema_hint_from_model(model: type[BaseModel]) -> dict[str, Any]:
    """Build schema hint with machine-readable `tables` specs for dojo_tools.tool_table()."""
    fields = model.model_fields
    top_level_keys = list(fields.keys())
    tables: dict[str, dict[str, Any]] = {}

    list_fields: list[tuple[str, Any]] = []
    dict_fields: list[tuple[str, Any]] = []

    for name, field in fields.items():
        ann = _unwrap_annotation(field.annotation)
        origin = get_origin(ann)
        if origin is list:
            list_fields.append((name, ann))
        elif origin is dict:
            dict_fields.append((name, ann))

    for dict_name, dict_ann in dict_fields:
        val_type = _dict_value_type(dict_ann)
        if _is_basemodel_type(val_type) and _model_has_gainers_losers(val_type):
            gainers_field = val_type.model_fields.get("gainers")
            item_model = (
                _inner_list_model(gainers_field.annotation)
                if gainers_field is not None
                else None
            )
            tables["sectors"] = _dict_side_lists_table(
                dict_name,
                item_model or SectorMoverItem,
            )
            return _finalize_hint(
                {
                    "shape": "nested",
                    "top_level_keys": top_level_keys,
                    "response_model": model.__name__,
                    "default_table": "sectors",
                    "tables": tables,
                }
            )

    dict_object_specs: list[tuple[str, type[BaseModel] | None]] = []
    dict_list_specs: list[tuple[str, type[BaseModel] | None]] = []
    for dict_name, dict_ann in dict_fields:
        val_type = _dict_value_type(dict_ann)
        val_origin = get_origin(val_type)
        if val_origin is list:
            item_model = _inner_list_model(val_type)
            dict_list_specs.append((dict_name, item_model))
        elif _is_basemodel_type(val_type):
            dict_object_specs.append((dict_name, val_type))

    if dict_object_specs or dict_list_specs:
        for dict_name, row_model in dict_object_specs:
            tables[dict_name] = _dict_records_table(dict_name, dict_name, row_model, group_key="market")
        for dict_name, item_model in dict_list_specs:
            tables[dict_name] = _dict_list_records_table(dict_name, dict_name, item_model, group_key="market")
        default_table = dict_object_specs[0][0] if dict_object_specs else dict_list_specs[0][0]
        return _finalize_hint(
            {
                "shape": "nested",
                "top_level_keys": top_level_keys,
                "response_model": model.__name__,
                "default_table": default_table,
                "tables": tables,
            }
        )

    tabular_names = [name for name, ann in list_fields if _is_list_of_rows(ann)]
    if tabular_names:
        rows_key = next((name for name in _PREFERRED_ROWS_KEYS if name in tabular_names), tabular_names[0])
        row_model = _inner_list_model(next(ann for name, ann in list_fields if name == rows_key))
        tables[rows_key] = _list_table(rows_key, rows_key, row_model)
        hint: dict[str, Any] = {
            "shape": "tabular",
            "rows_key": rows_key,
            "top_level_keys": top_level_keys,
            "response_model": model.__name__,
            "default_table": rows_key,
            "tables": tables,
        }
        if len(tabular_names) > 1:
            for name in tabular_names:
                if name != rows_key:
                    inner = _inner_list_model(next(ann for n, ann in list_fields if n == name))
                    tables[name] = _list_table(name, name, inner)
            hint["other_list_keys"] = [name for name in tabular_names if name != rows_key]
        return _finalize_hint(hint)

    return _finalize_hint(
        {
            "shape": "record",
            "top_level_keys": top_level_keys,
            "response_model": model.__name__,
            "pandas_example": "data = dojo_tools.tool_json(res)",
        }
    )


def _merge_hints(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if key == "tables" and isinstance(value, dict):
            tables = dict(merged.get("tables") or {})
            tables.update(value)
            merged["tables"] = tables
        else:
            merged[key] = value
    return _finalize_hint(merged)


@lru_cache(maxsize=128)
def _cached_model_hint(model: type[BaseModel]) -> dict[str, Any]:
    return infer_schema_hint_from_model(model)


def get_tool_schema_hint(tool_name: str) -> dict[str, Any] | None:
    """Resolve schema hint for a tool (auto from Pydantic + minimal overrides)."""
    normalized = str(tool_name or "").strip()
    if not normalized:
        return None
    normalized = TOOL_NAME_ALIASES.get(normalized, normalized)

    model = TOOL_RESPONSE_MODELS.get(normalized)
    base: dict[str, Any] | None = _cached_model_hint(model) if model is not None else None

    override = MANUAL_TOOL_SCHEMA_OVERRIDES.get(normalized)
    if base and override:
        return _merge_hints(base, override)
    if override:
        return _finalize_hint(dict(override))
    if base:
        return dict(base)
    return None
