"""Schema-driven helpers for execute_code (imported by the generated dojo_tools stub)."""

from __future__ import annotations

import json
from typing import Any

_GENERIC_LIST_KEYS = (
    "items",
    "rows",
    "results",
    "matches",
    "candidates",
)

_SKIP_NESTED_ROW_KEYS = frozenset({"next_call", "playbook", "usage"})


def tool_json(res: dict[str, Any]) -> Any:
    if not isinstance(res, dict):
        raise TypeError("tool response must be a dict")
    if not res.get("ok"):
        raise RuntimeError(res.get("error") or "tool call failed")
    data = res.get("data")
    if isinstance(data, dict):
        return data
    content = res.get("content")
    if isinstance(content, str) and content.strip().startswith(("{", "[")):
        return json.loads(content)
    return res


def _schema_hint(res: dict[str, Any]) -> dict[str, Any]:
    hint = res.get("schema_hint")
    return hint if isinstance(hint, dict) else {}


def _table_name(hint: dict[str, Any], table: str | None) -> str | None:
    name = table or hint.get("default_table")
    return str(name) if name else None


def _table_spec(hint: dict[str, Any], table: str | None) -> dict[str, Any] | None:
    tables = hint.get("tables") or {}
    if not isinstance(tables, dict):
        return None
    name = _table_name(hint, table)
    if not name or name not in tables:
        return None
    spec = tables[name]
    return spec if isinstance(spec, dict) else None


def row_fields_for_table(hint: dict[str, Any], table: str | None = None) -> list[str]:
    spec = _table_spec(hint, table)
    if spec:
        cols = spec.get("row_fields")
        if isinstance(cols, list) and cols:
            return [str(c) for c in cols]
    cols = hint.get("row_fields")
    if isinstance(cols, list):
        return [str(c) for c in cols]
    return []


def table_names(hint: dict[str, Any]) -> list[str]:
    tables = hint.get("tables") or {}
    if isinstance(tables, dict):
        return sorted(str(k) for k in tables.keys())
    return []


def _expand_bilingual(row: dict[str, Any], fields: list[str] | None) -> dict[str, Any]:
    out = dict(row)
    for field in fields or []:
        value = out.pop(field, None)
        if isinstance(value, dict):
            out[field + "_zh"] = value.get("zh") or ""
            out[field + "_en"] = value.get("en") or ""
        else:
            out[field + "_zh"] = ""
            out[field + "_en"] = ""
    return out


def _sanitize_display_row(row: Any) -> dict[str, Any]:
    if not isinstance(row, dict):
        return {"value": row}
    out: dict[str, Any] = {}
    for key, value in row.items():
        if key in _SKIP_NESTED_ROW_KEYS:
            continue
        if isinstance(value, dict):
            if key == "name" or all(isinstance(v, (str, int, float, bool, type(None))) for v in value.values()):
                if "zh" in value or "en" in value:
                    out[f"{key}_zh"] = value.get("zh") or ""
                    out[f"{key}_en"] = value.get("en") or ""
                else:
                    out[key] = json.dumps(value, ensure_ascii=False)
            continue
        if isinstance(value, list):
            continue
        out[key] = value
    return out


def _generic_list_rows(data: Any, key: str | None = None) -> list[dict[str, Any]]:
    if not isinstance(data, dict):
        return []
    candidates: list[str] = []
    if key:
        candidates.append(key)
    candidates.extend(_GENERIC_LIST_KEYS)
    seen: set[str] = set()
    for candidate in candidates:
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        rows = data.get(candidate)
        if isinstance(rows, list) and rows:
            return [_sanitize_display_row(row) if isinstance(row, dict) else {"value": row} for row in rows]
    return []


