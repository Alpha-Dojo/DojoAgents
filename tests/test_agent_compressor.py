from __future__ import annotations

import pytest
from dojoagents.agent.compressor import (
    ContextCompressor,
    _estimate_tokens_rough,
    _truncate_tool_call_args_json,
)
from dojoagents.agent.models import LLMResult


def test_rough_tokens_estimation():
    messages = [
        {"role": "system", "content": "You are a quant helper."},
        {"role": "user", "content": "Calculate the moving average."},
    ]
    # "You are a quant helper." -> 24 chars
    # "Calculate the moving average." -> 29 chars
    # Total chars = 53 -> estimated tokens = 53 // 4 = 13
    tokens = _estimate_tokens_rough(messages)
    assert tokens == 13


def test_rough_tokens_estimation_with_image_bytes():
    messages = [
        {
            "role": "user",
            "content": [
                {"text": "describe"},
                {"image": {"format": "png", "source": {"bytes": b"x" * 120}}},
            ],
        }
    ]
    # Image cost is a fixed conservative estimate; raw bytes/base64 length must
    # not inflate prompt character accounting or be persisted as text.
    assert _estimate_tokens_rough(messages) == 1026


def test_args_truncation():
    # Long string value inside JSON
    args_json = '{"path": "config.py", "content": "' + ("A" * 500) + '"}'
    shrunken = _truncate_tool_call_args_json(args_json, head_chars=50)

    import json

    parsed = json.loads(shrunken)
    assert parsed["path"] == "config.py"
    assert len(parsed["content"]) == 64  # 50 + len("...[truncated]")
    assert parsed["content"].endswith("...[truncated]")


def test_pre_pass_pruning():
    compressor = ContextCompressor(protect_last_n=2)

    messages = [
        {"role": "system", "content": "sys"},
        {
            "role": "assistant",
            "content": "thinking",
            "tool_calls": [
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {
                        "name": "read_file",
                        "arguments": '{"path": "test.py"}',
                    },
                }
            ],
        },
        # Outside tail, will be pruned
        {
            "role": "tool",
            "tool_call_id": "call_1",
            "content": "import pandas as pd\nimport numpy as np\n" + ("#" * 500),
        },
        # Protected tail (last 2 messages)
        {"role": "user", "content": "User tail"},
        {"role": "assistant", "content": "Assistant tail"},
    ]

    pruned = compressor.prune_old_tool_results(messages, protect_tail_count=2)
    assert len(pruned) == 5

    # Protected tail must be untouched
    assert pruned[3]["content"] == "User tail"
    assert pruned[4]["content"] == "Assistant tail"

    # Pruned tool result should be replaced by a 1-line summary
    pruned_tool_msg = pruned[2]
    assert pruned_tool_msg["role"] == "tool"
    assert "[read_file]" in pruned_tool_msg["content"]
    assert "test.py" in pruned_tool_msg["content"]
    assert len(pruned_tool_msg["content"]) < 100


class MockLLMProvider:
    def __init__(self, reply_content: str):
        self.reply_content = reply_content
        self.calls = []

    async def chat(self, messages, tools, model, **kwargs):
        self.calls.append((messages, tools, model))
        return LLMResult(content=self.reply_content)


@pytest.mark.asyncio
async def test_compression_trigger():
    compressor = ContextCompressor(protect_first_n=1, protect_last_n=1)
    provider = MockLLMProvider("Summary of middle history")

    messages = [
        {"role": "system", "content": "System message"},  # Head
        {"role": "user", "content": "Middle user 1"},  # Middle
        {"role": "assistant", "content": "Middle assistant 1"},  # Middle
        {"role": "user", "content": "Middle user 2"},  # Middle
        {"role": "user", "content": "Tail user"},  # Tail
    ]

    compressed = await compressor.compress(messages, provider, "gpt-4")

    # Head (1) + Summary (1) + Tail (1) = 3 messages
    assert len(compressed) == 3
    assert compressed[0]["content"] == "System message"
    assert "Summary of middle history" in compressed[1]["content"]
    assert compressed[2]["content"] == "Tail user"
    assert len(provider.calls) == 1


def _tool_history(*, pending=False):
    messages = [{"role": "user", "content": "research"}, {"role": "assistant", "content": "plan"}]
    for index in range(10):
        calls = [{"id": f"call-{index}-{part}", "type": "function", "function": {"name": "read_data", "arguments": "{}"}} for part in range(2)]
        messages.append({"role": "assistant", "content": "", "tool_calls": calls})
        for call in reversed(calls):
            messages.append({"role": "tool", "tool_call_id": call["id"], "content": "result"})
    if pending:
        messages.append(
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [{"id": "pending-call", "type": "function", "function": {"name": "read_data", "arguments": '{"query":"' + "x" * 500 + '"}'}}],
            }
        )
    else:
        messages.append({"role": "assistant", "content": "continue research"})
    return messages


def _assert_tool_pairs(messages, *, pending=frozenset()):
    outstanding = set()
    for message in messages:
        if message["role"] == "tool":
            assert message["tool_call_id"] in outstanding
            outstanding.remove(message["tool_call_id"])
        else:
            assert not outstanding
            ids = [call["id"] for call in message.get("tool_calls", [])]
            assert len(ids) == len(set(ids))
            outstanding.update(ids)
    assert outstanding == pending


