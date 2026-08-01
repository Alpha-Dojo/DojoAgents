"""Generate execute_code schema hints from Pydantic tool response models."""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Annotated, Any, Dict, Mapping, Union, get_args, get_origin

from pydantic import BaseModel

# Single priority list: default_table selection AND preferred rows_key order.
DEFAULT_TABLE_PRIORITY = (
    "sectors",
    "items",
    "klines",
    "bars",
    "positions",
    "holdings",
    "candidates",
    "rows",
    "indicators",
    "markets",
    "benchmarks",
    "news",
    "events",
    "tree",
)

_TOOL_TABLE_PANDAS = "dojo_tools.tool_print(res)"
_TOOL_MULTI_TABLE_PANDAS = "meta = dojo_tools.tool_meta(res); " "dojo_tools.tool_print(res, table='markets'); " "dojo_tools.tool_print(res, table='benchmarks')"
_TOOL_TREE_PANDAS = "data = dojo_tools.tool_json(res); tree = data.get('tree') or []"
_TOOL_TREE_NOTES = (
    "Nested L1→L2→L3 via children[]; do NOT flatten with tool_print/tool_df. "
    "Use dojo_tools.tool_json(res)['tree']. Prefer search_sector_taxonomy for keyword lookup."
)


class SchemaHintRegistry:
    """Explicit tool_name → response model map."""

    def __init__(self) -> None:
        self._models: dict[str, type[BaseModel]] = {}

    def register(self, tool_name: str, model: type[BaseModel]) -> None:
        name = str(tool_name or "").strip()
        if not name:
            raise ValueError("tool_name is required")
        if not isinstance(model, type) or not issubclass(model, BaseModel):
            raise TypeError(f"model must be a BaseModel subclass, got {model!r}")
        self._models[name] = model

    def register_many(self, mapping: Mapping[str, type[BaseModel]]) -> None:
        for tool_name, model in mapping.items():
            self.register(tool_name, model)

    def get_model(self, tool_name: str) -> type[BaseModel] | None:
        return self._models.get(str(tool_name or "").strip())

    def clear(self) -> None:
        self._models.clear()

    def items(self) -> list[tuple[str, type[BaseModel]]]:
        return sorted(self._models.items(), key=lambda item: item[0])


_REGISTRY = SchemaHintRegistry()
_DEFAULTS_REGISTERED = False


def get_schema_hint_registry() -> SchemaHintRegistry:
    return _REGISTRY


def register_financial_response_models(registry: SchemaHintRegistry | None = None) -> SchemaHintRegistry:
    """Bind financial tool names to Pydantic response models (idempotent)."""
    from dojoagents.dashboard.schemas.domain_api import (
        CompanyTickerSearchResponse,
        MarketOverviewResponse,
        SectorAnalysisResponse,
        SectorConstituentsResponse,
        SectorMoversResponse,
        StockScreenResponse,
        TaxonomyTreeResponse,
        TickerFinancialsBatchResponseV1,
        TickerNewsEventsResponseV1,
        TickerPriceTrendsResponseV1,
        TickerQuotesBatchResponseV1,
    )

    reg = registry if registry is not None else _REGISTRY
    reg.register_many(
        {
            "search_company_ticker": CompanyTickerSearchResponse,
            "get_taxonomy_tree": TaxonomyTreeResponse,
            "get_market_overview": MarketOverviewResponse,
            "get_sector_movers": SectorMoversResponse,
            "screen_market_stocks": StockScreenResponse,
            "get_sector_analysis": SectorAnalysisResponse,
            "filter_sector_constituents": SectorConstituentsResponse,
            "get_ticker_realtime_quote": TickerQuotesBatchResponseV1,
            "get_ticker_financials": TickerFinancialsBatchResponseV1,
            "get_ticker_news_and_events": TickerNewsEventsResponseV1,
            "get_ticker_price_trends": TickerPriceTrendsResponseV1,
        }
    )
    return reg


def _ensure_default_models_registered() -> None:
    global _DEFAULTS_REGISTERED
    if _DEFAULTS_REGISTERED:
        return
    register_financial_response_models(_REGISTRY)
    _DEFAULTS_REGISTERED = True


# Fallback only for tools without a registered ResponseModel.
STATIC_TOOL_SCHEMA_HINTS: dict[str, dict[str, Any]] = {}

TOOL_NAME_ALIASES: dict[str, str] = {
    "dojo.sdk.stock.kline": "get_ticker_price_trends",
    "code_execution": "execute_code",
}

