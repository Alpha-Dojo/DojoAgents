import pytest
from unittest.mock import AsyncMock, MagicMock

from dojoagents.agent.compressor import _estimate_tokens_rough, flatten_messages_for_compress
from dojoagents.agent.hooks.token_compression import TokenCompressionHook
from dojoagents.agent.token_ledger import SessionTokenLedger
from dojoagents.agent.token_policy import TokenCompressionPolicy


@pytest.mark.asyncio
async def test_before_model_call_compresses_on_message_estimate(tmp_path):
    ledger = SessionTokenLedger(tmp_path)
    state = ledger.load_or_create(
        "session-1",
        provider="openai",
        model_id="gpt-4.1",
        model_context_window=1000,
        session_max_tokens=1000,
        compression_threshold_ratio=0.8,
    )
    state.last_prompt_tokens = 100

    huge_text = "x" * 4000
    agent = MagicMock()
    agent.messages = [{"role": "user", "content": [{"text": huge_text}]}]

    compressor = MagicMock()
    compressor.compress = AsyncMock(return_value=[{"role": "user", "content": [{"text": "compact"}]}])

    hook = TokenCompressionHook(
        compressor=compressor,
        policy=TokenCompressionPolicy(threshold_ratio=0.8),
        llm_provider=MagicMock(),
        model="gpt-4.1",
        memory_manager=MagicMock(),
        enabled=True,
    )

    invocation_state = {
        "_dojo_token_ledger": ledger,
        "_dojo_compression_policy": TokenCompressionPolicy(threshold_ratio=0.8),
        "session_id": "session-1",
    }
    event = MagicMock(agent=agent, invocation_state=invocation_state, projected_input_tokens=None)

    await hook._before_model_call(event)

    compressor.compress.assert_awaited_once()
    assert agent.messages == [{"role": "user", "content": [{"text": "compact"}]}]
    assert state.compression_count == 1
    assert state.last_prompt_tokens == _estimate_tokens_rough(flatten_messages_for_compress(agent.messages))


@pytest.mark.asyncio
async def test_handle_context_length_exceeded_forces_compress_and_updates_window(tmp_path):
    ledger = SessionTokenLedger(tmp_path)
    state = ledger.load_or_create(
        "session-2",
        provider="openai",
        model_id="gpt-4.1",
        model_context_window=65536,
        session_max_tokens=65536,
        compression_threshold_ratio=0.8,
    )

    agent = MagicMock()
    agent.messages = [{"role": "user", "content": [{"text": "payload"}]}]

    compressor = MagicMock()
    compressor.compress = AsyncMock(return_value=[{"role": "user", "content": [{"text": "smaller"}]}])
    registry = MagicMock()

    hook = TokenCompressionHook(
        compressor=compressor,
        policy=TokenCompressionPolicy(threshold_ratio=0.8),
        llm_provider=MagicMock(),
        model="gpt-4.1",
        memory_manager=MagicMock(),
        enabled=True,
        model_context_registry=registry,
    )

    invocation_state = {"_dojo_token_ledger": ledger, "session_id": "session-2"}
    ok = await hook.handle_context_length_exceeded(
        agent,
        invocation_state,
        max_context=1048565,
        requested_tokens=3037564,
    )

    assert ok is True
    assert state.session_max_tokens == 1048565
    assert state.compression_count == 1
    assert state.last_prompt_tokens < 100
    registry.note_context_window.assert_called_once_with("openai", "gpt-4.1", 1048565)
    compressor.compress.assert_awaited_once()