@pytest.mark.anyio
@pytest.mark.parametrize("head,tail", [(3, 8), (1, 1), (0, 0), (99, 99)])
@pytest.mark.parametrize("strands", [False, True])
@pytest.mark.parametrize("pending", [False, True])
async def test_compression_keeps_parallel_tool_groups_and_pending_calls(head, tail, strands, pending):
    from copy import deepcopy
    from dojoagents.agent.compressor import flatten_messages_for_compress, messages_to_strands

    messages = _tool_history(pending=pending)
    if strands:
        messages = messages_to_strands(messages)
    before = deepcopy(messages)
    provider = MockLLMProvider("History summary")
    compressed = await ContextCompressor(head, tail).compress(messages, provider, "test-model")
    flat = flatten_messages_for_compress(compressed)
    _assert_tool_pairs(flat, pending={"pending-call"} if pending else set())
    assert messages == before
    if pending:
        assert flat[-1]["tool_calls"][0]["function"]["arguments"] == flatten_messages_for_compress(messages)[-1]["tool_calls"][0]["function"]["arguments"]
    if (head, tail) == (3, 8):
        assert provider.calls
        assert len(flat) < len(before)


def test_failed_tool_status_survives_pruning_and_format_roundtrip():
    from dojoagents.agent.compressor import flatten_messages_for_compress, messages_to_strands

    messages = [
        {"role": "assistant", "content": [{"toolUse": {"toolUseId": "failed-call", "name": "execute_code", "input": {}}}]},
        {
            "role": "user",
            "content": [{"toolResult": {"toolUseId": "failed-call", "name": "execute_code", "status": "error", "content": [{"text": "ValueError: bad input " + "x" * 500}]}}],
        },
        {"role": "assistant", "content": [{"text": "continue"}]},
    ]
    flat = flatten_messages_for_compress(messages)
    result = messages_to_strands(flat)
    assert result[1]["content"][0]["toolResult"]["status"] == "error"
    pruned = ContextCompressor().prune_old_tool_results(messages, protect_tail_count=1)
    failure = pruned[1]["content"][0]["toolResult"]
    assert failure["toolUseId"] == "failed-call" and failure["status"] == "error"
    assert "ValueError: bad input" in failure["content"][0]["text"]


@pytest.mark.anyio
@pytest.mark.parametrize("fault", ["orphan", "missing", "duplicate_call", "duplicate_result"])
async def test_invalid_source_is_preserved_and_logged_without_contents(fault, caplog):
    messages = _tool_history()
    if fault == "orphan":
        messages[3]["tool_call_id"] = "unknown-call"
    elif fault == "missing":
        del messages[3]
    elif fault == "duplicate_call":
        messages[2]["tool_calls"][1]["id"] = messages[2]["tool_calls"][0]["id"]
    else:
        messages.insert(4, dict(messages[3]))
    messages[0]["content"] = "private research text"
    provider = MockLLMProvider("summary")
    compressed = await ContextCompressor().compress(messages, provider, "test-model", session_id="session-test")
    assert compressed is messages
    assert not provider.calls
    assert "context_compression_pairing_invalid" in caplog.text
    assert "session-test" in caplog.text and "index=" in caplog.text
    assert "private research text" not in caplog.text


@pytest.mark.anyio
@pytest.mark.parametrize("corruption", ["result_id", "pending_id"])
async def test_invalid_converted_result_rolls_back_before_saving_summary_or_memory(monkeypatch, caplog, corruption):
    from copy import deepcopy
    from unittest.mock import AsyncMock
    from dojoagents.agent import compressor as module

    messages = module.messages_to_strands(_tool_history(pending=corruption == "pending_id"))
    before = deepcopy(messages)
    convert = module.messages_to_strands

    def corrupt_results(flat):
        converted = convert(flat)
        for message in converted:
            for block in message["content"]:
                if corruption == "result_id" and "toolResult" in block:
                    block["toolResult"]["toolUseId"] = "wrong-call"
                    return converted
                if corruption == "pending_id" and block.get("toolUse", {}).get("toolUseId") == "pending-call":
                    block["toolUse"]["toolUseId"] = "wrong-pending-call"
                    return converted
        return converted

    monkeypatch.setattr(module, "messages_to_strands", corrupt_results)
    compressor = ContextCompressor()
    provider = MockLLMProvider("[CONSOLIDATION SUMMARY]summary[LONG-TERM FACTS]fact")
    memory = type("Memory", (), {"save_memory": AsyncMock()})()
    result = await compressor.compress(messages, provider, "test-model", memory_manager=memory, session_id="session-test")
    assert result is messages and messages == before
    assert compressor._previous_summary is None
    memory.save_memory.assert_not_awaited()
    assert "context_compression_pairing_invalid" in caplog.text


@pytest.mark.anyio
async def test_compression_retains_failed_result_and_partial_pending_batch():
    from dojoagents.agent.compressor import flatten_messages_for_compress, messages_to_strands

    messages = _tool_history()
    messages.pop()
    messages[-1].update(status="error", content="ValueError: invalid data " + "x" * 500)
    messages.extend(
        [
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [{"id": name, "type": "function", "function": {"name": "read_data", "arguments": "{}"}} for name in ("pending-a", "pending-b")],
            },
            {"role": "tool", "tool_call_id": "pending-b", "status": "error", "content": "temporary failure"},
        ]
    )
    source = messages_to_strands(messages)
    compressed = await ContextCompressor(3, 8).compress(source, MockLLMProvider("summary"), "test-model")
    flat = flatten_messages_for_compress(compressed)
    _assert_tool_pairs(flat, pending={"pending-a"})
    for call_id in ("call-9-0", "pending-b"):
        failure = next(message for message in flat if message.get("tool_call_id") == call_id)
        assert failure["status"] == "error"
    assert "ValueError: invalid data" in next(message["content"] for message in flat if message.get("tool_call_id") == "call-9-0")
