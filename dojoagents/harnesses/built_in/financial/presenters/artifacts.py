"""Financial interpretation of generic persisted tool-result artifacts."""

from __future__ import annotations

import json
import re
from typing import Any

from .schema_hints import get_tool_schema_hint

_VIZ_DATA_MARKER = re.compile(r"===\s*VIZ_DATA\s*===", re.IGNORECASE)


def get_tool_artifact_schema_hint(tool_name: str) -> dict[str, Any] | None:
    hint = get_tool_schema_hint(tool_name)
    return dict(hint) if hint else None


def _normalize_bar_datetime(row: Any) -> str:
    if isinstance(row, dict):
        for key in ("datetime", "bar_time", "date"):
            value = row.get(key)
            if value:
                return str(value).strip()[:10]
        return ""
    for key in ("bar_time", "datetime", "date"):
        value = getattr(row, key, None)
        if value:
            return str(value).strip()[:10]
    return ""


def _position_rows_from_detail(data: dict[str, Any]) -> list[dict[str, Any]]:
    for key in ("positions", "holdings"):
        rows = data.get(key)
        if isinstance(rows, list):
            return [row for row in rows if isinstance(row, dict)]
    return []


def summarize_portfolio_detail_artifact_data(data: dict[str, Any]) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    portfolio_id = data.get("id") or data.get("portfolio_id")
    if portfolio_id:
        summary["portfolio_id"] = portfolio_id
    for key in ("name", "kind"):
        if data.get(key):
            summary[key] = data[key]
    eval_summary = data.get("eval_summary")
    if isinstance(eval_summary, dict):
        fields = (
            "candidate_count",
            "candidate_count_by_market",
            "position_count",
            "position_count_by_market",
        )
        summary["eval_summary"] = {field: eval_summary[field] for field in fields if field in eval_summary}
    else:
        summary["eval_summary"] = {
            "candidate_count": len(data.get("candidates") or []),
            "position_count": len(_position_rows_from_detail(data)),
        }
    positions: list[dict[str, Any]] = []
    for row in _position_rows_from_detail(data):
        try:
            shares = float(row.get("shares") or 0)
        except (TypeError, ValueError):
            shares = 0.0
        if shares <= 0:
            continue
        compact = {
            "ticker": row.get("ticker"),
            "name": row.get("name") or row.get("name_zh") or row.get("name_en"),
            "market": row.get("market"),
            "shares": shares,
        }
        for key in ("weight", "name_zh"):
            if row.get(key) is not None:
                compact[key] = row[key]
        positions.append(compact)
    if positions:
        summary["positions"] = positions
    candidates = data.get("candidates")
    if isinstance(candidates, list) and candidates:
        summary["candidate_count"] = len(candidates)
        summary["candidate_tickers"] = [str(row["ticker"]) for row in candidates[:40] if isinstance(row, dict) and row.get("ticker")]
    return summary


def summarize_kline_artifact_data(data: dict[str, Any]) -> dict[str, Any]:
    summary = {key: data[key] for key in ("as_of", "period_start", "period_end", "interval") if data.get(key)}
    klines = data.get("klines") or data.get("bars")
    if not isinstance(klines, list) or not klines:
        return summary
    latest_row = max(klines, key=lambda row: _normalize_bar_datetime(row) or "")
    bar_date = _normalize_bar_datetime(latest_row)
    if not bar_date:
        return summary

    def number(key: str) -> float | None:
        raw = latest_row.get(key) if isinstance(latest_row, dict) else getattr(latest_row, key, None)
        try:
            return None if raw is None else float(raw)
        except (TypeError, ValueError):
            return None

    latest: dict[str, Any] = {"datetime": bar_date}
    for field in ("open", "high", "low", "close", "volume"):
        value = number(field)
        if value is None and field == "volume":
            value = number("vol")
        if value is not None:
            latest[field] = value
    summary["latest_kline"] = latest
    summary.setdefault("as_of", bar_date)
    summary.setdefault("period_end", bar_date)
    return summary


def extract_viz_payload_from_content(content: str) -> dict[str, Any] | None:
    match = _VIZ_DATA_MARKER.search(str(content or ""))
    if not match:
        return None
    after = str(content or "")[match.end() :].strip()
    start = after.find("{")
    if start < 0:
        return None
    blob = after[start:]
    try:
        payload = json.loads(blob)
        return payload if isinstance(payload, dict) else None
    except json.JSONDecodeError:
        for line in blob.splitlines():
            try:
                payload = json.loads(line.strip())
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                return payload
    return None