def flatten_by_spec(data: Any, spec: dict[str, Any]) -> list[dict[str, Any]]:
    typ = str(spec.get("type") or "")
    if typ == "first_list":
        paths = spec.get("paths") or []
        expand = spec.get("expand_bilingual") or []
        if isinstance(data, dict):
            for path in paths:
                rows = data.get(path)
                if isinstance(rows, list) and rows:
                    return [_expand_bilingual(dict(row), expand) if isinstance(row, dict) else {"value": row} for row in rows]
            if spec.get("record_fallback") and data:
                return [_expand_bilingual(dict(data), expand)]
        return []

    path = spec.get("path")
    subtree = data.get(path) if isinstance(data, dict) else None
    expand = spec.get("expand_bilingual") or []

    if typ == "list":
        if not isinstance(subtree, list):
            return []
        sanitized = [_sanitize_display_row(_expand_bilingual(dict(row), expand) if isinstance(row, dict) else {"value": row}) for row in subtree]
        return sanitized

    if typ == "dict_records":
        if not isinstance(subtree, dict):
            return []
        group_key = spec.get("group_key") or "key"
        rows: list[dict[str, Any]] = []
        for key, value in subtree.items():
            row: dict[str, Any] = {group_key: key}
            if isinstance(value, dict):
                row.update(value)
            else:
                row["value"] = value
            rows.append(_sanitize_display_row(_expand_bilingual(row, expand)))
        return rows

    if typ == "dict_list_records":
        if not isinstance(subtree, dict):
            return []
        group_key = spec.get("group_key") or "group"
        rows = []
        for key, value in subtree.items():
            if not isinstance(value, list):
                continue
            for item in value:
                row = {group_key: key}
                if isinstance(item, dict):
                    row.update(item)
                else:
                    row["value"] = item
                rows.append(_sanitize_display_row(_expand_bilingual(row, expand)))
        return rows

    if typ == "dict_side_lists":
        if not isinstance(subtree, dict):
            return []
        group_key = spec.get("group_key") or "group"
        side_column = spec.get("side_column") or "side"
        sides = spec.get("sides") or ["gainers", "losers"]
        rank_by = spec.get("rank_by") or [group_key, side_column]
        rows = []
        counters: dict[tuple[Any, ...], int] = {}
        for group, payload in subtree.items():
            if not isinstance(payload, dict):
                continue
            for side in sides:
                for item in payload.get(side) or []:
                    if not isinstance(item, dict):
                        continue
                    row = {group_key: group, side_column: side, **item}
                    row = _expand_bilingual(row, expand)
                    bucket = tuple(row.get(k) for k in rank_by)
                    counters[bucket] = counters.get(bucket, 0) + 1
                    row["rank"] = counters[bucket]
                    rows.append(_sanitize_display_row(row))
        return rows

    raise KeyError("unsupported table spec type: " + typ)


def _resolve_table_rows(res: dict[str, Any], table: str | None = None) -> list[dict[str, Any]]:
    hint = _schema_hint(res)
    if hint:
        try:
            return tool_table(res, table)
        except KeyError:
            pass
    data = tool_json(res)
    rows = _generic_list_rows(data, table)
    if rows:
        return rows
    if hint:
        raise KeyError(f"no rows for table {table!r}; available tables: {', '.join(table_names(hint)) or '(none)'}")
    keys = ", ".join(sorted(data.keys())) if isinstance(data, dict) else "n/a"
    raise KeyError("no schema_hint and no generic list rows found; " f"use dojo_tools.tool_json(res). payload keys: {keys}")


def tool_table(res: dict[str, Any], table: str | None = None) -> list[dict[str, Any]]:
    data = tool_json(res)
    hint = _schema_hint(res)
    if not hint:
        raise KeyError("schema_hint is required; call via dojo_tools.load_tool_result(call_id)")
    spec = _table_spec(hint, table)
    if spec is None:
        available = ", ".join(table_names(hint)) or "(none)"
        name = _table_name(hint, table)
        raise KeyError(f"unknown table {name!r}; available: {available}")
    return flatten_by_spec(data, spec)


