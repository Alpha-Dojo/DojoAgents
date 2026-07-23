from __future__ import annotations

import json

import pytest

from dojoagents.agent.models import ToolCall
from dojoagents.tools.artifacts import (
    ARTIFACT_PERSIST_THRESHOLD_CHARS,
    ToolResultArtifactStore,
)
from dojoagents.harnesses.built_in.financial.presenters.artifacts import (
    FinancialArtifactAdapter,
    build_financial_artifact_pointer as build_artifact_pointer_message,
)
from dojoagents.tools.code_execution_tool import get_code_execution_spec, handle_code_execution
from dojoagents.tools.executor import ToolExecutor
from dojoagents.tools.dojo_tools_stub import build_dojo_tools_stub_code, hermes_function_name
from dojoagents.tools.registry import ToolRegistry, ToolSpec
from dojoagents.tools.sandbox import SandboxPolicy
from dojoagents.tools.terminal_tool import get_terminal_spec


@pytest.mark.asyncio
async def test_code_execution_calls_terminal_via_rpc():
    registry = ToolRegistry()
    policy = SandboxPolicy()
    registry.register(get_terminal_spec(policy))
    registry.register(get_code_execution_spec(registry, policy))
    executor = ToolExecutor(registry, policy)

    code = "import dojo_tools\n" "res = dojo_tools.terminal('echo rpc-ok')\n" "print('ScriptOut:', res.get('content', '').strip())\n"

    tool_call = ToolCall(id="tc-code", name="execute_code", arguments={"code": code})
    result = await executor.execute_one(tool_call)
    assert result.ok
    assert "ScriptOut: rpc-ok" in result.content


@pytest.mark.asyncio
async def test_code_execution_limit_reached():
    registry = ToolRegistry()
    policy = SandboxPolicy()
    registry.register(get_terminal_spec(policy))

    code = (
        "import dojo_tools\n"
        "res1 = dojo_tools.terminal('echo ok-1')\n"
        "res2 = dojo_tools.terminal('echo ok-2')\n"
        "print('R1:', res1.get('ok'))\n"
        "print('R2:', res2.get('ok'))\n"
        "print('Err:', res2.get('error'))\n"
    )

    res = await handle_code_execution({"code": code}, registry, policy, max_tool_calls=1)
    output = res["content"]
    assert "R1: True" in output
    assert "R2: False" in output
    assert "Tool call limit reached" in output


@pytest.mark.asyncio
async def test_code_execution_calls_registered_dashboard_tool_via_rpc(tmp_path):
    registry = ToolRegistry()
    policy = SandboxPolicy()

    async def price_trends(args: dict) -> dict:
        payload = {
            "ticker": args.get("ticker"),
            "market": args.get("market"),
            "klines": [{"datetime": "2026-06-30", "close": 512.0}],
        }
        return {"content": json.dumps(payload), "data": payload}

    registry.register(
        ToolSpec(
            name="get_ticker_price_trends",
            description="mock price trends",
            parameters={"type": "object", "properties": {}},
            handler=price_trends,
        )
    )
    registry.register(get_code_execution_spec(registry, policy))

    code = (
        "import dojo_tools\n"
        "res = dojo_tools.get_ticker_price_trends({'ticker': '0700', 'market': 'hk'})\n"
        "data = dojo_tools.tool_json(res)\n"
        "print('Close:', data['klines'][0]['close'])\n"
    )
    result = await handle_code_execution({"code": code}, registry, policy)
    assert "Close: 512.0" in result["content"]


@pytest.mark.asyncio
async def test_code_execution_load_tool_result_artifact(tmp_path):
    registry = ToolRegistry()
    policy = SandboxPolicy()
    store = ToolResultArtifactStore(tmp_path)
    store.save(
        session_id="session-1",
        call_id="call-kline",
        tool_name="get_ticker_price_trends",
        arguments={"ticker": "0700", "market": "hk"},
        content=json.dumps({"klines": [{"datetime": "2026-06-30", "close": 520.0}]}),
        data={"klines": [{"datetime": "2026-06-30", "close": 520.0}]},
    )
    registry.register(
        get_code_execution_spec(
            registry,
            policy,
            artifact_store=store,
            artifact_adapter=FinancialArtifactAdapter(),
        )
    )

    code = "import dojo_tools\n" "res = dojo_tools.load_tool_result('call-kline')\n" "data = dojo_tools.tool_json(res)\n" "print('Loaded:', data['klines'][0]['close'])\n"
    result = await handle_code_execution(
        {"code": code},
        registry,
        policy,
        artifact_store=store,
        artifact_adapter=FinancialArtifactAdapter(),
        agent_session_id="session-1",
    )
    assert "Loaded: 520.0" in result["content"]


