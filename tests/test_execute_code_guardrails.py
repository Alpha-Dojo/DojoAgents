from __future__ import annotations

import json

from dojoagents.agent.execute_code_guardrails import (
    check_execute_code_inline_data,
    detect_hardcoded_market_data,
)
from dojoagents.agent.guardrails import ToolCallGuardrailController, toolguard_synthetic_result


def test_detect_hardcoded_klines_from_user_example():
    code = """
import pandas as pd

klines_data = [
    {"datetime": "2026-06-26", "close": 356.36313339782514},
    {"datetime": "2026-06-29", "close": 363.78277122838953},
    {"datetime": "2026-06-30", "close": 371.19187898973496},
]
df = pd.DataFrame(klines_data)
"""
    finding = detect_hardcoded_market_data(code)
    assert finding is not None
    assert finding.datetime_ohlc_rows >= 2


def test_allows_dojo_tools_fetch_without_inline_rows():
    code = """
import pandas as pd
import dojo_tools

res = dojo_tools.get_ticker_price_trends({"ticker": "0700", "market": "hk"})
payload = dojo_tools.tool_json(res)
df = pd.DataFrame(payload["klines"])
print(df["close"].iloc[-1])
"""
    assert detect_hardcoded_market_data(code) is None


def test_allows_load_tool_result_path():
    code = """
import dojo_tools
payload = dojo_tools.tool_json(dojo_tools.load_tool_result("call-123"))
"""
    assert detect_hardcoded_market_data(code) is None


def test_blocks_even_with_hermes_import_when_inline_rows_present():
    code = """
import dojo_tools
klines_data = [
    {"datetime": "2026-06-26", "close": 356.36313339782514},
    {"datetime": "2026-06-29", "close": 363.78277122838953},
]
res = dojo_tools.get_ticker_price_trends({"ticker": "0700", "market": "hk"})
"""
    blocked, message = check_execute_code_inline_data("execute_code", {"code": code})
    assert blocked is True
    assert "hardcoded market data" in message


def test_guardrail_controller_blocks_execute_code():
    controller = ToolCallGuardrailController()
    code = """
prices = [
    {"date": "2026-01-01", "close": 100.1},
    {"date": "2026-01-02", "close": 101.2},
]
"""
    decision = controller.before_call("execute_code", {"code": code})
    assert decision.action == "block"
    assert decision.code == "execute_code_inline_market_data"

    synth = toolguard_synthetic_result(decision)
    payload = json.loads(synth["content"])
    assert payload["guardrail"]["code"] == "execute_code_inline_market_data"


def test_guardrail_allows_computation_on_fetched_columns():
    code = """
import dojo_tools
payload = dojo_tools.tool_json(dojo_tools.load_tool_result("abc"))
df = payload["klines"]
df["ma20"] = df["close"].rolling(20).mean()
"""
    decision = ToolCallGuardrailController().before_call("execute_code", {"code": code})
    assert decision.action == "allow"
