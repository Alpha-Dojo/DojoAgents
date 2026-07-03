from __future__ import annotations

import json

import pytest

from dojoagents.agent.models import ToolCall
from dojoagents.agent.tool_result_artifacts import (
    ARTIFACT_PERSIST_THRESHOLD_CHARS,
    ToolResultArtifactStore,
    build_artifact_pointer_message,
)
from dojoagents.tools.code_execution_tool import get_code_execution_spec, handle_code_execution
from dojoagents.tools.executor import ToolExecutor
from dojoagents.tools.hermes_tools_stub import build_hermes_tools_stub_code, hermes_function_name
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

    code = (
        "import hermes_tools\n"
        "res = hermes_tools.terminal('echo rpc-ok')\n"
        "print('ScriptOut:', res.get('content', '').strip())\n"
    )

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
        "import hermes_tools\n"
        "res1 = hermes_tools.terminal('echo ok-1')\n"
        "res2 = hermes_tools.terminal('echo ok-2')\n"
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
        "import hermes_tools\n"
        "res = hermes_tools.get_ticker_price_trends({'ticker': '0700', 'market': 'hk'})\n"
        "data = hermes_tools.tool_json(res)\n"
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
    registry.register(get_code_execution_spec(registry, policy, artifact_store=store))

    code = (
        "import hermes_tools\n"
        "res = hermes_tools.load_tool_result('call-kline')\n"
        "data = hermes_tools.tool_json(res)\n"
        "print('Loaded:', data['klines'][0]['close'])\n"
    )
    result = await handle_code_execution(
        {"code": code},
        registry,
        policy,
        artifact_store=store,
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
    registry.register(get_code_execution_spec(registry, policy, artifact_store=store))

    code = (
        "import hermes_tools\n"
        "res = hermes_tools.load_tool_result('call-sndk')\n"
        "rows = hermes_tools.tool_rows(res)\n"
        "print('Rows:', len(rows), 'FirstClose:', rows[0]['close'])\n"
    )
    result = await handle_code_execution(
        {"code": code},
        registry,
        policy,
        artifact_store=store,
        agent_session_id="session-1",
    )
    assert "Rows: 2 FirstClose: 194.5" in result["content"]


def test_hermes_stub_maps_dotted_tool_names():
    assert hermes_function_name("get_ticker_price_trends") == "get_ticker_price_trends"
    assert hermes_function_name("dojo.sdk.stock.kline") == "dojo_sdk_stock_kline"
    stub = build_hermes_tools_stub_code(
        socket_path="/tmp/test.sock",
        tool_names=["get_ticker_price_trends", "dojo.sdk.stock.kline"],
    )
    assert "def get_ticker_price_trends(" in stub
    assert "def dojo_sdk_stock_kline(" in stub
    assert "def load_tool_result(" in stub
    assert "def tool_rows(" in stub


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
    executor = ToolExecutor(registry, policy, artifact_store=store)
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

    executor = ToolExecutor(registry, policy, artifact_store=store)
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
    assert "tool_rows" in payload["parse_hint"]
