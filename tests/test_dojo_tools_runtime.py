from __future__ import annotations

import io
import json
from contextlib import redirect_stdout

from dojoagents.harnesses.built_in.financial.presenters.artifacts import (
    build_financial_artifact_pointer as build_artifact_pointer_message,
)
from dojoagents.harnesses.built_in.financial.presenters.schema_hints import get_tool_schema_hint
from dojoagents.tools.dojo_tools_runtime import (
    format_execute_code_error_hint,
    tool_columns,
    tool_concat,
    tool_df,
    tool_merge,
    tool_meta,
    tool_pick,
    tool_print,
)


def _overview_res() -> dict:
    hint = get_tool_schema_hint("get_market_overview")
    return {
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


def test_tool_meta_returns_scalars_only() -> None:
    meta = tool_meta(_overview_res())
    assert meta["as_of"] == "2026-07-07"
    assert meta["window_start"] == "2026-07-01"
    assert "markets" not in meta
    assert "benchmarks" not in meta


def test_tool_df_benchmarks_supports_column_subset() -> None:
    res = _overview_res()
    df = tool_df(res, "benchmarks")
    subset = tool_pick(df, ["symbol", "name_zh", "price", "change_percent"])
    assert subset.iloc[0]["name_zh"] == "上证指数"
    assert subset.iloc[0]["symbol"] == "000001.SH"


def test_tool_pick_skips_missing_columns() -> None:
    res = _overview_res()
    df = tool_df(res, "benchmarks")
    picked = tool_pick(df, ["symbol", "missing_col", "price"])
    assert list(picked.columns) == ["symbol", "price"]


def test_tool_columns_for_multi_table() -> None:
    res = _overview_res()
    bench_cols = tool_columns(res, "benchmarks")
    assert "symbol" in bench_cols
    assert "name_zh" in bench_cols


def test_tool_print_user_script_pattern(capsys) -> None:
    """Regression: agent script that hard-picks benchmark columns must not KeyError."""
    res = _overview_res()
    tool_print(res, title="=== 主要指数表现 ===", table="benchmarks", columns=["symbol", "name_zh", "price", "change_percent"])
    out = capsys.readouterr().out
    assert "000001.SH" in out
    assert "上证指数" in out


def test_sector_movers_tool_print() -> None:
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
                            "member_count": 42,
                        }
                    ],
                    "losers": [],
                }
            },
        },
        "schema_hint": hint,
    }
    buf = io.StringIO()
    with redirect_stdout(buf):
        tool_print(res, table=None, columns=["side", "rank", "name_zh", "change_percent", "member_count"], limit=20)
    out = buf.getvalue()
    assert "半导体" in out
    assert "gainers" in out or "3.2" in out


def test_format_execute_code_error_hint_appends_column_guidance() -> None:
    tb = "KeyError: \"['name_zh'] not in index\""
    code = "df = dojo_tools.tool_df(res)\nprint(df[['name_zh']])"
    enriched = format_execute_code_error_hint(tb, code)
    assert "execute_code hints" in enriched
    assert "tool_pick" in enriched


def test_artifact_pointer_parse_hint_uses_tool_print() -> None:
    message = build_artifact_pointer_message(
        tool_name="get_market_overview",
        call_id="mo-1",
        data={"days": 1, "markets": {}, "benchmarks": {}},
    )
    payload = json.loads(message)
    assert "tool_print" in payload["parse_hint"]


def test_sector_search_tool_print() -> None:
    hint = get_tool_schema_hint("search_sector_taxonomy")
    assert hint is not None
    res = {
        "ok": True,
        "data": {
            "query": "银行",
            "count": 1,
            "items": [
                {
                    "sector_path_id": "1/2/3",
                    "level1_id": "1",
                    "level2_id": "2",
                    "level3_id": "3",
                    "breadcrumb_zh": "金融 > 银行 > 商业银行",
                    "level3_name_zh": "商业银行",
                    "match_score": 95,
                    "matched_level": "L3",
                    "next_call": {"tool": "filter_sector_constituents", "arguments": {}},
                }
            ],
            "best_match": {"level3_id": "3"},
        },
        "schema_hint": hint,
    }
    buf = io.StringIO()
    with redirect_stdout(buf):
        tool_print(res)
    out = buf.getvalue()
    assert "query: 银行" in out
    assert "商业银行" in out
    assert "1/2/3" in out


def test_sector_search_works_without_schema_hint_fallback() -> None:
    res = {
        "ok": True,
        "data": {
            "query": "能源",
            "count": 1,
            "items": [
                {
                    "sector_path_id": "4/5/6",
                    "breadcrumb_zh": "能源 > 公用事业",
                    "match_score": 80,
                    "next_call": {"tool": "filter_sector_constituents", "arguments": {}},
                }
            ],
        },
    }
    df = tool_df(res)
    assert df.iloc[0]["sector_path_id"] == "4/5/6"
    assert "next_call" not in df.columns


def test_sector_search_schema_registered() -> None:
    hint = get_tool_schema_hint("search_sector_taxonomy")
    assert hint is not None
    assert hint["default_table"] == "items"
    assert "breadcrumb_zh" in hint["row_fields"]


def test_market_overview_pandas_example_mentions_multi_table() -> None:
    hint = get_tool_schema_hint("get_market_overview")
    assert hint is not None
    assert "tool_print" in hint["pandas_example"]
    assert "benchmarks" in hint["pandas_example"]


def test_artifact_pointer_for_sector_search_includes_schema() -> None:
    message = build_artifact_pointer_message(
        tool_name="search_sector_taxonomy",
        call_id="search-1",
        data={"query": "银行", "count": 1, "items": [{"sector_path_id": "1/2/3"}]},
    )
    payload = json.loads(message)
    assert payload["schema_hint"]["default_table"] == "items"
    assert "tool_print" in payload["parse_hint"]


def test_tool_concat_merges_multi_market_constituents() -> None:
    hint = get_tool_schema_hint("filter_sector_constituents")

    def _res(market: str, ticker: str) -> dict:
        return {
            "ok": True,
            "data": {
                "market": market,
                "count": 1,
                "items": [{"ticker": ticker, "market": market, "name": {"zh": ticker, "en": ticker}}],
            },
            "schema_hint": hint,
        }

    df = tool_concat([_res("cn", "600000"), _res("hk", "0700")])
    assert len(df) == 2
    assert set(df["market"]) == {"cn", "hk"}


def test_tool_merge_joins_constituents_and_financials() -> None:
    const_hint = get_tool_schema_hint("filter_sector_constituents")
    res_a = {
        "ok": True,
        "data": {"items": [{"ticker": "AAPL", "market": "us", "pe": 30}]},
        "schema_hint": const_hint,
    }
    res_b = {
        "ok": True,
        "data": {"items": [{"ticker": "AAPL", "market": "us", "window_change_percent": 5.2}]},
        "schema_hint": const_hint,
    }
    merged = tool_merge(res_a, res_b, on=["ticker", "market"])
    assert merged.iloc[0]["ticker"] == "AAPL"
    assert merged.iloc[0]["pe"] == 30
    assert merged.iloc[0]["window_change_percent"] == 5.2
