from __future__ import annotations

import json

import pytest

from dojoagents.agent.tool_result_artifacts import build_artifact_pointer_message, get_tool_artifact_schema_hint
from dojoagents.agent.tool_schema_hints import (
    TOOL_NAME_ALIASES,
    infer_schema_hint_from_model,
    get_tool_schema_hint,
)
from dojoagents.dashboard.schemas.domain_api import (
    MarketOverviewResponse,
    SectorMoversResponse,
    StockScreenResponse,
    TickerFinancialsResponseV1,
    TickerPriceTrendsResponseV1,
)
from dojoagents.tools.dojo_tools_stub import build_dojo_tools_stub_code


def _stub_namespace() -> dict:
    namespace: dict = {}
    exec(build_dojo_tools_stub_code(socket_path="/tmp/test.sock", tool_names=[]), namespace)
    return namespace


def test_market_overview_hint_exposes_table_specs() -> None:
    hint = get_tool_schema_hint("get_market_overview")
    assert hint is not None
    assert hint["shape"] == "nested"
    assert "markets" in hint["tables"]
    assert "benchmarks" in hint["tables"]
    assert hint["tables"]["markets"]["type"] == "dict_records"
    assert hint["pandas_example"] == "df = pd.DataFrame(dojo_tools.tool_table(res))"


def test_sector_movers_hint_exposes_side_list_table() -> None:
    hint = get_tool_schema_hint("get_sector_movers")
    assert hint is not None
    assert hint["default_table"] == "sectors"
    spec = hint["tables"]["sectors"]
    assert spec["type"] == "dict_side_lists"
    assert "rank" in hint["row_fields"]
    assert "name_zh" in hint["row_fields"]
    assert "change_percent" in hint["row_fields"]


def test_tabular_tools_get_table_spec() -> None:
    screen_hint = get_tool_schema_hint("screen_market_stocks")
    assert screen_hint is not None
    assert screen_hint["shape"] == "tabular"
    assert screen_hint["default_table"] == "items"
    assert screen_hint["tables"]["items"]["type"] == "list"

    kline_hint = get_tool_schema_hint("get_ticker_price_trends")
    assert kline_hint is not None
    assert kline_hint["default_table"] == "klines"
    assert "datetime" in kline_hint["row_fields"]


def test_alias_resolves_kline_tool() -> None:
    assert TOOL_NAME_ALIASES["dojo.sdk.stock.kline"] == "get_ticker_price_trends"
    hint = get_tool_schema_hint("dojo.sdk.stock.kline")
    assert hint is not None
    assert hint["default_table"] == "klines"


def test_financials_table_tries_items_then_indicators() -> None:
    hint = get_tool_schema_hint("get_ticker_financials")
    assert hint is not None
    assert hint["tables"]["rows"]["type"] == "first_list"
    assert hint["tables"]["rows"]["paths"] == ["items", "indicators"]


def test_artifact_pointer_parse_hint_uses_tool_table() -> None:
    message = build_artifact_pointer_message(
        tool_name="get_market_overview",
        call_id="mo-1",
        data={"days": 1, "markets": {}, "benchmarks": {}},
    )
    payload = json.loads(message)
    assert "tool_table" in payload["parse_hint"]


def test_tool_table_sector_movers_from_schema() -> None:
    ns = _stub_namespace()
    hint = get_tool_schema_hint("get_sector_movers")
    res = {
        "ok": True,
        "data": {
            "days": 1,
            "markets": {
                "cn": {
                    "gainers": [
                        {
                            "concept_code": "semis",
                            "name": {"zh": "半导体", "en": "Semiconductors"},
                            "change_percent": 3.2,
                            "avg_market_cap": 1e10,
                            "member_count": 42,
                        }
                    ],
                    "losers": [],
                }
            },
        },
        "schema_hint": hint,
    }
    rows = ns["tool_table"](res)
    assert len(rows) == 1
    assert rows[0]["market"] == "cn"
    assert rows[0]["side"] == "gainers"
    assert rows[0]["rank"] == 1
    assert rows[0]["name_zh"] == "半导体"
    assert rows[0]["change_percent"] == 3.2


def test_tool_rows_delegates_to_tool_table() -> None:
    ns = _stub_namespace()
    hint = get_tool_schema_hint("screen_market_stocks")
    res = {
        "ok": True,
        "data": {"items": [{"ticker": "AAPL", "market": "us"}]},
        "schema_hint": hint,
    }
    rows = ns["tool_rows"](res)
    assert rows[0]["ticker"] == "AAPL"


@pytest.mark.parametrize(
    ("model", "default_table"),
    [
        (StockScreenResponse, "items"),
        (TickerPriceTrendsResponseV1, "klines"),
    ],
)
def test_infer_schema_hint_from_model(model, default_table) -> None:
    hint = infer_schema_hint_from_model(model)
    assert hint["shape"] == "tabular"
    assert hint["default_table"] == default_table


def test_infer_market_overview_from_model() -> None:
    hint = infer_schema_hint_from_model(MarketOverviewResponse)
    assert hint["shape"] == "nested"
    assert set(hint["tables"]) == {"markets", "benchmarks"}


def test_infer_sector_movers_from_model() -> None:
    hint = infer_schema_hint_from_model(SectorMoversResponse)
    assert hint["tables"]["sectors"]["type"] == "dict_side_lists"


def test_financials_first_list_fallback() -> None:
    ns = _stub_namespace()
    hint = get_tool_schema_hint("get_ticker_financials")
    batch = {
        "ok": True,
        "data": {"items": [{"ticker": "AAPL", "market": "us"}]},
        "schema_hint": hint,
    }
    single = {
        "ok": True,
        "data": {"ticker": "AAPL", "indicators": [{"metric": "pe", "value": 30}]},
        "schema_hint": hint,
    }
    assert ns["tool_table"](batch)[0]["ticker"] == "AAPL"
    assert ns["tool_table"](single)[0]["metric"] == "pe"
