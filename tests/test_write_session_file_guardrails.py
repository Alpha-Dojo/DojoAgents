from __future__ import annotations

import json

import pytest

from dojoagents.agent.guardrails import ToolGuardrailDecision, toolguard_synthetic_result
from dojoagents.agent.models import LLMResult, ToolCall
from dojoagents.agent.providers import StaticLLMProvider
from dojoagents.agent.write_session_file_guardrails import (
    WriteSessionFileClassification,
    classify_write_session_file,
    write_session_file_guardrail_from_classification,
)
from dojoagents.tools.executor import ToolExecutor
from dojoagents.tools.process_registry import WriteSessionFileGuardContext, active_write_session_file_guard
from dojoagents.tools.registry import ToolRegistry
from dojoagents.tools.sandbox import SandboxPolicy
from dojoagents.tools.session_file_tool import get_write_session_file_spec


def _classification_json(*, allow_write: bool, explanation: str = "") -> str:
    return json.dumps({"allow_write": allow_write, "explanation": explanation})


@pytest.mark.asyncio
async def test_classifier_denies_unrequested_write() -> None:
    provider = StaticLLMProvider(
        [
            LLMResult(
                content=_classification_json(
                    allow_write=False,
                    explanation="User asked for analysis only.",
                )
            )
        ]
    )
    classification = await classify_write_session_file(
        "分析半导体板块",
        provider,
        model="test-model",
    )
    blocked, message, code = write_session_file_guardrail_from_classification(
        "write_session_file",
        classification,
    )
    assert blocked is True
    assert code == "write_session_file_user_request_required"
    assert "explicitly request" in message.lower()


@pytest.mark.asyncio
async def test_classifier_allows_explicit_file_request() -> None:
    provider = StaticLLMProvider(
        [LLMResult(content=_classification_json(allow_write=True, explanation="User asked to export JSON."))]
    )
    classification = await classify_write_session_file(
        "把结果导出为 analysis.json",
        provider,
        model="test-model",
    )
    blocked, _, code = write_session_file_guardrail_from_classification(
        "write_session_file",
        classification,
    )
    assert blocked is False
    assert code == "allow"


@pytest.mark.asyncio
async def test_classifier_caches_per_turn() -> None:
    provider = StaticLLMProvider([LLMResult(content=_classification_json(allow_write=True))])
    metadata: dict = {}
    await classify_write_session_file("save file", provider, model="test-model", request_metadata=metadata)
    await classify_write_session_file("save file", provider, model="test-model", request_metadata=metadata)
    assert len(provider.calls) == 1


@pytest.mark.asyncio
async def test_classifier_fails_closed_on_bad_json() -> None:
    provider = StaticLLMProvider([LLMResult(content="not json")])
    classification = await classify_write_session_file("分析", provider, model="test-model")
    blocked, _, code = write_session_file_guardrail_from_classification(
        "write_session_file",
        classification,
    )
    assert blocked is True
    assert code == "write_session_file_user_request_required"


def test_loop_style_guardrail_decision_payload() -> None:
    blocked, message, code = write_session_file_guardrail_from_classification(
        "write_session_file",
        WriteSessionFileClassification(allow_write=False, explanation="No file request."),
    )
    assert blocked is True
    decision = ToolGuardrailDecision(
        action="block",
        code=code,
        message=message,
        tool_name="write_session_file",
    )
    synth = toolguard_synthetic_result(decision)
    payload = json.loads(synth["content"])
    assert payload["guardrail"]["code"] == "write_session_file_user_request_required"


@pytest.mark.asyncio
async def test_tool_handler_blocks_when_guard_denies(tmp_path) -> None:
    provider = StaticLLMProvider([LLMResult(content=_classification_json(allow_write=False))])
    token = active_write_session_file_guard.set(
        WriteSessionFileGuardContext(
            llm_provider=provider,
            model="test-model",
            user_message="分析候选股",
            request_metadata={},
            enabled=True,
        )
    )
    try:
        registry = ToolRegistry()
        registry.register(get_write_session_file_spec(tmp_path))
        executor = ToolExecutor(registry, SandboxPolicy(timeout_seconds=5))
        result = await executor.execute_one(
            ToolCall(
                id="call-1",
                name="write_session_file",
                arguments={"filename": "report.json", "content": {"ok": True}, "format": "json"},
            ),
            session_id="sess-abc",
        )
    finally:
        active_write_session_file_guard.reset(token)

    assert result.ok is False
    assert "explicitly request" in result.error.lower()


@pytest.mark.asyncio
async def test_tool_handler_allows_when_guard_approves(tmp_path) -> None:
    provider = StaticLLMProvider([LLMResult(content=_classification_json(allow_write=True))])
    token = active_write_session_file_guard.set(
        WriteSessionFileGuardContext(
            llm_provider=provider,
            model="test-model",
            user_message="导出 analysis.json",
            request_metadata={},
            enabled=True,
        )
    )
    try:
        registry = ToolRegistry()
        registry.register(get_write_session_file_spec(tmp_path))
        executor = ToolExecutor(registry, SandboxPolicy(timeout_seconds=5))
        result = await executor.execute_one(
            ToolCall(
                id="call-1",
                name="write_session_file",
                arguments={"filename": "report.json", "content": {"ok": True}, "format": "json"},
            ),
            session_id="sess-abc",
        )
    finally:
        active_write_session_file_guard.reset(token)

    assert result.ok is True
    assert result.data["path"].endswith("sess-abc/outputs/report.json")
