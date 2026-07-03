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
    return json.dumps(summary, ensure_ascii=False, indent=2)
