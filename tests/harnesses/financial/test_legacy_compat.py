from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from dojoagents.agent.models import ChatRequest
from dojoagents.harnesses.built_in.financial.compat import FinancialLegacyBehavior
from dojoagents.harnesses.built_in.financial.context import (
    FinancialContext,
    FinancialContextError,
)
from dojoagents.sessions.models import SessionPrincipal


class _MemoryManager:
    def build_system_prompt(self) -> str:
        return ""

    async def prefetch_all(self, _query: str, *, session_id: str) -> str:
        return ""


class _ExtensionRegistry:
    def __init__(self) -> None:
        self.contexts: list[Any] = []

    def prompt_context(self, request_context: Any) -> str:
        self.contexts.append(request_context)
        return "extension context"


def _request(*, context: dict[str, Any] | None = None, quant: Any = None) -> ChatRequest:
    return ChatRequest(
        "analyze",
        principal=SessionPrincipal("local"),
        session_id="financial-compat",
        channel="cli",
        context=context or {},
        quant=quant,
        metadata={
            "_turn_intent_result": {
                "continue_unfinished": False,
                "prior_task_summary": "",
                "last_turn_status": "complete",
            }
        },
    )


def _loop() -> SimpleNamespace:
    return SimpleNamespace(
        task_manager=None,
        skill_manager=SimpleNamespace(prompt_block=lambda **_kwargs: ""),
        memory_manager=_MemoryManager(),
        extension_registry=_ExtensionRegistry(),
        usage_llm_provider=object(),
    )


@pytest.mark.anyio
@pytest.mark.parametrize(
    "quant",
    [
        {
            "market": "us",
            "symbols": ["aapl"],
            "timeframe": "1d",
        },
        FinancialContext("us", ("AAPL",), "1d"),
    ],
)
async def test_legacy_prompt_decodes_raw_and_typed_quant_payloads(quant: Any) -> None:
    loop = _loop()

    blocks = await FinancialLegacyBehavior().build_prompt_blocks(
        loop,
        _request(quant=quant),
        "test-model",
    )

    assert any("Quant context" in block and "AAPL" in block for block in blocks)
    [extension_context] = loop.extension_registry.contexts
    assert extension_context == FinancialContext("us", ("AAPL",), "1d")


@pytest.mark.anyio
async def test_legacy_prompt_prefers_canonical_financial_context() -> None:
    loop = _loop()
    request = _request(
        context={
            "financial": {
                "market": "hk",
                "symbols": ["0700"],
                "timeframe": "1d",
            }
        },
        quant={
            "market": "us",
            "symbols": ["AAPL"],
            "timeframe": "1d",
        },
    )

    blocks = await FinancialLegacyBehavior().build_prompt_blocks(
        loop,
        request,
        "test-model",
    )

    assert any("market: hk" in block and "0700" in block for block in blocks)
    [extension_context] = loop.extension_registry.contexts
    assert extension_context == FinancialContext("hk", ("0700",), "1d")


@pytest.mark.anyio
async def test_legacy_prompt_reports_invalid_quant_field_path() -> None:
    with pytest.raises(
        FinancialContextError,
        match="context.financial.market",
    ):
        await FinancialLegacyBehavior().build_prompt_blocks(
            _loop(),
            _request(
                quant={
                    "market": "mars",
                    "symbols": ["AAPL"],
                    "timeframe": "1d",
                }
            ),
            "test-model",
        )