def get_viz_hint_for_payload(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None
    dates, prices = payload.get("dates"), payload.get("prices")
    if isinstance(dates, list) and isinstance(prices, list) and len(dates) >= 2 and len(prices) >= 2:
        summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
        return {
            "mapping_hint": "drawdown_analysis",
            "kind": "auto",
            "required_fields": ["dates", "prices"],
            "optional_fields": ["drawdown_pcts", "summary"],
            "agent_viz_build_example": {
                "mapping_hint": "drawdown_analysis",
                "kind": "auto",
                "title": f"{summary.get('ticker') or 'Ticker'} drawdown",
                "data": {
                    "dates": dates[:2] + ["..."],
                    "prices": prices[:2] + ["..."],
                    "drawdown_pcts": payload.get("drawdown_pcts", [])[:2] + ["..."],
                    "summary": summary or {"max_drawdown_pct": 17.5},
                },
            },
        }
    if payload.get("klines") or payload.get("bars"):
        return {
            "mapping_hint": "ticker_kline",
            "kind": "auto",
            "source_tool": "get_ticker_price_trends",
            "data_keys": ["klines", "bars"],
        }
    if payload.get("series") or payload.get("points"):
        return {"kind": "line", "data_keys": ["series", "points"]}
    if payload.get("metrics") or payload.get("items"):
        return {"kind": "kpi_row", "data_keys": ["metrics", "items"]}
    if payload.get("rows"):
        return {"kind": "table", "data_keys": ["rows", "columns"]}
    return None


def format_execute_code_viz_hint(payload: dict[str, Any] | None) -> str:
    hint = get_viz_hint_for_payload(payload)
    return "" if not hint else "\n\n--- viz_hint ---\n" + json.dumps(hint, ensure_ascii=False, indent=2)


def enrich_execute_code_tool_result(result: dict[str, Any]) -> dict[str, Any]:
    enriched = dict(result)
    content = str(enriched.get("content") or "")
    payload = enriched.get("data")
    if not isinstance(payload, dict):
        payload = extract_viz_payload_from_content(content)
        if payload is not None:
            enriched["data"] = payload
    elif not isinstance(payload.get("session_output_files"), list):
        extracted = extract_viz_payload_from_content(content)
        if extracted is not None:
            enriched["data"] = extracted
    data = enriched.get("data")
    if isinstance(data, dict) and not isinstance(data.get("session_output_files"), list):
        hint_block = format_execute_code_viz_hint(data)
        if hint_block and hint_block not in content:
            enriched["content"] = content + hint_block
    return enriched


def build_financial_artifact_pointer(
    *,
    tool_name: str,
    call_id: str,
    arguments: dict[str, Any] | None = None,
    data: Any = None,
    content: str | None = None,
) -> str:
    summary: dict[str, Any] = {
        "artifact": True,
        "tool": tool_name,
        "call_id": call_id,
        "load_hint": f'dojo_tools.load_tool_result("{call_id}")',
        "rpc_hint": f"Re-fetch live data with dojo_tools.{tool_name}(...) inside execute_code when needed.",
    }
    if isinstance(data, dict):
        if data.get("ticker") or data.get("symbol"):
            summary["ticker"] = data.get("ticker") or data.get("symbol")
        if data.get("market"):
            summary["market"] = data["market"]
        rows = data.get("klines") or data.get("bars") or data.get("items")
        if isinstance(rows, list):
            summary["row_count"] = len(rows)
        if tool_name == "get_ticker_price_trends":
            summary.update(summarize_kline_artifact_data(data))
            summary["reuse_hint"] = "Do NOT call get_ticker_price_trends again for the latest bar; " "use latest_kline/as_of above or dojo_tools.load_tool_result(call_id)."
        if tool_name == "portfolio_read_detail":
            summary.update(summarize_portfolio_detail_artifact_data(data))
            summary["reuse_hint"] = (
                "Use positions[] above with portfolio_write_create_order(s) for portfolio "
                "mutations; do not use terminal or re-call portfolio_read_detail. Load the full "
                "result by call_id inside execute_code when more fields are required."
            )
    for key in ("ticker", "tickers", "market", "portfolio_id"):
        if arguments and arguments.get(key):
            summary[key] = arguments[key]
    schema_hint = get_tool_artifact_schema_hint(tool_name)
    if schema_hint:
        summary["schema_hint"] = schema_hint
        if isinstance(schema_hint.get("usage_notes"), str):
            summary["usage_notes"] = schema_hint["usage_notes"].strip()
        summary["parse_hint"] = schema_hint.get("pandas_example") or ("res = dojo_tools.load_tool_result(call_id); dojo_tools.tool_print(res)")
    viz_payload = data if isinstance(data, dict) else extract_viz_payload_from_content(content or "")
    viz_hint = get_viz_hint_for_payload(viz_payload)
    if viz_hint:
        summary["viz_hint"] = viz_hint
        mapping = viz_hint.get("mapping_hint") or viz_hint.get("kind") or "auto"
        summary["viz_build_hint"] = f'agent_viz_build({{"mapping_hint": "{mapping}", "kind": ' f'"{viz_hint.get("kind") or "auto"}", "data": <loaded payload>}})'
    return json.dumps(summary, ensure_ascii=False, indent=2)


class FinancialArtifactAdapter:
    def extract_data(self, tool_name: str, content: str, data: Any) -> Any:
        if data is not None:
            return data
        if tool_name in {"execute_code", "code_execution"}:
            return extract_viz_payload_from_content(content)
        return None

    def build_pointer(self, **kwargs: Any) -> str:
        return build_financial_artifact_pointer(**kwargs)

    def enrich_loaded_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        result = dict(payload)
        data = result.get("data")
        if not isinstance(data, dict):
            data = extract_viz_payload_from_content(str(result.get("content") or ""))
            if data is not None:
                result["data"] = data
        tool_name = str(result.get("tool_name") or "")
        result["schema_hint"] = get_tool_artifact_schema_hint(tool_name)
        result["viz_hint"] = get_viz_hint_for_payload(data if isinstance(data, dict) else None)
        return result


__all__ = [
    "FinancialArtifactAdapter",
    "build_financial_artifact_pointer",
    "enrich_execute_code_tool_result",
    "extract_viz_payload_from_content",
    "format_execute_code_viz_hint",
    "get_tool_artifact_schema_hint",
    "get_viz_hint_for_payload",
    "summarize_kline_artifact_data",
    "summarize_portfolio_detail_artifact_data",
]
