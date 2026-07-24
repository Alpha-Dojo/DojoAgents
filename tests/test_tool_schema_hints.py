from __future__ import annotations

import json

import pytest

from dojoagents.harnesses.built_in.financial.presenters.artifacts import (
    build_financial_artifact_pointer as build_artifact_pointer_message,
)
from dojoagents.harnesses.built_in.financial.presenters.schema_hints import (
    TOOL_NAME_ALIASES,
    infer_schema_hint_from_model,
    get_tool_schema_hint,
)
from dojoagents.dashboard.schemas.domain_api import (
    MarketOverviewResponse,
    SectorMoversResponse,
    StockScreenResponse,
    TickerPriceTrendsResponseV1,
)
from dojoagents.tools.dojo_tools_runtime import (
    tool_df,
    tool_meta,
    tool_pick,
    tool_table,
)


def test_market_overview_hint_exposes_table_specs() -> None:
    hint = get_tool_schema_hint("get_market_overview")
    assert hint is not None
    assert hint["shape"] == "nested"
    assert "markets" in hint["tables"]
    assert "benchmarks" in hint["tables"]
    assert hint["tables"]["markets"]["type"] == "dict_records"
    assert "tool_print" in hint["pandas_example"]
    assert "benchmarks" in hint["pandas_example"]
    assert "window_mode" in hint["usage_notes"]
    assert "window_start" in hint["top_level_keys"]


def test_sector_movers_hint_exposes_side_list_table() -> None:
    hint = get_tool_schema_hint("get_sector_movers")
    assert hint is not None
    assert hint["default_table"] == "sectors"
    spec = hint["tables"]["sectors"]
    assert spec["type"] == "dict_side_lists"
    assert "rank" in hint["row_fields"]
    assert "name_zh" in hint["row_fields"]
    assert "change_percent" in hint["row_fields"]
    assert "member_count<5" in hint["usage_notes"]


def test_tabular_tools_get_table_spec() -> None:
    screen_hint = get_tool_schema_hint("screen_market_stocks")
    assert screen_hint is not None
    assert screen_hint["shape"] == "tabular"
    assert screen_hint["default_table"] == "items"
    assert screen_hint["tables"]["items"]["type"] == "list"
    assert "name" in screen_hint["tables"]["items"]["expand_bilingual"]

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


def test_artifact_pointer_parse_hint_uses_tool_print() -> None:
    message = build_artifact_pointer_message(
        tool_name="get_market_overview",
        call_id="mo-1",
        data={"days": 1, "markets": {}, "benchmarks": {}},
    )
    payload = json.loads(message)
    assert "tool_print" in payload["parse_hint"]
    assert "window_mode" in payload["usage_notes"]


def test_tool_table_sector_movers_from_schema() -> None:
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
    rows = tool_table(res)
    assert len(rows) == 1
    assert rows[0]["market"] == "cn"
    assert rows[0]["side"] == "gainers"
    assert rows[0]["rank"] == 1
    assert rows[0]["name_zh"] == "半导体"
    assert rows[0]["change_percent"] == 3.2


def test_tool_rows_delegates_to_tool_table() -> None:
    from dojoagents.tools.dojo_tools_runtime import tool_rows

    hint = get_tool_schema_hint("screen_market_stocks")
    res = {
        "ok": True,
        "data": {"items": [{"ticker": "AAPL", "market": "us"}]},
        "schema_hint": hint,
    }
    rows = tool_rows(res)
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
    assert tool_table(batch)[0]["ticker"] == "AAPL"
    assert tool_table(single)[0]["metric"] == "pe"


def test_tool_table_expands_bilingual_for_screen_market_stocks() -> None:
    hint = get_tool_schema_hint("screen_market_stocks")
    res = {
        "ok": True,
        "data": {
            "as_of": "2026-07-07",
            "universe_count": 5000,
            "match_count": 1,
            "items": [
                {
                    "ticker": "0700",
                    "market": "hk",
                    "name": {"zh": "腾讯", "en": "Tencent"},
                    "last_price": 400.0,
                    "pe": 20.0,
                }
            ],
        },
        "schema_hint": hint,
    }
    rows = tool_table(res)
    assert rows[0]["name_zh"] == "腾讯"
    assert rows[0]["name_en"] == "Tencent"
    assert "name" not in rows[0]


def test_tool_df_and_tool_meta() -> None:
    hint = get_tool_schema_hint("screen_market_stocks")
    res = {
        "ok": True,
        "data": {
            "as_of": "2026-07-07",
            "universe_count": 5000,
            "match_count": 1,
            "items": [
                {
                    "ticker": "0700",
                    "market": "hk",
                    "name": {"zh": "腾讯", "en": "Tencent"},
                    "last_price": 400.0,
                    "pe": 20.0,
                }
            ],
        },
        "schema_hint": hint,
    }
    meta = tool_meta(res)
    assert meta["as_of"] == "2026-07-07"
    assert meta["universe_count"] == 5000
    assert meta["match_count"] == 1

    df = tool_df(res)
    assert "name_zh" in df.columns
    assert set(df.columns).issubset(set(hint["row_fields"]))
    assert df.iloc[0]["name_zh"] == "腾讯"
    assert df.iloc[0]["ticker"] == "0700"


def test_row_fields_dedupe_group_key_when_model_has_same_field() -> None:
    hint = get_tool_schema_hint("get_market_overview")
    bench_fields = hint["tables"]["benchmarks"]["row_fields"]
    assert bench_fields.count("market") == 1
    market_fields = hint["tables"]["markets"]["row_fields"]
    assert market_fields.count("market") == 1


def test_tool_df_uses_per_table_row_fields_for_market_overview() -> None:
    hint = get_tool_schema_hint("get_market_overview")
    res = {
        "ok": True,
        "data": {
            "days": 5,
            "window_start": "2026-07-01",
            "window_end": "2026-07-07",
            "as_of": "2026-07-07",
            "markets": {
                "cn": {
                    "listed_count": 5000,
                    "total_market_cap": 1e13,
                    "weighted_pe": 15.2,
                    "simple_pe": 14.1,
                    "pe_sample_count": 4000,
                },
            },
            "benchmarks": {
                "cn": [
                    {
                        "market": "cn",
                        "symbol": "000001.SH",
                        "name": {"zh": "上证指数", "en": "SSE Composite"},
                        "price": 3200.5,
                        "change_percent": 1.2,
                    },
                ],
            },
        },
        "schema_hint": hint,
    }
    df_markets = tool_df(res, "markets")
    assert list(df_markets.columns) == hint["tables"]["markets"]["row_fields"]
    assert "listed_count" in df_markets.columns

    df_bench = tool_df(res, "benchmarks")
    expected = hint["tables"]["benchmarks"]["row_fields"]
    assert list(df_bench.columns) == [c for c in expected if c in df_bench.columns]
    subset = tool_pick(df_bench, ["symbol", "name_zh", "price", "change_percent"])
    assert subset.iloc[0]["name_zh"] == "上证指数"
    assert subset.iloc[0]["symbol"] == "000001.SH"
