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
    # text 8 chars + image 120 bytes -> 128 // 4 = 32
    assert _estimate_tokens_rough(messages) == 32


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
