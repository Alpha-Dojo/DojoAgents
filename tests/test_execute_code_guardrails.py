from __future__ import annotations

import json

import pytest

from dojoagents.harnesses.built_in.financial.policies.execute_code_guardrails import (
    ExecuteCodeClassification,
    classify_execute_code,
    execute_code_guardrail_from_classification,
)
from dojoagents.agent.guardrails import ToolCallGuardrailController, ToolGuardrailDecision, toolguard_synthetic_result
from dojoagents.agent.models import LLMResult
from dojoagents.agent.providers import StaticLLMProvider


def _classification_json(
    *,
    allow_execution: bool,
    block_reason: str = "none",
    explanation: str = "",
) -> str:
    return json.dumps(
        {
            "allow_execution": allow_execution,
            "block_reason": block_reason,
            "explanation": explanation,
        }
    )


@pytest.mark.asyncio
async def test_classifier_blocks_hardcoded_market_data() -> None:
    code = """
klines_data = [
    {"datetime": "2026-06-26", "close": 356.36313339782514},
    {"datetime": "2026-06-29", "close": 363.78277122838953},
]
df = __import__("pandas").DataFrame(klines_data)
"""
    provider = StaticLLMProvider(
        [
            LLMResult(
                content=_classification_json(
                    allow_execution=False,
                    block_reason="hardcoded_market_data",
                    explanation="Inline OHLC rows detected.",
                )
            )
        ]
    )
    classification = await classify_execute_code(
        code,
        "plot NVDA",
        provider,
        model="test-model",
    )
    blocked, message, code_name = execute_code_guardrail_from_classification("execute_code", classification)
    assert blocked is True
    assert code_name == "execute_code_inline_market_data"
    assert "hardcoded" in message.lower() or "OHLC" in message


@pytest.mark.asyncio
async def test_classifier_blocks_inline_rows_even_with_dojo_tools_import() -> None:
    code = """
import dojo_tools

klines_data = [
    {"datetime": "2026-06-26", "close": 356.36313339782514},
    {"datetime": "2026-06-29", "close": 363.78277122838953},
]
res = dojo_tools.get_ticker_price_trends({"ticker": "0700", "market": "hk"})
df = __import__("pandas").DataFrame(klines_data)
"""
    provider = StaticLLMProvider(
        [
            LLMResult(
                content=_classification_json(
                    allow_execution=False,
                    block_reason="hardcoded_market_data",
                    explanation="Inline OHLC rows detected despite dojo_tools import.",
                )
            )
        ]
    )
    classification = await classify_execute_code(
        code,
        "plot 0700",
        provider,
        model="test-model",
    )
    blocked, message, code_name = execute_code_guardrail_from_classification("execute_code", classification)
    assert blocked is True
    assert code_name == "execute_code_inline_market_data"
    assert "hardcoded" in message.lower() or "OHLC" in message


@pytest.mark.asyncio
async def test_classifier_allows_dojo_tools_fetch_script() -> None:
    code = """
import dojo_tools
payload = dojo_tools.tool_json(dojo_tools.load_tool_result("abc"))
df = payload["klines"]
df["ma20"] = df["close"].rolling(20).mean()
"""
    provider = StaticLLMProvider([LLMResult(content=_classification_json(allow_execution=True))])
    classification = await classify_execute_code(code, "compute MA20", provider, model="test-model")
    blocked, _, code_name = execute_code_guardrail_from_classification("execute_code", classification)
    assert blocked is False
    assert code_name == "allow"


@pytest.mark.asyncio
async def test_classifier_blocks_presentation_only_knowledge_graph_doc() -> None:
    code = """
node_type_taxonomy = {"semiconductor": {"name": "晶圆代工"}}
print("=" * 72)
print("方案A")
for key, row in node_type_taxonomy.items():
    print(key, row["name"])
"""
    provider = StaticLLMProvider(
        [
            LLMResult(
                content=_classification_json(
                    allow_execution=False,
                    block_reason="presentation_only",
                    explanation="Script only prints a schema document.",
                )
            )
        ]
    )
    classification = await classify_execute_code(
        code,
        "知识图谱节点类型设计",
        provider,
        model="test-model",
    )
    blocked, message, code_name = execute_code_guardrail_from_classification("execute_code", classification)
    assert blocked is True
    assert code_name == "execute_code_presentation_only"
    assert "presentation" in message.lower() or "ASCII" in message


@pytest.mark.asyncio
async def test_classifier_caches_by_code_hash() -> None:
    provider = StaticLLMProvider([LLMResult(content=_classification_json(allow_execution=True))])
    metadata: dict = {}
    await classify_execute_code("print(1)", "msg", provider, model="test-model", request_metadata=metadata)
    await classify_execute_code("print(1)", "msg", provider, model="test-model", request_metadata=metadata)
    assert len(provider.calls) == 1


def test_loop_style_guardrail_decision_for_inline_data() -> None:
    blocked, message, code_name = execute_code_guardrail_from_classification(
        "execute_code",
        ExecuteCodeClassification(
            allow_execution=False,
            block_reason="hardcoded_market_data",
            explanation="Inline OHLC rows detected.",
        ),
    )
    assert blocked is True
    assert code_name == "execute_code_inline_market_data"

    decision = ToolGuardrailDecision(
        action="block",
        code=code_name,
        message=message,
        tool_name="execute_code",
    )
    synth = toolguard_synthetic_result(decision)
    payload = json.loads(synth["content"])
    assert payload["guardrail"]["code"] == "execute_code_inline_market_data"


def test_non_execute_code_tools_skip_classifier_path() -> None:
    decision = ToolCallGuardrailController().before_call("portfolio_read_detail", {"portfolio_id": "p-1"})
    assert decision.action == "allow"
