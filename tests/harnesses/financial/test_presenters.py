from __future__ import annotations

import pytest

from dojoagents.agent.models import ToolCall, ToolResult
from dojoagents.config.models import AgentsConfig, HarnessConfig
from dojoagents.harnesses.builder import HarnessBuilder
from dojoagents.harnesses.built_in.financial.config import FinancialHarnessConfig
from dojoagents.harnesses.built_in.financial.harness import FinancialHarness
from dojoagents.harnesses.built_in.financial.presenters import FinancialResultProjector
from dojoagents.harnesses.context import HarnessBuildContext
from dojoagents.harnesses.registries.presenters import PresenterRegistry
from dojoagents.tools.executor import ToolExecutor
from dojoagents.tools.registry import ToolRegistry, ToolSpec
from dojoagents.tools.sandbox import SandboxPolicy


def _capabilities(tmp_path):
    config = AgentsConfig(
        harness=HarnessConfig(
            config={
                "data_root": str(tmp_path / "data"),
                "portfolio_data_root": str(tmp_path / "portfolio"),
                "refresh_enabled": False,
            }
        )
    )
    context = HarnessBuildContext(config, config.harness.config, tmp_path, tmp_path, "api", None)
    harness = FinancialHarness(FinancialHarnessConfig.from_context(context))
    builder = HarnessBuilder(harness.descriptor)
    harness.configure(builder, context)
    return builder.build()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("name", "data", "expected_kind"),
    [
        ("get_ticker_realtime_quote", {"ticker": "AAPL", "market": "us", "last_price": 200}, "quote_card"),
        (
            "get_ticker_price_trends",
            {
                "ticker": "AAPL",
                "market": "us",
                "klines": [{"datetime": "2026-01-01", "open": 1, "high": 2, "low": 1, "close": 1}, {"datetime": "2026-01-02", "open": 1, "high": 2, "low": 1, "close": 2}],
            },
            "price_kline",
        ),
        ("get_market_overview", {"markets": {"us": {"listed_count": 1, "total_market_cap": 10, "weighted_pe": 20}}}, "kpi_row"),
        ("get_sector_movers", {"markets": {"us": {"gainers": [{"name_zh": "软件", "change_percent": 3}], "losers": []}}}, "hbar_rank"),
        ("portfolio_read_detail", {"id": "p-1", "name": "P", "positions": [{"ticker": "AAPL", "market": "us", "shares": 1}]}, "table"),
    ],
)
async def test_financial_presenters_map_domain_results(name, data, expected_kind, tmp_path):
    registry = PresenterRegistry(_capabilities(tmp_path).presenters)
    result = ToolResult("c1", name, True, data=data)
    presented = (await registry.present((result,), None))[0]
    assert any(block["kind"] == expected_kind for block in presented.viz_blocks)


@pytest.mark.asyncio
async def test_execute_code_presenter_extracts_viz_data_and_projector_preserves_facts(tmp_path):
    registry = PresenterRegistry(_capabilities(tmp_path).presenters)
    execute = ToolResult(
        "code-1",
        "execute_code",
        True,
        content='=== VIZ_DATA ===\n{"dates":["2026-01-01","2026-01-02"],"prices":[10,9]}',
        artifacts=[{"object_id": "obj-1", "media_type": "application/json"}],
    )
    write = ToolResult(
        "write-1",
        "portfolio_write_rename",
        True,
        data={"portfolio_id": "p-1"},
        metadata={"tool_arguments": {"portfolio_id": "p-1"}},
    )
    execute, write = await registry.present((execute, write), None)
    projection = FinancialResultProjector(registry).project((execute, write))

    assert "viz_hint" in execute.content
    assert execute.data["prices"] == [10, 9]
    assert write.resource_changes[0]["portfolio_id"] == "p-1"
    assert projection["artifacts"][0]["object_id"] == "obj-1"
    assert projection["resource_changes"][0]["resource"] == "portfolio"


@pytest.mark.asyncio
async def test_core_tool_executor_can_normalize_without_financial_presenter():
    async def quote(_args):
        return {"data": {"ticker": "AAPL", "market": "us", "last_price": 200}}

    tools = ToolRegistry()
    tools.register(ToolSpec("get_ticker_realtime_quote", "quote", {"type": "object"}, quote))
    executor = ToolExecutor(
        tools,
        SandboxPolicy(timeout_seconds=2),
        presenter_registry=None,
    )
    result = await executor.execute_one(ToolCall("c1", "get_ticker_realtime_quote", {"ticker": "AAPL"}), session_id="s-1")

    assert result.ok is True
    assert result.data["ticker"] == "AAPL"
    assert result.viz_blocks == []
    assert result.resource_changes == []
    assert result.metadata["tool_arguments"] == {"ticker": "AAPL"}


def test_generic_session_service_does_not_import_financial_presenters():
    from pathlib import Path

    source = Path("dojoagents/sessions/service.py").read_text(encoding="utf-8")
    assert "built_in.financial" not in source
