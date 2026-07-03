from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dojoagents.agent.session_repository import _atomic_write_json
from dojoagents.logging import get_logger

LOGGER = get_logger(__name__)

ARTIFACT_PERSIST_THRESHOLD_CHARS = 5000
ARTIFACT_KEEP_FULL_CONTENT_TOOLS = frozenset(
    {
        "execute_code",
        "code_execution",
    }
)
_CALL_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,128}$")
_VIZ_DATA_MARKER = re.compile(r"===\s*VIZ_DATA\s*===", re.IGNORECASE)

# Hints for execute_code when large tool outputs are replaced by artifact pointers.
TOOL_ARTIFACT_SCHEMA_HINTS: dict[str, dict[str, Any]] = {
    "get_ticker_price_trends": {
        "rows_key": "klines",
        "row_fields": ["datetime", "open", "high", "low", "close", "volume"],
        "pandas_example": (
            "df = pd.DataFrame(hermes_tools.tool_rows(res)); "
            "df['date'] = pd.to_datetime(df['datetime'])"
        ),
    },
    "dojo.sdk.stock.kline": {
        "rows_key": "klines",
        "row_fields": ["datetime", "open", "high", "low", "close", "volume"],
        "pandas_example": "df = pd.DataFrame(hermes_tools.tool_rows(res))",
    },
    "get_ticker_financials": {
        "rows_key": "items",
        "pandas_example": "df = pd.DataFrame(hermes_tools.tool_rows(res))",
    },
    "screen_market_stocks": {
        "rows_key": "items",
        "pandas_example": "df = pd.DataFrame(hermes_tools.tool_rows(res))",
    },
    "filter_sector_constituents": {
        "rows_key": "items",
        "pandas_example": "df = pd.DataFrame(hermes_tools.tool_rows(res))",
    },
}


def get_tool_artifact_schema_hint(tool_name: str) -> dict[str, Any] | None:
    hint = TOOL_ARTIFACT_SCHEMA_HINTS.get(str(tool_name or "").strip())
    return dict(hint) if hint else None


def extract_viz_payload_from_content(content: str) -> dict[str, Any] | None:
    text = str(content or "")
    match = _VIZ_DATA_MARKER.search(text)
    if not match:
        return None
    after = text[match.end() :].strip()
    start = after.find("{")
    if start < 0:
        return None
    blob = after[start:]
    try:
        payload = json.loads(blob)
        return payload if isinstance(payload, dict) else None
    except json.JSONDecodeError:
        for line in blob.splitlines():
            candidate = line.strip()
            if not candidate.startswith("{"):
                continue
            try:
                payload = json.loads(candidate)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                return payload
    return None


