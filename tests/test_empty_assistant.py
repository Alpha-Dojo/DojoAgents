from __future__ import annotations

import pytest

from dojoagents.agent.empty_assistant import (
    build_empty_assistant_recovery_prompt,
    is_empty_assistant_content,
    last_assistant_turn_empty,
    mark_incomplete_assistant_payload,
    sanitize_session_message,
)
from dojoagents.agent.models import ChatRequest, LLMResult
from dojoagents.agent.providers import StaticLLMProvider
from dojoagents.agent.turn_intent import (
    TurnIntentResult,
    build_turn_intent_anchor_async,
    format_unfinished_task_summary,
)
from strands.types.session import SessionMessage


def test_is_empty_assistant_content_detects_blank_turn() -> None:
    assert is_empty_assistant_content([]) is True
    assert is_empty_assistant_content([{"text": "  "}]) is True
    assert is_empty_assistant_content([{"toolUse": {"toolUseId": "x", "name": "t", "input": {}}}]) is False
    assert is_empty_assistant_content([{"text": "done"}]) is False


def test_last_assistant_turn_empty() -> None:
    messages = [
        {"role": "user", "content": [{"text": "hello"}]},
        {"role": "assistant", "content": []},
    ]
    assert last_assistant_turn_empty(messages) is True


def test_mark_incomplete_assistant_payload_adds_metadata_and_placeholder() -> None:
    marked = mark_incomplete_assistant_payload({"role": "assistant", "content": []}, locale="zh")
    assert marked["metadata"]["dojo_incomplete"] is True
    assert marked["content"][0]["text"].startswith("[未完成：")


def test_sanitize_session_message_rewrites_empty_assistant() -> None:
    original = SessionMessage.from_message({"role": "assistant", "content": []}, 3)
    sanitized = sanitize_session_message(original, locale="en")
    payload = sanitized.to_message()
    assert payload["metadata"]["dojo_incomplete"] is True
    assert payload["content"][0]["text"].startswith("[INCOMPLETE:")


@pytest.mark.asyncio
async def test_build_turn_intent_anchor_for_continuation_overrides_closed_turn_rule() -> None:
    provider = StaticLLMProvider(
        [
            LLMResult(
                content=(
                    '{"continue_unfinished": true, '
                    '"prior_task_summary": "构建半导体行业上下游关系图谱", '
                    '"last_turn_status": "tools_only_no_deliverable", '
                    '"needs_code_execution": false}'
                )
            )
        ]
    )
    request = ChatRequest(
        user_id="local",
        session_id="sess-1",
        channel="dashboard",
        message="继续执行前述任务",
        metadata={
            "locale": "zh",
            "history": [
                {"role": "user", "content": "构建半导体行业上下游关系图谱"},
                {"role": "assistant", "content": "工具执行已完成，请查看上方步骤与组合更新。"},
            ],
        },
    )
    anchor_text, _intent = await build_turn_intent_anchor_async(request, provider, model="test-model")
    assert "续做未完成工作" in anchor_text
    assert "半导体行业上下游关系图谱" in anchor_text
    assert "不要继续执行旧任务" not in anchor_text


def test_format_unfinished_task_summary_mentions_tools_placeholder() -> None:
    summary = format_unfinished_task_summary(
        TurnIntentResult(
            mode="continue_unfinished",
            prior_task_summary="构建半导体行业上下游关系图谱",
            last_turn_status="tools_only_no_deliverable",
        ),
        "zh",
    )
    assert "半导体" in summary
    assert "占位" in summary or "交付" in summary


def test_recovery_prompt_mentions_tool_results_when_present() -> None:
    prompt = build_empty_assistant_recovery_prompt("zh", tools_ran=True)
    assert "工具结果" in prompt