def tool_meta(res: dict[str, Any]) -> dict[str, Any]:
    """Scalar top-level fields only (as_of, match_count, … — not nested markets/items)."""
    data = tool_json(res)
    if not isinstance(data, dict):
        return {}
    hint = _schema_hint(res)
    keys = hint.get("top_level_keys")
    if isinstance(keys, list) and keys:
        return {k: data[k] for k in keys if k in data and not isinstance(data[k], (list, dict))}
    return {k: v for k, v in data.items() if not isinstance(v, (list, dict))}


def tool_columns(res: dict[str, Any], table: str | None = None) -> list[str]:
    rows = _resolve_table_rows(res, table)
    if not rows:
        return row_fields_for_table(_schema_hint(res), table)
    seen: set[str] = set()
    ordered: list[str] = []
    for row in rows:
        if isinstance(row, dict):
            for key in row.keys():
                if key not in seen:
                    seen.add(key)
                    ordered.append(str(key))
    schema_cols = row_fields_for_table(_schema_hint(res), table)
    if schema_cols:
        front = [c for c in schema_cols if c in seen]
        tail = [c for c in ordered if c not in front]
        return front + tail
    return ordered


def _order_dataframe_columns(df: Any, schema_cols: list[str]) -> Any:
    if df is None or getattr(df, "empty", True):
        return df
    actual = list(df.columns)
    if not schema_cols:
        return df
    front = [c for c in schema_cols if c in actual]
    tail = [c for c in actual if c not in front]
    return df[front + tail] if front or tail else df


def tool_df(res: dict[str, Any], table: str | None = None) -> Any:
    import pandas as pd

    rows = _resolve_table_rows(res, table)
    df = pd.DataFrame(rows)
    return _order_dataframe_columns(df, row_fields_for_table(_schema_hint(res), table))


def tool_pick(df: Any, columns: list[str] | None = None) -> Any:
    """Select columns without KeyError; missing names are skipped."""
    if df is None or columns is None:
        return df
    if getattr(df, "empty", True):
        return df
    cols = [c for c in columns if c in df.columns]
    return df[cols] if cols else df


def tool_concat(
    results: list[dict[str, Any]],
    *,
    table: str | None = None,
    dedupe: bool = True,
) -> Any:
    """Stack rows from multiple load_tool_result payloads (e.g. CN + HK constituents)."""
    import pandas as pd

    frames = []
    for res in results:
        if not isinstance(res, dict):
            continue
        df = tool_df(res, table)
        if df is not None and not getattr(df, "empty", True):
            frames.append(df)
    if not frames:
        return pd.DataFrame()
    out = pd.concat(frames, ignore_index=True, sort=False)
    if dedupe:
        out = out.drop_duplicates(keep="first")
    return out


def tool_merge(
    left: dict[str, Any] | Any,
    right: dict[str, Any] | Any,
    *,
    on: list[str] | None = None,
    table: str | None = None,
    how: str = "left",
) -> Any:
    """Merge two tool results or DataFrames using explicit join keys."""
    import pandas as pd

    ldf = tool_df(left, table) if isinstance(left, dict) else left
    rdf = tool_df(right, table) if isinstance(right, dict) else right
    keys = list(on or [])
    if not keys:
        raise KeyError("tool_merge: explicit 'on' keys are required; " f"left={list(ldf.columns)} right={list(rdf.columns)}")
    overlap = (set(ldf.columns) & set(rdf.columns)) - set(keys)
    rdf = rdf.drop(columns=[c for c in overlap if c in rdf.columns], errors="ignore")
    return pd.merge(ldf, rdf, on=keys, how=how)