def get_viz_hint_for_payload(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None

    dates = payload.get("dates")
    prices = payload.get("prices")
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
    if not hint:
        return ""
    return "\n\n--- viz_hint ---\n" + json.dumps(hint, ensure_ascii=False, indent=2)


def enrich_execute_code_tool_result(result: dict[str, Any]) -> dict[str, Any]:
    """Parse VIZ_DATA from execute_code stdout and attach structured data + viz hints."""
    enriched = dict(result)
    content = str(enriched.get("content") or "")
    payload = enriched.get("data")
    if not isinstance(payload, dict):
        payload = extract_viz_payload_from_content(content)
        if payload is not None:
            enriched["data"] = payload
    elif not (isinstance(payload.get("dates"), list) and isinstance(payload.get("prices"), list)):
        extracted = extract_viz_payload_from_content(content)
        if extracted is not None:
            payload = extracted
            enriched["data"] = payload

    if isinstance(enriched.get("data"), dict):
        hint_block = format_execute_code_viz_hint(enriched["data"])
        if hint_block and hint_block not in content:
            enriched["content"] = content + hint_block
    return enriched


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _validate_call_id(call_id: str) -> str:
    text = str(call_id or "").strip()
    if not text or not _CALL_ID_PATTERN.fullmatch(text):
        raise ValueError(f"invalid tool result call_id: {call_id!r}")
    return text


def _validate_session_id(session_id: str) -> str:
    text = str(session_id or "").strip()
    if not text or "/" in text or "\\" in text or text in {".", ".."}:
        raise ValueError(f"invalid session id: {session_id!r}")
    return text


class ToolResultArtifactStore:
    """Persist large tool outputs for execute_code via hermes_tools.load_tool_result."""

    def __init__(self, sessions_root: str | Path) -> None:
        self.sessions_root = Path(sessions_root).expanduser().resolve()

    def _artifact_dir(self, session_id: str) -> Path:
        safe_session = _validate_session_id(session_id)
        return self.sessions_root / safe_session / "tool_results"

    def artifact_path(self, session_id: str, call_id: str) -> Path:
        safe_call_id = _validate_call_id(call_id)
        return self._artifact_dir(session_id) / f"{safe_call_id}.json"

    def save(
        self,
        *,
        session_id: str,
        call_id: str,
        tool_name: str,
        arguments: dict[str, Any] | None,
        content: str,
        data: Any = None,
        ok: bool = True,
        truncated: bool = False,
    ) -> Path:
        path = self.artifact_path(session_id, call_id)
        payload = {
            "schema_version": 1,
            "session_id": _validate_session_id(session_id),
            "call_id": _validate_call_id(call_id),
            "tool_name": tool_name,
            "arguments": dict(arguments or {}),
            "ok": ok,
            "truncated": truncated,
            "content": content,
            "data": data,
            "created_at": _utc_now(),
        }
        _atomic_write_json(path, payload)
        return path

    def load(self, session_id: str, call_id: str) -> dict[str, Any] | None:
        path = self.artifact_path(session_id, call_id)
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            LOGGER.exception("Failed to read tool result artifact: %s", path)
            return None

    def list_summaries(self, session_id: str) -> list[dict[str, Any]]:
        directory = self._artifact_dir(session_id)
        if not directory.exists():
            return []
        rows: list[dict[str, Any]] = []
        for path in sorted(directory.glob("*.json")):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                LOGGER.exception("Failed to read tool result artifact summary: %s", path)
                continue
            if not isinstance(payload, dict):
                continue
            rows.append(
                {
                    "call_id": payload.get("call_id") or path.stem,
                    "tool_name": payload.get("tool_name"),
                    "created_at": payload.get("created_at"),
                    "truncated": bool(payload.get("truncated")),
                    "content_chars": len(str(payload.get("content") or "")),
                }
            )
        rows.sort(key=lambda item: str(item.get("created_at") or ""), reverse=True)
        return rows


def build_artifact_pointer_message(
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
        "load_hint": f'hermes_tools.load_tool_result("{call_id}")',
        "rpc_hint": f"Re-fetch live data with hermes_tools.{tool_name}(...) inside execute_code when needed.",
    }
    if isinstance(data, dict):
        if data.get("ticker") or data.get("symbol"):
            summary["ticker"] = data.get("ticker") or data.get("symbol")
        if data.get("market"):
            summary["market"] = data.get("market")
        klines = data.get("klines") or data.get("bars")
        if isinstance(klines, list):
            summary["row_count"] = len(klines)
        items = data.get("items")
        if isinstance(items, list):
            summary["row_count"] = len(items)
    if arguments:
        for key in ("ticker", "tickers", "market", "portfolio_id"):
            if key in arguments and arguments[key]:
                summary[key] = arguments[key]
    schema_hint = get_tool_artifact_schema_hint(tool_name)
    if schema_hint:
        summary["schema_hint"] = schema_hint
        summary["parse_hint"] = (
            "res = hermes_tools.load_tool_result(call_id); "
            "rows = hermes_tools.tool_rows(res); "
            f"df = pd.DataFrame(rows)  # rows_key={schema_hint.get('rows_key')!r}"
        )

    viz_payload: dict[str, Any] | None = data if isinstance(data, dict) else None
    if viz_payload is None and content:
        viz_payload = extract_viz_payload_from_content(content)
    viz_hint = get_viz_hint_for_payload(viz_payload)
    if viz_hint:
        summary["viz_hint"] = viz_hint
        summary["viz_build_hint"] = (
            'agent_viz_build({"mapping_hint": '
            f'"{viz_hint.get("mapping_hint") or viz_hint.get("kind") or "auto"}", '
            f'"kind": "{viz_hint.get("kind") or "auto"}", '
            '"data": <payload from load_tool_result / VIZ_DATA>})'
        )
    return json.dumps(summary, ensure_ascii=False, indent=2)
