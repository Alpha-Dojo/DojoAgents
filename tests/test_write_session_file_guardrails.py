from __future__ import annotations

import json
from pathlib import Path

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
from dojoagents.tasks.manager import TaskPromptManager
from dojoagents.tools.session_file_tool import get_write_session_file_spec


@pytest.fixture
def task_manager() -> TaskPromptManager:
    repo_root = Path(__file__).resolve().parents[1]
    built_in = repo_root / "dojoagents" / "tasks" / "built_in"
    pipelines = repo_root / "dojoagents" / "tasks" / "pipelines"
    return TaskPromptManager(task_dirs=[built_in], pipeline_dirs=[pipelines])


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
async def test_task_mode_allows_required_output_write_without_classifier(
    tmp_path: Path,
    task_manager: TaskPromptManager,
) -> None:
    provider = StaticLLMProvider(
        [LLMResult(content=_classification_json(allow_write=False, explanation="Should not run."))]
    )
    token = active_write_session_file_guard.set(
        WriteSessionFileGuardContext(
            llm_provider=provider,
            model="test-model",
            user_message="Run pipeline daily-market-events step 1: sector-attribution",
            request_metadata={
                "task_mode": True,
                "active_task": {
                    "task_id": "sector-attribution",
                    "params": {"trading_date": "2026-07-03"},
                    "outputs": [{"filename": "market_news_raw_pack_2026-07-03.json", "format": "json"}],
                },
            },
            enabled=True,
        )
    )
    try:
        registry = ToolRegistry()
        task_output_root = tmp_path / "task-outputs"
        registry.register(
            get_write_session_file_spec(
                tmp_path,
                task_output_root=task_output_root,
                task_manager=task_manager,
            )
        )
        executor = ToolExecutor(registry, SandboxPolicy())
        result = await executor.execute_one(
            ToolCall(
                id="call-task-write",
                name="write_session_file",
                arguments={
                    "filename": "market_news_raw_pack_2026-07-03.json",
                    "format": "json",
                    "content": {
                        "trading_date": "2026-07-03",
                        "window_start_date": "2026-07-03",
                        "window_end_date": "2026-07-03",
                        "sector_moves": [],
                        "news_items": [],
                        "sectors_without_news": [],
                    },
                },
            ),
            session_id="sess-task-write",
        )
    finally:
        active_write_session_file_guard.reset(token)

    assert result.ok is True
    assert len(provider.calls) == 0
    assert "sector-attribution" in result.content
    assert "market_news_raw_pack_2026-07-03.json" in result.content


@pytest.mark.asyncio
async def test_task_mode_rejects_placeholder_output(tmp_path: Path, task_manager: TaskPromptManager) -> None:
    provider = StaticLLMProvider(
        [LLMResult(content=_classification_json(allow_write=False, explanation="Should not run."))]
    )
    token = active_write_session_file_guard.set(
        WriteSessionFileGuardContext(
            llm_provider=provider,
            model="test-model",
            user_message="Run sector-attribution",
            request_metadata={
                "task_mode": True,
                "active_task": {
                    "task_id": "sector-attribution",
                    "params": {"trading_date": "2026-07-03"},
                    "outputs": [
                        {
                            "filename": "market_news_raw_pack_2026-07-03.json",
                            "format": "json",
                            "schema": "schema/market_news_raw_pack.schema.json",
                        }
                    ],
                },
            },
            enabled=True,
        )
    )
    try:
        registry = ToolRegistry()
        task_output_root = tmp_path / "task-outputs"
        registry.register(
            get_write_session_file_spec(
                tmp_path,
                task_output_root=task_output_root,
                task_manager=task_manager,
            )
        )
        executor = ToolExecutor(registry, SandboxPolicy())
        result = await executor.execute_one(
            ToolCall(
                id="call-task-placeholder",
                name="write_session_file",
                arguments={
                    "filename": "market_news_raw_pack_2026-07-03.json",
                    "format": "json",
                    "content": {
                        "note": "also saved at ~/.dojo/tasks/outputs/sector-attribution/foo.json",
                        "copy_of_task_output": True,
                    },
                },
            ),
            session_id="sess-task-placeholder",
        )
    finally:
        active_write_session_file_guard.reset(token)

    assert result.ok is False
    assert "placeholder" in str(result.error).lower() or "validation failed" in str(result.error).lower()


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