@pytest.mark.asyncio
async def test_code_execution_tool_rows_from_artifact(tmp_path):
    registry = ToolRegistry()
    policy = SandboxPolicy()
    store = ToolResultArtifactStore(tmp_path)
    rows = [
        {"datetime": "2025-01-06", "open": 193.98, "high": 195.0, "low": 192.0, "close": 194.5},
        {"datetime": "2025-01-07", "open": 194.5, "high": 196.0, "low": 193.0, "close": 195.2},
    ]
    store.save(
        session_id="session-1",
        call_id="call-sndk",
        tool_name="get_ticker_price_trends",
        arguments={"ticker": "SNDK", "market": "us"},
        content=json.dumps({"ticker": "SNDK", "klines": rows}),
        data={"ticker": "SNDK", "klines": rows},
    )
    registry.register(
        get_code_execution_spec(
            registry,
            policy,
            artifact_store=store,
            artifact_adapter=FinancialArtifactAdapter(),
        )
    )

    code = (
        "import dojo_tools\n" "res = dojo_tools.load_tool_result('call-sndk')\n" "rows = dojo_tools.tool_rows(res)\n" "print('Rows:', len(rows), 'FirstClose:', rows[0]['close'])\n"
    )
    result = await handle_code_execution(
        {"code": code},
        registry,
        policy,
        artifact_store=store,
        artifact_adapter=FinancialArtifactAdapter(),
        agent_session_id="session-1",
    )
    assert "Rows: 2 FirstClose: 194.5" in result["content"]


def test_hermes_stub_maps_dotted_tool_names():
    assert hermes_function_name("get_ticker_price_trends") == "get_ticker_price_trends"
    assert hermes_function_name("dojo.sdk.stock.kline") == "dojo_sdk_stock_kline"
    stub = build_dojo_tools_stub_code(
        socket_path="/tmp/test.sock",
        tool_names=["get_ticker_price_trends", "dojo.sdk.stock.kline"],
    )
    assert "def get_ticker_price_trends(" in stub
    assert "def dojo_sdk_stock_kline(" in stub
    assert "def load_tool_result(" in stub
    assert "tool_print" in stub
    assert "dojo_tools_runtime" in stub


@pytest.mark.asyncio
async def test_code_execution_bootstrap_provides_pandas_without_user_import():
    registry = ToolRegistry()
    policy = SandboxPolicy()
    registry.register(get_code_execution_spec(registry, policy))

    code = "print('HasPandas:', pd is not None)\n"
    result = await handle_code_execution({"code": code}, registry, policy)
    assert "HasPandas: True" in result["content"]