# Usage notes, first_list fallbacks, and tools with no ResponseModel.
MANUAL_TOOL_SCHEMA_OVERRIDES: dict[str, dict[str, Any]] = {
    "get_ticker_price_trends": {
        "pandas_example": ("df = dojo_tools.tool_df(res); " "df['date'] = pd.to_datetime(df['datetime'])"),
    },
    "get_market_overview": {
        "pandas_example": _TOOL_MULTI_TABLE_PANDAS,
        "usage_notes": (
            "Window: pass days (latest N trade days, default 1, max 90) OR start_date+end_date "
            "(YYYY-MM-DD, both required, max 126 calendar days); dates override days. "
            "Scalars via dojo_tools.tool_meta(res): window_mode, window_start, window_end, as_of, days. "
            "Tables: markets=current cap/PE/count snapshot; benchmarks=window change_percent + clipped klines. "
            "Omit market arg for US+CN+HK in one call."
        ),
    },
    "get_sector_movers": {
        "usage_notes": (
            "Window rules match get_market_overview (days OR start_date+end_date). "
            "tool_meta(res): window_mode, window_start, window_end, days. "
            "Default table sectors: gainers/losers per market with side+rank columns. "
            "change_percent = sector total return over window. Rankings skip member_count<5 "
            "and default to 200亿 (2e10) total-sector cap floor (pass min_cap_*=0 to disable). "
            "Copy level1_id/level2_id/level3_id into filter_sector_constituents or get_sector_analysis."
        ),
    },
    "filter_sector_constituents": {
        "usage_notes": (
            "Default (omit dates): change_percent = live quote; window_change_percent from optional days "
            "(1–90). Historical: pass start_date+end_date (YYYY-MM-DD, both required; single day: set equal; "
            "max 126 calendar-day span) — dates override days and fill both change_percent and "
            "window_change_percent with the window return."
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
    "search_sector_taxonomy": {
        "shape": "tabular",
        "rows_key": "items",
        "top_level_keys": ["query", "count", "expanded_queries", "l3_options"],
        "default_table": "items",
        "tables": {
            "items": {
                "type": "list",
                "path": "items",
                "expand_bilingual": [],
                "row_fields": [
                    "sector_path_id",
                    "level1_id",
                    "level2_id",
                    "level3_id",
                    "breadcrumb_zh",
                    "breadcrumb_en",
                    "level3_name_zh",
                    "level3_name_en",
                    "match_score",
                    "matched_level",
                ],
            },
            "l3_options": {
                "type": "list",
                "path": "l3_options",
                "expand_bilingual": [],
                "row_fields": [
                    "sector_path_id",
                    "name_zh",
                    "name_en",
                    "level2_name_zh",
                    "level2_name_en",
                    "hit",
                ],
            },
        },
        "pandas_example": (
            "dojo_tools.tool_print(res, table='items'); "
            "dojo_tools.tool_print(res, table='l3_options')"
        ),
        "usage_notes": (
            "items/best_match = ranked keyword hits. "
            "l3_options = full L3 menu under those L2 branches (hit marks items overlap). "
            "Copy sector_path_id verbatim from items or l3_options."
        ),
    },
    "get_taxonomy_tree": {
        "shape": "tree",
        "tree_key": "tree",
        "pandas_example": _TOOL_TREE_PANDAS,
        "usage_notes": _TOOL_TREE_NOTES,
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


def _is_list_annotation(annotation: Any) -> bool:
    return annotation is list or get_origin(annotation) is list


def _is_dict_annotation(annotation: Any) -> bool:
    return annotation in (dict, Dict) or get_origin(annotation) is dict


def _is_basemodel_type(annotation: Any) -> bool:
    return isinstance(annotation, type) and issubclass(annotation, BaseModel)


def _is_bilingual_text_type(annotation: Any) -> bool:
    unwrapped = _unwrap_annotation(annotation)
    return isinstance(unwrapped, type) and unwrapped.__name__ == "BilingualText"


def _is_list_of_rows(annotation: Any) -> bool:
    if not _is_list_annotation(annotation):
        return False
    args = get_args(annotation)
    if not args:
        return True
    inner = _unwrap_annotation(args[0])
    if _is_basemodel_type(inner):
        return True
    return get_origin(inner) is dict or inner in (dict, Any)


def _inner_list_model(annotation: Any) -> type[BaseModel] | None:
    if not _is_list_annotation(annotation):
        return None
    args = get_args(annotation)
    if not args:
        return None
    inner = _unwrap_annotation(args[0])
    return inner if _is_basemodel_type(inner) else None


def _dict_value_type(dict_ann: Any) -> Any:
    args = get_args(dict_ann)
    return _unwrap_annotation(args[1]) if len(args) >= 2 else Any


def _is_untyped_dict(annotation: Any) -> bool:
    return _is_dict_annotation(annotation) and not get_args(annotation)


def _bilingual_field_names(model: type[BaseModel]) -> list[str]:
    return [name for name, field in model.model_fields.items() if _is_bilingual_text_type(field.annotation)]


def _row_fields_for_model(
    model: type[BaseModel] | None,
    *,
    extra: list[str] | None = None,
    skip: frozenset[str] = frozenset(),
) -> list[str]:
    fields: list[str] = []
    seen: set[str] = set()
    for name in extra or []:
        if name and name not in seen:
            fields.append(name)
            seen.add(name)
    if model is None:
        return fields
    for name, field in model.model_fields.items():
        if name in skip or name in seen:
            continue
        if _is_bilingual_text_type(field.annotation):
            for col in (f"{name}_zh", f"{name}_en"):
                if col not in seen:
                    fields.append(col)
                    seen.add(col)
            continue
        ann = _unwrap_annotation(field.annotation)
        if _is_list_annotation(ann):
            continue
        fields.append(name)
        seen.add(name)
    return fields


def _list_table(path: str, row_model: type[BaseModel] | None) -> dict[str, Any]:
    return {
        "type": "list",
        "path": path,
        "expand_bilingual": _bilingual_field_names(row_model) if row_model else [],
        "row_fields": _row_fields_for_model(row_model),
    }


def _dict_records_table(path: str, row_model: type[BaseModel] | None, *, group_key: str) -> dict[str, Any]:
    return {
        "type": "dict_records",
        "path": path,
        "group_key": group_key,
        "expand_bilingual": _bilingual_field_names(row_model) if row_model else [],
        "row_fields": _row_fields_for_model(row_model, extra=[group_key]),
    }


def _dict_list_records_table(path: str, item_model: type[BaseModel] | None, *, group_key: str) -> dict[str, Any]:
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
    return {
        "type": "dict_side_lists",
        "path": path,
        "group_key": group_key,
        "side_column": side_column,
        "sides": list(sides),
        "rank_by": [group_key, side_column],
        "expand_bilingual": _bilingual_field_names(item_model),
        "row_fields": _row_fields_for_model(
            item_model,
            extra=[group_key, side_column, "rank"],
            skip=frozenset({"top_members", "sample_tickers"}),
        ),
    }


def _model_has_gainers_losers(model: type[BaseModel]) -> bool:
    names = set(model.model_fields)
    return "gainers" in names and "losers" in names


def _model_has_children_list(model: type[BaseModel]) -> bool:
    children = model.model_fields.get("children")
    if children is None:
        return False
    return _is_list_annotation(_unwrap_annotation(children.annotation))


def _is_tree_list_annotation(annotation: Any) -> bool:
    row_model = _inner_list_model(annotation)
    return row_model is not None and _model_has_children_list(row_model)


def _pick_default_table(tables: Mapping[str, Any]) -> str | None:
    if not tables:
        return None
    for name in DEFAULT_TABLE_PRIORITY:
        if name in tables:
            return name
    return sorted(tables.keys())[0]


def _pick_rows_key(tables: Mapping[str, Any]) -> str | None:
    for name in DEFAULT_TABLE_PRIORITY:
        spec = tables.get(name)
        if isinstance(spec, dict) and spec.get("type") == "list":
            return name
    for name, spec in tables.items():
        if isinstance(spec, dict) and spec.get("type") == "list":
            return name
    return None


def _infer_shape(tables: Mapping[str, Any], tree_keys: list[str]) -> str:
    """tabular = only list tables; nested = any dict_* / side_lists; tree = tree only."""
    if not tables:
        return "tree" if tree_keys else "record"
    if all(spec.get("type") == "list" for spec in tables.values()):
        return "tabular"
    return "nested"


def _finalize_hint(hint: dict[str, Any]) -> dict[str, Any]:
    tables = hint.get("tables") or {}
    default_table = hint.get("default_table")
    if default_table and default_table in tables:
        hint.setdefault("row_fields", tables[default_table].get("row_fields", []))
    if tables and default_table:
        hint.setdefault("pandas_example", _TOOL_TABLE_PANDAS)
    elif hint.get("shape") == "tree":
        hint.setdefault("pandas_example", _TOOL_TREE_PANDAS)
        hint.setdefault("usage_notes", _TOOL_TREE_NOTES)
    return hint


def _deep_merge_dicts(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Merge dicts recursively; lists and scalars from override replace base."""
    out = dict(base)
    for key, value in override.items():
        existing = out.get(key)
        if isinstance(existing, dict) and isinstance(value, dict):
            out[key] = _deep_merge_dicts(existing, value)
        else:
            out[key] = value
    return out


@dataclass
class _CollectedSpecs:
    top_level_keys: list[str]
    tables: dict[str, dict[str, Any]] = field(default_factory=dict)
    tree_keys: list[str] = field(default_factory=list)
    untyped_fields: list[str] = field(default_factory=list)


def _collect_field_specs(model: type[BaseModel]) -> _CollectedSpecs:
    """Walk model fields once and emit table / tree / untyped specs."""
    specs = _CollectedSpecs(top_level_keys=list(model.model_fields.keys()))

    for name, field_info in model.model_fields.items():
        ann = _unwrap_annotation(field_info.annotation)

        if _is_list_annotation(ann):
            if _is_tree_list_annotation(ann):
                specs.tree_keys.append(name)
            elif _is_list_of_rows(ann):
                specs.tables[name] = _list_table(name, _inner_list_model(ann))
            continue

        if not _is_dict_annotation(ann):
            continue

        if _is_untyped_dict(ann):
            specs.untyped_fields.append(name)
            continue

        val_type = _dict_value_type(ann)
        if _is_basemodel_type(val_type) and _model_has_gainers_losers(val_type):
            gainers_field = val_type.model_fields.get("gainers")
            item_model = _inner_list_model(gainers_field.annotation) if gainers_field is not None else None
            specs.tables["sectors"] = _dict_side_lists_table(name, item_model or BaseModel)
            continue

        if _is_list_annotation(val_type):
            specs.tables[name] = _dict_list_records_table(name, _inner_list_model(val_type), group_key="market")
        elif _is_basemodel_type(val_type):
            specs.tables[name] = _dict_records_table(name, val_type, group_key="market")
        else:
            specs.untyped_fields.append(name)

    return specs


def _assemble_hint(model_name: str, specs: _CollectedSpecs) -> dict[str, Any]:
    """Build a single hint dict from collected specs (one exit path)."""
    tables = specs.tables
    tree_keys = specs.tree_keys
    shape = _infer_shape(tables, tree_keys)

    hint: dict[str, Any] = {
        "shape": shape,
        "top_level_keys": specs.top_level_keys,
        "response_model": model_name,
    }

    if shape == "tree":
        tree_key = next((name for name in DEFAULT_TABLE_PRIORITY if name in tree_keys), tree_keys[0])
        hint["tree_key"] = tree_key
        hint["pandas_example"] = _TOOL_TREE_PANDAS
        hint["usage_notes"] = _TOOL_TREE_NOTES
    elif tables:
        default_table = _pick_default_table(tables)
        rows_key = _pick_rows_key(tables)
        hint["default_table"] = default_table
        hint["tables"] = tables
        if rows_key:
            hint["rows_key"] = rows_key
            other_lists = [name for name, spec in tables.items() if spec.get("type") == "list" and name != rows_key]
            if other_lists:
                hint["other_list_keys"] = other_lists
        if tree_keys:
            hint["tree_keys"] = tree_keys
            hint.setdefault("usage_notes", _TOOL_TREE_NOTES)
    else:
        hint["pandas_example"] = "data = dojo_tools.tool_json(res)"

    if specs.untyped_fields:
        hint["untyped_fields"] = list(specs.untyped_fields)
    return _finalize_hint(hint)


def infer_schema_hint_from_model(model: type[BaseModel]) -> dict[str, Any]:
    """Build schema hint with machine-readable `tables` specs for dojo_tools.tool_table()."""
    try:
        model.model_rebuild()
    except Exception:
        pass
    return _assemble_hint(model.__name__, _collect_field_specs(model))


def _merge_hints(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        existing = merged.get(key)
        if isinstance(existing, dict) and isinstance(value, dict):
            merged[key] = _deep_merge_dicts(existing, value)
        else:
            merged[key] = value
    return _finalize_hint(merged)


@lru_cache(maxsize=128)
def _cached_model_hint(model: type[BaseModel]) -> dict[str, Any]:
    return infer_schema_hint_from_model(model)


def get_tool_schema_hint(tool_name: str) -> dict[str, Any] | None:
    """Resolve schema hint for a tool (auto from Pydantic + minimal overrides)."""
    _ensure_default_models_registered()
    normalized = str(tool_name or "").strip()
    if not normalized:
        return None
    normalized = TOOL_NAME_ALIASES.get(normalized, normalized)

    model = _REGISTRY.get_model(normalized)
    base: dict[str, Any] | None = None
    if model is not None:
        base = _cached_model_hint(model)
    elif normalized in STATIC_TOOL_SCHEMA_HINTS:
        base = STATIC_TOOL_SCHEMA_HINTS[normalized]

    override = MANUAL_TOOL_SCHEMA_OVERRIDES.get(normalized)
    if base and override:
        result = _merge_hints(base, override)
    elif override:
        result = _finalize_hint(dict(override))
    elif base:
        result = base
    else:
        return None
    return copy.deepcopy(result)
