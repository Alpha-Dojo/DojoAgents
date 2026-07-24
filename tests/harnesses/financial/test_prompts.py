from __future__ import annotations

import ast
from pathlib import Path

import pytest

from dojoagents.agent.models import ChatRequest
from dojoagents.config.models import AgentsConfig, HarnessConfig
from dojoagents.harnesses.builder import HarnessBuilder
from dojoagents.harnesses.built_in.financial.context import (
    FinancialContext,
    FinancialContextError,
    FinancialRequestContextCodec,
)
from dojoagents.harnesses.built_in.financial.harness import FinancialHarness
from dojoagents.harnesses.built_in.financial.config import FinancialHarnessConfig
from dojoagents.harnesses.context import HarnessBuildContext, HarnessSessionContext, HarnessTurnContext
from dojoagents.harnesses.decisions import ToolControlDecision
from dojoagents.harnesses.runtime import HarnessRuntime
from dojoagents.harnesses.state import HarnessSessionState
from dojoagents.sessions.models import SessionPrincipal


def _request(*, channel="dashboard", context=None, quant=None, metadata=None, message="分析 AAPL"):
    return ChatRequest(
        message,
        session_id="s-1",
        principal=SessionPrincipal("alice"),
        channel=channel,
        context=context or {},
        quant=quant,
        metadata=metadata or {"locale": "zh"},
    )


def _turn(request):
    return HarnessTurnContext(
        request,
        HarnessSessionContext(request.principal, request.session_id, HarnessSessionState()),
    )


def _harness(tmp_path):
    root = AgentsConfig(
        harness=HarnessConfig(
            config={
                "data_root": str(tmp_path / "financial"),
                "portfolio_data_root": str(tmp_path / "portfolio"),
                "refresh_enabled": False,
            }
        )
    )
    context = HarnessBuildContext(
        root,
        root.harness.config,
        tmp_path,
        tmp_path,
        "dashboard",
        None,
    )
    harness = FinancialHarness(FinancialHarnessConfig.from_context(context))
    builder = HarnessBuilder(harness.descriptor)
    harness.configure(builder, context)
    return harness, builder.build()


def test_financial_context_decodes_typed_and_legacy_quant_payloads():
    codec = FinancialRequestContextCodec()
    current = codec.decode(
        _request(
            context={
                "financial": {
                    "market": "us",
                    "symbols": ["aapl", "MSFT"],
                    "timeframe": "1d",
                    "currency": "usd",
                    "freshness": "latest_available",
                }
            }
        )
    )
    legacy = codec.decode(
        _request(
            quant={
                "market": "stock",
                "symbols": ["BTC-USD"],
                "timeframe": "1d",
                "currency": "USD",
                "data_freshness": "latest_available",
            }
        )
    )

    assert current == FinancialContext("us", ("AAPL", "MSFT"), "1d", "USD", "latest_available")
    assert legacy.freshness == "latest_available"
    assert "symbols: AAPL, MSFT" in current.prompt_block()


@pytest.mark.parametrize(
    ("payload", "field"),
    [
        ({"market": "mars", "symbols": ["AAPL"], "timeframe": "1d"}, "market"),
        ({"market": "us", "symbols": [""], "timeframe": "1d"}, "symbols.0"),
        ({"market": "us", "symbols": ["AAPL"], "timeframe": "tomorrow"}, "timeframe"),
        ({"market": "us", "symbols": ["AAPL"], "timeframe": "1d", "currency": "US"}, "currency"),
        ({"market": "us", "symbols": ["AAPL"], "timeframe": "1d", "freshness": "whenever"}, "freshness"),
    ],
)
def test_financial_context_errors_include_typed_field_paths(payload, field):
    with pytest.raises(FinancialContextError) as captured:
        FinancialRequestContextCodec().decode(_request(context={"financial": payload}))
    assert captured.value.field_path == f"context.financial.{field}"
    assert captured.value.code == "invalid_financial_context"


@pytest.mark.asyncio
async def test_financial_prompt_graph_orders_blocks_and_filters_dashboard_channel(tmp_path):
    _harness_instance, capabilities = _harness(tmp_path)

    async def allow(call, context):
        return ToolControlDecision("allow", "test")

    runtime = HarnessRuntime(
        capabilities,
        core_safety_prompt="CORE SAFETY",
        core_tool_authorizer=allow,
        revalidate_tool_call=lambda call: None,
    )
    dashboard = _turn(
        _request(
            context={"financial": {"market": "us", "symbols": ["AAPL"], "timeframe": "1d"}},
            metadata={
                "locale": "zh",
                "active_task_prompt": "## ACTIVE TASK: research",
                "history": [{"role": "user", "content": "创建组合"}],
                "_turn_intent_result": {
                    "continue_unfinished": False,
                    "prior_task_summary": "",
                    "last_turn_status": "complete",
                },
            },
            message="买入 AAPL",
        )
    )
    blocks = await runtime.before_turn(dashboard)
    ids = [block.block_id for block in blocks]

    assert ids[0] == "core.safety"
    assert ids[1:] == [
        "financial.identity",
        "core.temporal",
        "financial.instructions",
        "financial.memory",
        "financial.request-context",
        "financial.dashboard-tools",
        "financial.dashboard-visualization",
        "financial.task-context",
        "financial.turn-scope",
    ]
    text = "\n".join(block.content for block in blocks)
    assert "full-market finance analysis agent" in text
    assert "Quant context" in text
    assert "Dashboard Tool Calling Protocol" in text
    assert "viz_blocks" in text
    assert "禁止" in text and "agent_viz_build" in text
    assert "ACTIVE TASK: research" in text
    assert "当前任务" in text
    assert dashboard.turn_state.values["request_contexts"]["financial.context-codec"].market == "us"

    cli_blocks = await runtime.before_turn(_turn(_request(channel="cli")))
    cli_ids = {block.block_id for block in cli_blocks}
    assert "financial.dashboard-tools" not in cli_ids
    assert "financial.dashboard-visualization" not in cli_ids


def test_financial_harness_registers_memory_and_skill_sources_explicitly(tmp_path):
    harness_instance, capabilities = _harness(tmp_path)
    assert [spec.component_id for spec in capabilities.memories] == ["financial.memory.skill-summary"]
    assert harness_instance.memory_provider.generated_skill_dir == Path("~/.dojo/skills/generated").expanduser()
    assert any(spec.component_id == "financial.skills.built-in" for spec in capabilities.skills)
    assert any(spec.component_id == "financial.skills.user" for spec in capabilities.skills)
    assert any(spec.component_id == "financial.skills.generated" for spec in capabilities.skills)


def test_agent_core_sources_do_not_import_financial_or_quant_modules():
    repo = Path(__file__).resolve().parents[3]
    forbidden = (
        "dojoagents.quant",
        "dojoagents.harnesses.built_in.financial",
        "dojoagents.dashboard.services.financial",
    )
    for relative in ("dojoagents/agent/models.py", "dojoagents/agent/loop.py"):
        tree = ast.parse((repo / relative).read_text(encoding="utf-8"))
        imports = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.append(node.module)
        assert not [name for name in imports if name.startswith(forbidden)], relative
