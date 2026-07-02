from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Mapping

EXECUTE_CODE_TOOL_NAMES = frozenset({"execute_code", "code_execution"})

_OHLC_FIELD_LITERAL = re.compile(
    r'["\'](?:close|open|high|low|last_price|adj_close)["\']\s*:\s*-?\d+(?:\.\d+)?',
    re.IGNORECASE,
)
_DATETIME_OHLC_ROW = re.compile(
    r"\{[^{}]*"
    r'["\'](?:datetime|date|bar_time|time)["\']\s*:\s*["\'][^"\']+["\']'
    r"[^{}]*"
    r'["\'](?:close|open|high|low)["\']\s*:\s*-?\d+(?:\.\d+)?'
    r"[^{}]*\}",
    re.IGNORECASE | re.DOTALL,
)
_INLINE_SERIES_ASSIGN = re.compile(
    r"(?:klines|bars|ohlc|prices|price_data|klines_data|fin_rows|financials_data)\s*=\s*\[\s*\{",
    re.IGNORECASE,
)
_SUSPICIOUS_PRICE_DECIMAL = re.compile(r":\s*-?\d+\.\d{6,}\s*[,}\]]")
_HERMES_FETCH = re.compile(
    r"hermes_tools\.(?:get_ticker_price_trends|get_ticker_financials|get_ticker_realtime_quote|"
    r"load_tool_result|call_tool|tool_json|dojo_sdk\w*|list_tool_results)\s*\(",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ExecuteCodeInlineDataFinding:
    reason: str
    ohlc_field_literals: int = 0
    datetime_ohlc_rows: int = 0
    suspicious_decimals: int = 0
    inline_series_assign: bool = False


def _strip_python_comments(code: str) -> str:
    return re.sub(r"#.*$", "", code, flags=re.MULTILINE)


def detect_hardcoded_market_data(code: str) -> ExecuteCodeInlineDataFinding | None:
    text = _strip_python_comments(code or "")
    if not text.strip():
        return None

    ohlc_field_literals = len(_OHLC_FIELD_LITERAL.findall(text))
    datetime_ohlc_rows = len(_DATETIME_OHLC_ROW.findall(text))
    suspicious_decimals = len(_SUSPICIOUS_PRICE_DECIMAL.findall(text))
    inline_series_assign = _INLINE_SERIES_ASSIGN.search(text) is not None

    if datetime_ohlc_rows >= 2:
        return ExecuteCodeInlineDataFinding(
            reason=f"found {datetime_ohlc_rows} inline datetime/OHLC dict rows",
            ohlc_field_literals=ohlc_field_literals,
            datetime_ohlc_rows=datetime_ohlc_rows,
            suspicious_decimals=suspicious_decimals,
            inline_series_assign=inline_series_assign,
        )

    if ohlc_field_literals >= 3:
        return ExecuteCodeInlineDataFinding(
            reason=f"found {ohlc_field_literals} inline OHLC price literals",
            ohlc_field_literals=ohlc_field_literals,
            datetime_ohlc_rows=datetime_ohlc_rows,
            suspicious_decimals=suspicious_decimals,
            inline_series_assign=inline_series_assign,
        )

    if inline_series_assign and ohlc_field_literals >= 1:
        return ExecuteCodeInlineDataFinding(
            reason="found inline kline/price list assigned from dict literals",
            ohlc_field_literals=ohlc_field_literals,
            datetime_ohlc_rows=datetime_ohlc_rows,
            suspicious_decimals=suspicious_decimals,
            inline_series_assign=True,
        )

    if ohlc_field_literals >= 2 and suspicious_decimals >= 1:
        return ExecuteCodeInlineDataFinding(
            reason="found multiple OHLC literals with suspicious high-precision prices",
            ohlc_field_literals=ohlc_field_literals,
            datetime_ohlc_rows=datetime_ohlc_rows,
            suspicious_decimals=suspicious_decimals,
            inline_series_assign=inline_series_assign,
        )

    return None


def uses_hermes_data_fetch(code: str) -> bool:
    return _HERMES_FETCH.search(code or "") is not None


def check_execute_code_inline_data(
    tool_name: str,
    args: Mapping[str, Any] | None,
) -> tuple[bool, str]:
    if tool_name not in EXECUTE_CODE_TOOL_NAMES:
        return False, ""

    code = args.get("code") if isinstance(args, Mapping) else None
    if not isinstance(code, str) or not code.strip():
        return False, ""

    finding = detect_hardcoded_market_data(code)
    if finding is None:
        return False, ""

    if uses_hermes_data_fetch(code) and finding.datetime_ohlc_rows < 2 and finding.ohlc_field_literals < 3:
        return False, ""

    message = (
        f"Blocked {tool_name}: hardcoded market data detected ({finding.reason}). "
        "Do NOT inline OHLC/price rows in Python. Fetch real data inside the script via "
        "`import hermes_tools` — e.g. "
        "`hermes_tools.get_ticker_price_trends({'ticker': '0700', 'market': 'hk'})` or "
        "`hermes_tools.load_tool_result('<call_id>')`, then parse with `hermes_tools.tool_json(res)`."
    )
    return True, message