def tool_print(
    res: dict[str, Any],
    *,
    table: str | None = None,
    columns: list[str] | None = None,
    title: str | None = None,
    limit: int | None = None,
) -> None:
    """Print metadata + tabular rows safely (no KeyError on missing columns)."""
    if title:
        print(title)
    meta = tool_meta(res)
    if meta:
        for key, value in meta.items():
            print(f"{key}: {value}")
    df = tool_df(res, table)
    if columns is None and not getattr(df, "empty", True):
        columns = row_fields_for_table(_schema_hint(res), table) or list(df.columns)
    view = tool_pick(df, columns)
    if limit is not None and hasattr(view, "head"):
        view = view.head(limit)
    if getattr(view, "empty", True):
        data = tool_json(res)
        items = data.get("items") if isinstance(data, dict) else None
        if isinstance(items, list) and len(items) == 0:
            print("(no matches)")
            best = data.get("best_match") if isinstance(data, dict) else None
            if isinstance(best, dict) and best:
                print("best_match:", json.dumps(best, ensure_ascii=False))
        else:
            print("(no rows)")
            if isinstance(data, dict):
                print("payload keys:", ", ".join(sorted(data.keys())))
    else:
        print(view.to_string(index=False))


def tool_rows(res: dict[str, Any], key: str | None = None) -> list[dict[str, Any]]:
    hint = _schema_hint(res)
    if key is None and hint.get("tables") and hint.get("default_table"):
        return tool_table(res)
    data = tool_json(res)
    if key:
        rows = data.get(key) if isinstance(data, dict) else None
        if isinstance(rows, list):
            return rows
        raise KeyError(f"list key not found: {key!r}")
    hint_key = hint.get("rows_key")
    fallback_keys = hint.get("fallback_rows_keys")
    candidates: list[str] = []
    if isinstance(hint_key, str):
        candidates.append(hint_key)
    if isinstance(fallback_keys, list):
        candidates.extend(str(item) for item in fallback_keys if item)
    candidates.extend(_GENERIC_LIST_KEYS)
    seen: set[str] = set()
    for candidate in candidates:
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        if isinstance(data, dict):
            rows = data.get(candidate)
            if isinstance(rows, list):
                return rows
    nested = data.get("data") if isinstance(data, dict) else None
    if isinstance(nested, list):
        return nested
    keys = ", ".join(sorted(data.keys())) if isinstance(data, dict) else "n/a"
    msg = "no tabular rows; use dojo_tools.tool_df(res) or tool_df(res, '<table>'). " f"tables={table_names(hint) or 'n/a'}; payload keys: {keys}"
    raise KeyError(msg)


def format_execute_code_error_hint(output: str, code: str) -> str:
    """Append actionable hints when common execute_code patterns fail."""
    if "KeyError" not in output and "NameError" not in output:
        return output
    hints: list[str] = []
    if "KeyError" in output and ("name_zh" in output or "symbol" in output or "columns" in output.lower()):
        hints.append(
            "HINT: use dojo_tools.tool_df(res[, table]) then dojo_tools.tool_pick(df, columns) "
            "or dojo_tools.tool_print(res, table='...', columns=[...]). "
            "Column names: dojo_tools.tool_columns(res[, table]). "
            "Multi-table tools: res['schema_hint']['tables'].keys()."
        )
    if "KeyError" in output and ("merge" in output.lower() or "_x" in output or "_y" in output):
        hints.append(
            "HINT: combine compatible result tables with "
            "dojo_tools.tool_concat([res_a, res_b]). "
            "Join two tables with dojo_tools.tool_merge(res_a, res_b, on=[...]). "
            "Avoid manual pd.merge — use tool_pick after merge for columns."
        )
    if "KeyError" in output and ("schema_hint" in output or "no generic list" in output):
        hints.append(
            "HINT: inspect available schema tables before calling "
            "dojo_tools.tool_print(res, table='...'). Nested payloads may require "
            "tool_json(res) instead of tabular conversion."
        )
    if "KeyError" in output and "load_tool_result" not in code and "tool_df" not in code and "tool_print" not in code:
        hints.append("HINT: load prior tool output with res = dojo_tools.load_tool_result(call_id).")
    if "NameError" in output and " pd" in output or "pd." in output:
        hints.append("HINT: pd/np/dojo_tools are pre-imported in execute_code bootstrap.")
    if not hints:
        return output
    return output.rstrip() + "\n\n--- execute_code hints ---\n" + "\n".join(hints)