@pytest.mark.asyncio
async def test_code_execution_tool_df_from_screen_artifact(tmp_path):
    registry = ToolRegistry()
    policy = SandboxPolicy()
    store = ToolResultArtifactStore(tmp_path)
    store.save(
        session_id="session-1",
        call_id="call-screen",
        tool_name="screen_market_stocks",
        arguments={"market": "hk"},
        content=json.dumps(
            {
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
            }
        ),
        data={
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
    )
    registry.register(
        get_code_execution_spec(
            registry,
            policy,
            artifact_store=store,
            artifact_adapter=FinancialArtifactAdapter(),
        )
    )

    code = (
        "res = dojo_tools.load_tool_result('call-screen')\n"
        "meta = dojo_tools.tool_meta(res)\n"
        "df = dojo_tools.tool_df(res)\n"
        "print('AsOf:', meta.get('as_of'))\n"
        "print('NameZh:', df.iloc[0]['name_zh'])\n"
    )
    result = await handle_code_execution(
        {"code": code},
        registry,
        policy,
        artifact_store=store,
        artifact_adapter=FinancialArtifactAdapter(),
        agent_session_id="session-1",
    )
    assert "AsOf: 2026-07-07" in result["content"]
    assert "NameZh: 腾讯" in result["content"]


@pytest.mark.asyncio
async def test_code_execution_agent_market_overview_script(tmp_path):
    """Regression: full agent script pattern (meta + multi-table + column pick)."""
    registry = ToolRegistry()
    policy = SandboxPolicy()
    store = ToolResultArtifactStore(tmp_path)
    overview = {
        "days": 5,
        "window_start": "2026-07-01",
        "window_end": "2026-07-07",
        "as_of": "2026-07-07",
        "markets": {"cn": {"listed_count": 5000, "total_market_cap": 1e13, "pe_sample_count": 4000}},
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
    }
    sectors = {
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
    }
    store.save(
        session_id="session-1",
        call_id="call-overview",
        tool_name="get_market_overview",
        arguments={"days": 5},
        content=json.dumps(overview),
        data=overview,
    )
    store.save(
        session_id="session-1",
        call_id="call-sectors",
        tool_name="get_sector_movers",
        arguments={"days": 1},
        content=json.dumps(sectors),
        data=sectors,
    )
    registry.register(
        get_code_execution_spec(
            registry,
            policy,
            artifact_store=store,
            artifact_adapter=FinancialArtifactAdapter(),
        )
    )

    code = (
        "res1 = dojo_tools.load_tool_result('call-overview')\n"
        "meta = dojo_tools.tool_meta(res1)\n"
        "print('数据时间:', meta.get('as_of'))\n"
        "print('统计区间:', meta.get('window_start'), '~', meta.get('window_end'))\n"
        "df_bench = dojo_tools.tool_df(res1, 'benchmarks')\n"
        "print(dojo_tools.tool_pick(df_bench, ['symbol', 'name_zh', 'price', 'change_percent']).to_string(index=False))\n"
        "res2 = dojo_tools.load_tool_result('call-sectors')\n"
        "df_sectors = dojo_tools.tool_df(res2)\n"
        "print(dojo_tools.tool_pick(df_sectors, ['side', 'rank', 'name_zh', 'change_percent', 'member_count']).head(20).to_string(index=False))\n"
    )
    result = await handle_code_execution(
        {"code": code},
        registry,
        policy,
        artifact_store=store,
        artifact_adapter=FinancialArtifactAdapter(),
        agent_session_id="session-1",
    )
    assert result["metadata"]["exit_code"] == 0
    assert "2026-07-07" in result["content"]
    assert "000001.SH" in result["content"]
    assert "上证指数" in result["content"]
    assert "半导体" in result["content"]


@pytest.mark.asyncio
async def test_code_execution_market_overview_benchmarks_subset(tmp_path):
    registry = ToolRegistry()
    policy = SandboxPolicy()
    store = ToolResultArtifactStore(tmp_path)
    payload = {
        "days": 5,
        "window_start": "2026-07-01",
        "window_end": "2026-07-07",
        "as_of": "2026-07-07",
        "markets": {"cn": {"listed_count": 5000, "total_market_cap": 1e13, "pe_sample_count": 4000}},
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
    }
    store.save(
        session_id="session-1",
        call_id="call-overview",
        tool_name="get_market_overview",
        arguments={"days": 5},
        content=json.dumps(payload),
        data=payload,
    )
    registry.register(
        get_code_execution_spec(
            registry,
            policy,
            artifact_store=store,
            artifact_adapter=FinancialArtifactAdapter(),
        )
    )

    code = (
        "res = dojo_tools.load_tool_result('call-overview')\n"
        "meta = dojo_tools.tool_meta(res)\n"
        "df_bench = dojo_tools.tool_df(res, 'benchmarks')\n"
        "print('Window:', meta.get('window_start'), meta.get('window_end'))\n"
        "print(df_bench[['symbol', 'name_zh', 'price', 'change_percent']].to_string(index=False))\n"
    )
    result = await handle_code_execution(
        {"code": code},
        registry,
        policy,
        artifact_store=store,
        artifact_adapter=FinancialArtifactAdapter(),
        agent_session_id="session-1",
    )
    assert "Window: 2026-07-01 2026-07-07" in result["content"]
    assert "000001.SH" in result["content"]
    assert "上证指数" in result["content"]


@pytest.mark.asyncio
async def test_executor_persists_large_tool_result_and_replaces_llm_content(tmp_path):
    registry = ToolRegistry()
    policy = SandboxPolicy()
    store = ToolResultArtifactStore(tmp_path)

    async def big_payload(_: dict) -> dict:
        rows = [{"datetime": f"2026-01-{(i % 28) + 1:02d}", "close": float(i), "open": float(i)} for i in range(300)]
        payload = {"ticker": "0700", "market": "hk", "klines": rows}
        content = json.dumps(payload)
        assert len(content) >= ARTIFACT_PERSIST_THRESHOLD_CHARS
        return {"content": content, "data": payload}

    registry.register(
        ToolSpec(
            name="get_ticker_price_trends",
            description="mock",
            parameters={"type": "object", "properties": {}},
            handler=big_payload,
        )
    )
    executor = ToolExecutor(
        registry,
        policy,
        artifact_store=store,
        artifact_adapter=FinancialArtifactAdapter(),
    )
    result = await executor.execute_one(
        ToolCall(id="call-big", name="get_ticker_price_trends", arguments={"ticker": "0700"}),
        session_id="session-abc",
    )
    assert result.ok
    assert '"artifact": true' in result.content
    assert result.data is not None
    assert isinstance(result.data, dict)
    assert len(result.data.get("klines") or []) == 300
    loaded = store.load("session-abc", "call-big")
    assert loaded is not None
    assert loaded["tool_name"] == "get_ticker_price_trends"


@pytest.mark.asyncio
async def test_executor_keeps_execute_code_stdout_when_large(tmp_path):
    registry = ToolRegistry()
    policy = SandboxPolicy()
    store = ToolResultArtifactStore(tmp_path)

    stdout = "GOOG summary\n" + ("analysis row\n" * 900)
    assert len(stdout) >= ARTIFACT_PERSIST_THRESHOLD_CHARS

    async def fake_execute(_: dict) -> dict:
        return {"content": stdout, "metadata": {"exit_code": 0}}

    registry.register(
        ToolSpec(
            name="execute_code",
            description="mock execute_code",
            parameters={"type": "object", "properties": {}},
            handler=fake_execute,
        )
    )

    executor = ToolExecutor(
        registry,
        policy,
        artifact_store=store,
        artifact_adapter=FinancialArtifactAdapter(),
    )
    result = await executor.execute_one(
        ToolCall(id="call-exec", name="execute_code", arguments={"code": "print('x')"}),
        session_id="session-exec",
    )

    assert result.ok
    assert "GOOG summary" in result.content
    assert '"artifact": true' not in result.content
    loaded = store.load("session-exec", "call-exec")
    assert loaded is not None
    assert loaded["tool_name"] == "execute_code"
    assert "GOOG summary" in loaded["content"]


def test_build_artifact_pointer_message_includes_call_id():
    message = build_artifact_pointer_message(
        tool_name="get_ticker_price_trends",
        call_id="abc-123",
        arguments={"ticker": "0700", "market": "hk"},
        data={"ticker": "0700", "klines": [{}] * 10},
    )
    payload = json.loads(message)
    assert payload["artifact"] is True
    assert payload["call_id"] == "abc-123"
    assert "load_tool_result" in payload["load_hint"]
    assert payload["schema_hint"]["rows_key"] == "klines"
    assert "datetime" in payload["schema_hint"]["row_fields"]
    assert "dojo_tools.tool_" in payload["parse_hint"]


def test_build_artifact_pointer_message_includes_latest_kline_summary() -> None:
    message = build_artifact_pointer_message(
        tool_name="get_ticker_price_trends",
        call_id="nvda-1",
        data={
            "ticker": "NVDA",
            "market": "us",
            "as_of": "2026-07-03",
            "period_end": "2026-07-03",
            "klines": [
                {"datetime": "2026-07-01", "open": 190, "high": 195, "low": 188, "close": 192},
                {"datetime": "2026-07-03", "open": 197, "high": 200, "low": 192, "close": 194.83},
            ],
        },
    )
    payload = json.loads(message)
    assert payload["latest_kline"]["datetime"] == "2026-07-03"
    assert payload["latest_kline"]["close"] == pytest.approx(194.83)
    assert payload["as_of"] == "2026-07-03"
    assert "reuse_hint" in payload
    assert "Do NOT call get_ticker_price_trends again" in payload["reuse_hint"]


def test_build_artifact_pointer_message_includes_portfolio_positions() -> None:
    message = build_artifact_pointer_message(
        tool_name="portfolio_read_detail",
        call_id="folio-1",
        arguments={"portfolio_id": "p-default"},
        data={
            "id": "p-default",
            "name": "我的默认组合",
            "kind": "manual",
            "eval_summary": {
                "candidate_count": 0,
                "position_count": 1,
                "position_count_by_market": {"us": 0, "cn": 0, "hk": 1},
            },
            "positions": [
                {
                    "ticker": "0700.HK",
                    "name": "腾讯控股",
                    "name_zh": "腾讯控股",
                    "market": "hk",
                    "shares": 2300.0,
                    "weight": 1.0,
                }
            ],
            "performance": {"dates": ["2026-01-01"] * 500, "portfolio": [1.0] * 500},
        },
    )
    payload = json.loads(message)
    assert payload["artifact"] is True
    assert payload["portfolio_id"] == "p-default"
    assert payload["eval_summary"]["position_count"] == 1
    assert len(payload["positions"]) == 1
    assert payload["positions"][0]["ticker"] == "0700.HK"
    assert payload["positions"][0]["shares"] == pytest.approx(2300.0)
    assert payload["schema_hint"]["rows_key"] == "positions"
    assert "reuse_hint" in payload
    assert "terminal" in payload["reuse_hint"]
    assert "portfolio_write_create_order" in payload["reuse_hint"]


def test_build_artifact_pointer_message_includes_viz_hint_for_drawdown_payload() -> None:
    message = build_artifact_pointer_message(
        tool_name="execute_code",
        call_id="exec-1",
        data={
            "dates": ["2025-01-02", "2025-01-03"],
            "prices": [150.0, 145.0],
            "drawdown_pcts": [0.0, -3.3],
            "summary": {"ticker": "SNDK", "max_drawdown_pct": 3.3},
        },
    )
    payload = json.loads(message)
    assert payload["viz_hint"]["mapping_hint"] == "drawdown_analysis"
    assert "agent_viz_build" in payload["viz_build_hint"]


def test_extract_viz_payload_from_execute_code_stdout() -> None:
    from dojoagents.harnesses.built_in.financial.presenters.artifacts import (
        enrich_execute_code_tool_result,
        extract_viz_payload_from_content,
        format_execute_code_viz_hint,
    )

    stdout = (
        "=== SNDK summary ===\nMax drawdown 17.5%\n\n"
        "=== VIZ_DATA ===\n"
        '{"dates":["2025-01-02","2025-01-03"],"prices":[150.0,145.0],"drawdown_pcts":[0.0,-3.3],'
        '"summary":{"ticker":"SNDK","max_drawdown_pct":17.5}}'
    )
    payload = extract_viz_payload_from_content(stdout)
    assert payload is not None
    assert payload["summary"]["ticker"] == "SNDK"
    assert "drawdown_analysis" in format_execute_code_viz_hint(payload)

    enriched = enrich_execute_code_tool_result({"content": stdout})
    assert enriched["data"]["summary"]["max_drawdown_pct"] == 17.5
    assert "--- viz_hint ---" in enriched["content"]


def test_market_overview_schema_hint_uses_nested_pandas_example() -> None:
    from dojoagents.harnesses.built_in.financial.presenters.artifacts import (
        build_financial_artifact_pointer as build_artifact_pointer_message,
        get_tool_artifact_schema_hint,
    )

    hint = get_tool_artifact_schema_hint("get_market_overview")
    assert hint is not None
    assert hint["shape"] == "nested"
    assert "tool_print" in hint["pandas_example"]

    message = build_artifact_pointer_message(
        tool_name="get_market_overview",
        call_id="overview-1",
        data={
            "days": 5,
            "as_of": "2026-07-03",
            "markets": {"us": {"listed_count": 100, "total_market_cap": 1e13}},
            "benchmarks": {"us": [{"symbol": "SPY", "change_percent": 1.2}]},
        },
    )
    payload = json.loads(message)
    assert payload["schema_hint"]["shape"] == "nested"
    assert "tool_print" in payload["parse_hint"]


def test_tool_rows_error_includes_table_guidance_for_nested_payload() -> None:
    from dojoagents.tools.dojo_tools_runtime import tool_rows

    res = {
        "ok": True,
        "data": {
            "days": 5,
            "markets": {"us": {"listed_count": 1}},
            "benchmarks": {"us": []},
        },
        "schema_hint": {
            "shape": "nested",
            "pandas_example": "data = dojo_tools.tool_json(res); markets_df = ...",
        },
    }
    with pytest.raises(KeyError, match="tool_df"):
        tool_rows(res)


@pytest.mark.asyncio
async def test_load_tool_result_includes_tool_name_and_schema_hint(tmp_path) -> None:
    from dojoagents.tools.code_execution_tool import AsyncCodeExecutionRPC
    from dojoagents.harnesses.built_in.financial.presenters.artifacts import (
        FinancialArtifactAdapter,
    )

    store = ToolResultArtifactStore(tmp_path)
    store.save(
        session_id="sess-1",
        call_id="overview-1",
        tool_name="get_market_overview",
        arguments={"days": 5},
        content='{"days": 5}',
        data={"days": 5, "markets": {}, "benchmarks": {}},
        ok=True,
        truncated=False,
    )
    server = AsyncCodeExecutionRPC(
        "/tmp/test.sock",
        tool_registry=type("R", (), {"get": lambda self, name: None})(),
        artifact_store=store,
        artifact_adapter=FinancialArtifactAdapter(),
        agent_session_id="sess-1",
    )
    loaded = server._load_tool_result({"call_id": "overview-1"})
    assert loaded["ok"] is True
    assert loaded["tool_name"] == "get_market_overview"
    assert loaded["schema_hint"]["shape"] == "nested"
