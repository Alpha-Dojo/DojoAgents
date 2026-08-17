from dojoagents.agent.token_ledger import SessionTokenLedger


def test_session_token_ledger_record_and_save(tmp_path):
    ledger = SessionTokenLedger(tmp_path)
    state = ledger.load_or_create(
        "session-a",
        provider="openai",
        model_id="gpt-4.1",
        model_context_window=65536,
        session_max_tokens=65536,
        compression_threshold_ratio=0.8,
    )
    state.record_loop({"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120})
    state.record_loop({"prompt_tokens": 150, "completion_tokens": 10, "total_tokens": 160})
    ledger.save()

    reloaded = SessionTokenLedger(tmp_path)
    loaded = reloaded.load_or_create(
        "session-a",
        provider="openai",
        model_id="gpt-4.1",
        model_context_window=65536,
        session_max_tokens=65536,
        compression_threshold_ratio=0.8,
    )
    assert loaded.loop_count == 2
    assert loaded.cumulative_total_tokens == 280
    assert loaded.last_prompt_tokens == 150
    assert loaded.snapshot()["utilization_ratio"] > 0


def test_session_token_ledger_load_existing_does_not_create_missing_state(tmp_path):
    ledger = SessionTokenLedger(tmp_path)

    assert ledger.load_existing("missing") is None
    assert not (tmp_path / "missing.json").exists()


def test_session_token_ledger_update_context_window(tmp_path):
    ledger = SessionTokenLedger(tmp_path)
    state = ledger.load_or_create(
        "session-b",
        provider="openai",
        model_id="gpt-4.1",
        model_context_window=65536,
        session_max_tokens=65536,
        compression_threshold_ratio=0.8,
    )
    state.update_context_window(1048565)
    assert state.model_context_window == 1048565
    assert state.session_max_tokens == 1048565
